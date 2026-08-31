from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from urllib.parse import unquote, urlparse


class ResourcePoolImportError(ValueError):
    pass


@dataclass(frozen=True)
class ProxyImportRow:
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    label: str | None = None

    @property
    def endpoint_key(self) -> str:
        normalized = f"socks5|{self.host.lower()}|{self.port}|{self.username or ''}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AccountImportRow:
    name: str
    platform: str
    group_name: str | None = None
    login_identifier: str | None = None
    password: str | None = None
    totp_secret: str | None = None
    cookie_json: str | None = None
    proxy: str | None = None
    notes: str | None = None


_PROXY_HEADER_NAMES = {"host", "ip", "服务器", "地址"}
_ACCOUNT_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "账号名称", "名称", "账号"),
    "platform": ("platform", "平台"),
    "group_name": ("group", "group_name", "分组", "账号分组"),
    "login_identifier": ("login", "login_identifier", "username", "登录账号", "用户名", "邮箱"),
    "password": ("password", "密码"),
    "totp_secret": ("totp", "totp_secret", "2fa", "2fa_secret", "二步验证", "验证密钥"),
    "cookie_json": ("cookie", "cookies", "cookie_json", "Cookie", "Cookies"),
    "proxy": ("proxy", "proxy_id", "socks5", "ip", "IP", "代理"),
    "notes": ("notes", "备注"),
}


def parse_proxy_import_text(text: str) -> list[ProxyImportRow]:
    """Parse common SOCKS5 provider exports.

    Supported lines:
    - host:port
    - host:port:username:password
    - socks5://username:password@host:port
    - CSV/TSV: host,port,username,password,label
    """

    rows: list[ProxyImportRow] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue
        try:
            row = _parse_proxy_line(line)
        except ResourcePoolImportError as exc:
            raise ResourcePoolImportError(f"第 {line_number} 行：{exc}") from exc
        if row is None:
            continue
        rows.append(row)

    if not rows:
        raise ResourcePoolImportError("没有找到可导入的 SOCKS5 记录。")
    if len(rows) > 5000:
        raise ResourcePoolImportError("一次最多导入 5000 条 SOCKS5。")

    keys = [row.endpoint_key for row in rows]
    if len(keys) != len(set(keys)):
        raise ResourcePoolImportError("导入内容中存在重复的 SOCKS5 记录。")
    return rows


def _parse_proxy_line(line: str) -> ProxyImportRow | None:
    lower = line.lower()
    if lower.startswith("socks5://"):
        parsed = urlparse(line)
        if not parsed.hostname or parsed.port is None:
            raise ResourcePoolImportError("SOCKS5 URL 缺少 Host 或 Port。")
        return _proxy_row(
            parsed.hostname,
            parsed.port,
            unquote(parsed.username) if parsed.username else None,
            unquote(parsed.password) if parsed.password else None,
            None,
        )

    delimiter = "\t" if "\t" in line and "," not in line else "," if "," in line else None
    if delimiter:
        values = next(csv.reader([line], delimiter=delimiter))
        values = [value.strip() for value in values]
        if values and values[0].lower() in _PROXY_HEADER_NAMES:
            return None
        if len(values) < 2:
            raise ResourcePoolImportError("CSV 至少需要 host 和 port 两列。")
        return _proxy_row(
            values[0],
            values[1],
            values[2] if len(values) > 2 else None,
            values[3] if len(values) > 3 else None,
            values[4] if len(values) > 4 else None,
        )

    parts = line.split(":", 3)
    if len(parts) not in {2, 4}:
        raise ResourcePoolImportError("支持 host:port 或 host:port:username:password 格式。")
    return _proxy_row(
        parts[0],
        parts[1],
        parts[2] if len(parts) == 4 else None,
        parts[3] if len(parts) == 4 else None,
        None,
    )


def _proxy_row(host: object, port: object, username: object, password: object, label: object) -> ProxyImportRow:
    normalized_host = str(host or "").strip()
    if not normalized_host:
        raise ResourcePoolImportError("Host 不能为空。")
    try:
        normalized_port = int(str(port).strip())
    except (TypeError, ValueError) as exc:
        raise ResourcePoolImportError("Port 必须是数字。") from exc
    if not 1 <= normalized_port <= 65535:
        raise ResourcePoolImportError("Port 必须在 1-65535 之间。")

    normalized_username = str(username or "").strip() or None
    normalized_password = str(password or "").strip() or None
    if bool(normalized_username) != bool(normalized_password):
        raise ResourcePoolImportError("SOCKS5 用户名和密码必须同时提供，或同时留空。")

    return ProxyImportRow(
        host=normalized_host,
        port=normalized_port,
        username=normalized_username,
        password=normalized_password,
        label=str(label or "").strip() or None,
    )


def parse_account_import_csv(text: str) -> list[AccountImportRow]:
    """Parse account-pool CSV with English or Chinese column names."""

    stream = io.StringIO(text.lstrip("\ufeff"))
    try:
        reader = csv.DictReader(stream)
    except csv.Error as exc:
        raise ResourcePoolImportError("账号 CSV 无法解析。") from exc
    if not reader.fieldnames:
        raise ResourcePoolImportError("账号 CSV 必须包含表头。")

    field_lookup = {str(name).strip(): str(name) for name in reader.fieldnames if name is not None}

    def source_name(canonical: str) -> str | None:
        for alias in _ACCOUNT_ALIASES[canonical]:
            if alias in field_lookup:
                return field_lookup[alias]
        lower_lookup = {key.lower(): value for key, value in field_lookup.items()}
        for alias in _ACCOUNT_ALIASES[canonical]:
            if alias.lower() in lower_lookup:
                return lower_lookup[alias.lower()]
        return None

    name_column = source_name("name")
    if not name_column:
        raise ResourcePoolImportError("账号 CSV 缺少“账号名称/name”列。")

    columns = {key: source_name(key) for key in _ACCOUNT_ALIASES}
    rows: list[AccountImportRow] = []
    for row_number, raw in enumerate(reader, start=2):
        if not raw or not any(str(value or "").strip() for value in raw.values()):
            continue

        def value(key: str) -> str | None:
            column = columns[key]
            if not column:
                return None
            normalized = str(raw.get(column) or "").strip()
            return normalized or None

        name = value("name")
        if not name:
            raise ResourcePoolImportError(f"第 {row_number} 行：账号名称不能为空。")
        platform = (value("platform") or "facebook").lower()
        if platform not in {"facebook", "instagram"}:
            raise ResourcePoolImportError(f"第 {row_number} 行：当前批量导入只支持 Facebook / Instagram。")

        rows.append(
            AccountImportRow(
                name=name,
                platform=platform,
                group_name=value("group_name"),
                login_identifier=value("login_identifier"),
                password=value("password"),
                totp_secret=value("totp_secret"),
                cookie_json=value("cookie_json"),
                proxy=value("proxy"),
                notes=value("notes"),
            )
        )

    if not rows:
        raise ResourcePoolImportError("账号 CSV 中没有可导入记录。")
    if len(rows) > 2000:
        raise ResourcePoolImportError("一次最多导入 2000 个账号。")
    return rows
