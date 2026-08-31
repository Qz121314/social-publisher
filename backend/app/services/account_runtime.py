from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.account import Account, BrowserProfile
from app.models.resource_pool import ProxyEndpoint
from app.services.browser_sessions import BrowserSessionError, browser_sessions
from app.services.credential_vault import (
    CredentialVaultError,
    credential_vault,
    proxy_secret_reference,
)
from app.services.ixbrowser import IXBrowserError, IXBrowserService
from app.services.profile_locks import ProfileBusyError, profile_locks
from app.services.profile_sync import sanitize_profile_payload


class AccountRuntimeError(RuntimeError):
    pass


class AccountRuntimeNeedsAttention(AccountRuntimeError):
    pass


def ensure_account_runtime(db: Session, account: Account) -> int:
    """Materialize or reconcile the persistent iX runtime for one account.

    Imported account resources may not have an iX Profile yet. The first batch
    login creates one deterministic Profile, applies the account's fixed SOCKS5,
    stores only safe Profile metadata locally, and permanently binds it back to
    the account. Existing Profile bindings are reused rather than recreated.
    """

    if account.ix_profile_id is not None:
        profile = db.get(BrowserProfile, account.ix_profile_id)
        if profile is None:
            raise AccountRuntimeNeedsAttention(
                f"账号已绑定 iX #{account.ix_profile_id}，但本地没有该环境，请先同步 iXBrowser。"
            )
        _reconcile_existing_proxy(db, account, profile)
        return int(account.ix_profile_id)

    if account.proxy_id is None:
        raise AccountRuntimeNeedsAttention("账号尚未分配 SOCKS5，请先在账号池分配 IP。")

    endpoint = db.get(ProxyEndpoint, account.proxy_id)
    if endpoint is None or not endpoint.enabled:
        raise AccountRuntimeNeedsAttention("账号绑定的 SOCKS5 已不存在或已停用。")
    if endpoint.status == "error":
        raise AccountRuntimeNeedsAttention("账号绑定的 SOCKS5 当前标记为异常，请先检查 IP。")

    ix = IXBrowserService()
    profile_name = _runtime_profile_name(account)

    # Idempotency: if the previous process created the Profile but died before
    # binding it to Account, reuse the deterministic Profile instead of creating
    # another environment on retry.
    existing = ix.find_profile_by_name(profile_name)
    if existing is not None:
        profile_id = _profile_id(existing)
        if profile_id is None:
            raise AccountRuntimeError("找到同名 iX 环境，但无法读取 Profile ID。")
        _materialize_local_profile(db, ix, profile_id, profile_name)
        account.ix_profile_id = profile_id
        account.status = "runtime_ready"
        db.commit()
        _reconcile_existing_proxy(db, account, db.get(BrowserProfile, profile_id))
        return profile_id

    username, password = _proxy_credentials(endpoint)
    try:
        created = ix.create_profile(
            name=profile_name,
            site_url=_platform_start_url(account.platform),
            proxy_type="socks5",
            proxy_ip=endpoint.host,
            proxy_port=endpoint.port,
            proxy_user=username,
            proxy_password=password,
        )
    except IXBrowserError as exc:
        raise AccountRuntimeError(str(exc)) from exc

    profile_id = _profile_id(created)
    if profile_id is None:
        match = ix.find_profile_by_name(profile_name)
        profile_id = _profile_id(match) if match is not None else None
    if profile_id is None:
        raise AccountRuntimeError(
            "iXBrowser 已创建环境，但没有返回可绑定的 Profile ID。请同步环境后重试，不要重复创建。"
        )

    _materialize_local_profile(db, ix, profile_id, profile_name)
    account.ix_profile_id = profile_id
    account.status = "runtime_ready"
    db.commit()
    return profile_id


def _reconcile_existing_proxy(
    db: Session,
    account: Account,
    profile: BrowserProfile | None,
) -> None:
    if profile is None or account.proxy_id is None:
        return
    endpoint = db.get(ProxyEndpoint, account.proxy_id)
    if endpoint is None or not endpoint.enabled:
        raise AccountRuntimeNeedsAttention("账号绑定的 SOCKS5 已不存在或已停用。")

    same_proxy = (
        profile.proxy_type == "socks5"
        and profile.proxy_ip == endpoint.host
        and str(profile.proxy_port or "") == str(endpoint.port)
    )
    if same_proxy:
        return

    try:
        profile_locks.assert_unlocked(db, profile.profile_id)
    except ProfileBusyError as exc:
        raise AccountRuntimeNeedsAttention("该 iX 环境正在执行其他任务，暂时不能更新固定 SOCKS5。") from exc

    try:
        browser_sessions.close(profile.profile_id, force=True)
    except (IXBrowserError, BrowserSessionError):
        # If there is no managed open session this is harmless; iX update below
        # remains the source of truth and will fail explicitly if the Profile is busy.
        pass

    username, password = _proxy_credentials(endpoint)
    ix = IXBrowserService()
    try:
        ix.update_profile_socks5_proxy(
            profile.profile_id,
            proxy_ip=endpoint.host,
            proxy_port=endpoint.port,
            proxy_user=username,
            proxy_password=password,
        )
        remote = ix.get_profile(profile.profile_id)
    except IXBrowserError as exc:
        raise AccountRuntimeError(str(exc)) from exc

    if remote is not None:
        profile.raw_json = json.dumps(sanitize_profile_payload(remote), ensure_ascii=False, default=str)
        db.commit()


def _proxy_credentials(endpoint: ProxyEndpoint) -> tuple[str | None, str | None]:
    username = None
    password = None
    try:
        if endpoint.username_configured:
            username = credential_vault.get_text(proxy_secret_reference(endpoint.id, "username"))
        if endpoint.password_configured:
            password = credential_vault.get_text(proxy_secret_reference(endpoint.id, "password"))
    except CredentialVaultError as exc:
        raise AccountRuntimeNeedsAttention(f"无法读取 SOCKS5 安全凭据：{exc}") from exc
    return username, password


def _materialize_local_profile(
    db: Session,
    ix: IXBrowserService,
    profile_id: int,
    fallback_name: str,
) -> BrowserProfile:
    local = db.get(BrowserProfile, profile_id)
    if local is not None:
        return local

    try:
        remote = ix.get_profile(profile_id)
    except IXBrowserError as exc:
        raise AccountRuntimeError(f"iX #{profile_id} 已创建，但无法读取环境信息：{exc}") from exc
    if remote is None:
        raise AccountRuntimeError(f"iX #{profile_id} 已创建，但无法读取环境信息。")

    local = BrowserProfile(
        profile_id=profile_id,
        name=str(remote.get("name") or fallback_name),
        group_id=_optional_int(remote.get("group_id")),
        group_name=_optional_str(remote.get("group_name")),
        raw_json=json.dumps(sanitize_profile_payload(remote), ensure_ascii=False, default=str),
        is_available=True,
    )
    db.merge(local)
    db.commit()
    return db.get(BrowserProfile, profile_id) or local


def _runtime_profile_name(account: Account) -> str:
    safe = " ".join(account.name.strip().split())[:80] or f"Account-{account.id}"
    return f"SP-{account.id}-{safe}"


def _platform_start_url(platform: str) -> str:
    return {
        "facebook": "https://www.facebook.com/",
        "instagram": "https://www.instagram.com/",
    }.get(platform, "chrome://newtab")


def _profile_id(value: object) -> int | None:
    if isinstance(value, dict):
        candidate = value.get("profile_id", value.get("id"))
    else:
        candidate = value
    if isinstance(candidate, bool):
        return None
    try:
        result = int(candidate)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
