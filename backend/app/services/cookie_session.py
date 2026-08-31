from __future__ import annotations

import json
from typing import Any


class CookieSessionError(ValueError):
    pass


MAX_COOKIE_PAYLOAD_BYTES = 512 * 1024
MAX_COOKIES = 500
PLATFORM_COOKIE_DOMAINS: dict[str, tuple[str, ...]] = {
    "facebook": ("facebook.com",),
    "instagram": ("instagram.com",),
}


def _domain_matches(domain: str, suffix: str) -> bool:
    normalized = domain.strip().lower().lstrip(".")
    return normalized == suffix or normalized.endswith(f".{suffix}")


def normalize_cookie_payload(raw: str, platform: str) -> tuple[str, int]:
    """Validate and reduce a browser-cookie export to platform cookies only.

    The normalized JSON is suitable for encrypted storage in CredentialVault.
    Unknown fields and third-party domains are discarded instead of being
    persisted blindly.
    """

    encoded = raw.encode("utf-8")
    if len(encoded) > MAX_COOKIE_PAYLOAD_BYTES:
        raise CookieSessionError("Cookie 数据过大，单个账号最多允许 512 KB。")

    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CookieSessionError("Cookie 必须是有效的 JSON。") from exc

    if isinstance(payload, dict):
        payload = payload.get("cookies")
    if not isinstance(payload, list):
        raise CookieSessionError("Cookie JSON 必须是数组，或包含 cookies 数组。")
    if len(payload) > MAX_COOKIES:
        raise CookieSessionError(f"Cookie 数量不能超过 {MAX_COOKIES} 条。")

    allowed_suffixes = PLATFORM_COOKIE_DOMAINS.get(platform)
    if not allowed_suffixes:
        raise CookieSessionError("当前平台暂未开放 Cookie 登录。")

    normalized: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = item.get("value")
        domain = str(item.get("domain") or "").strip().lower()
        if not name or value is None or not domain:
            continue
        if not any(_domain_matches(domain, suffix) for suffix in allowed_suffixes):
            continue

        cookie: dict[str, Any] = {
            "name": name,
            "value": str(value),
            "domain": domain,
            "path": str(item.get("path") or "/"),
        }
        if isinstance(item.get("secure"), bool):
            cookie["secure"] = item["secure"]
        if isinstance(item.get("httpOnly"), bool):
            cookie["httpOnly"] = item["httpOnly"]
        elif isinstance(item.get("httponly"), bool):
            cookie["httpOnly"] = item["httponly"]

        expiry = item.get("expiry", item.get("expirationDate"))
        if isinstance(expiry, (int, float)) and expiry > 0:
            cookie["expiry"] = int(expiry)

        same_site = item.get("sameSite")
        if isinstance(same_site, str):
            lookup = same_site.strip().lower()
            mapped = {
                "strict": "Strict",
                "lax": "Lax",
                "none": "None",
                "no_restriction": "None",
                "unspecified": None,
            }.get(lookup)
            if mapped:
                cookie["sameSite"] = mapped

        normalized.append(cookie)

    if not normalized:
        platform_name = "Facebook" if platform == "facebook" else "Instagram"
        raise CookieSessionError(f"没有找到可用于 {platform_name} 的有效 Cookie。")

    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":")), len(normalized)
