from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.account import Account, AccountGroup
from app.models.auth import AccountAuthConfig
from app.models.resource_pool import ProxyEndpoint
from app.schemas.resource_pool import (
    AccountBatchProxyAssign,
    AccountPoolImportText,
    ProxyBatchDelete,
    ProxyEndpointRead,
    ProxyImportText,
)
from app.services.cookie_session import CookieSessionError, normalize_cookie_payload
from app.services.credential_vault import (
    CredentialVaultError,
    CredentialVaultUnavailable,
    account_secret_reference,
    clear_account_secrets,
    clear_proxy_secrets,
    credential_vault,
    proxy_secret_reference,
)
from app.services.login_engine import normalize_totp_secret
from app.services.resource_pool import (
    AccountImportRow,
    ResourcePoolImportError,
    parse_account_import_csv,
    parse_proxy_import_text,
)

router = APIRouter(tags=["resource-pools"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/proxy-pool", response_model=list[ProxyEndpointRead])
def list_proxy_pool(db: Session = Depends(get_db)) -> list[ProxyEndpointRead]:
    assigned = dict(
        db.execute(
            select(Account.proxy_id, func.count(Account.id))
            .where(Account.proxy_id.is_not(None))
            .group_by(Account.proxy_id)
        ).all()
    )
    items = list(db.scalars(select(ProxyEndpoint).order_by(ProxyEndpoint.id.desc())).all())
    return [
        ProxyEndpointRead.model_validate(item).model_copy(
            update={"assigned_count": int(assigned.get(item.id, 0))}
        )
        for item in items
    ]


@router.post("/proxy-pool/import")
def import_proxy_pool(payload: ProxyImportText, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        rows = parse_proxy_import_text(payload.text)
    except ResourcePoolImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing_keys = set(
        db.scalars(
            select(ProxyEndpoint.endpoint_key).where(
                ProxyEndpoint.endpoint_key.in_([row.endpoint_key for row in rows])
            )
        ).all()
    )
    created_ids: list[int] = []
    skipped = 0
    try:
        for row in rows:
            if row.endpoint_key in existing_keys:
                skipped += 1
                continue
            endpoint = ProxyEndpoint(
                endpoint_key=row.endpoint_key,
                protocol="socks5",
                host=row.host,
                port=row.port,
                label=row.label,
                username_configured=bool(row.username),
                password_configured=bool(row.password),
                status="unknown",
            )
            db.add(endpoint)
            db.flush()
            created_ids.append(endpoint.id)
            if row.username:
                credential_vault.put_text(proxy_secret_reference(endpoint.id, "username"), row.username)
            if row.password:
                credential_vault.put_text(proxy_secret_reference(endpoint.id, "password"), row.password)
        db.commit()
    except CredentialVaultUnavailable as exc:
        db.rollback()
        for proxy_id in created_ids:
            clear_proxy_secrets(proxy_id)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CredentialVaultError as exc:
        db.rollback()
        for proxy_id in created_ids:
            clear_proxy_secrets(proxy_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "status": "ok",
        "received": len(rows),
        "created": len(created_ids),
        "skipped": skipped,
    }


@router.post("/proxy-pool/batch/delete")
def delete_proxy_pool(payload: ProxyBatchDelete, db: Session = Depends(get_db)) -> dict[str, object]:
    ids = list(dict.fromkeys(payload.proxy_ids))
    endpoints = list(db.scalars(select(ProxyEndpoint).where(ProxyEndpoint.id.in_(ids))).all())
    found = {item.id for item in endpoints}
    missing = [item for item in ids if item not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"未找到 IP：{', '.join(map(str, missing[:10]))}")

    assigned = set(
        db.scalars(select(Account.proxy_id).where(Account.proxy_id.in_(ids))).all()
    )
    assigned.discard(None)
    if assigned:
        raise HTTPException(
            status_code=409,
            detail=f"有 {len(assigned)} 个 IP 仍绑定账号，请先解除或重新分配。",
        )

    for endpoint in endpoints:
        clear_proxy_secrets(endpoint.id)
        db.delete(endpoint)
    db.commit()
    return {"status": "ok", "deleted": len(endpoints)}


@router.post("/account-pool/import")
def import_account_pool(payload: AccountPoolImportText, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        rows = parse_account_import_csv(payload.text)
        prepared = [_prepare_account_row(row) for row in rows]
    except (ResourcePoolImportError, CookieSessionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing_identifiers = {
        (platform, identifier.lower())
        for platform, identifier in db.execute(
            select(Account.platform, AccountAuthConfig.login_identifier)
            .join(AccountAuthConfig, AccountAuthConfig.account_id == Account.id)
            .where(AccountAuthConfig.login_identifier.is_not(None))
        ).all()
        if identifier
    }

    group_by_name = {
        item.name.lower(): item
        for item in db.scalars(select(AccountGroup)).all()
    }
    created_account_ids: list[int] = []
    skipped = 0
    seen_identifiers: set[tuple[str, str]] = set()

    try:
        for row, normalized_totp, normalized_cookies, cookie_count in prepared:
            identity_key = (
                (row.platform, row.login_identifier.lower())
                if row.login_identifier
                else None
            )
            if identity_key and (identity_key in existing_identifiers or identity_key in seen_identifiers):
                skipped += 1
                continue
            if identity_key:
                seen_identifiers.add(identity_key)

            group_id = None
            if row.group_name:
                group = group_by_name.get(row.group_name.lower())
                if group is None:
                    group = AccountGroup(name=row.group_name)
                    db.add(group)
                    db.flush()
                    group_by_name[row.group_name.lower()] = group
                group_id = group.id

            proxy_id = _resolve_proxy_reference(db, row.proxy)
            account = Account(
                name=row.name,
                platform=row.platform,
                ix_profile_id=None,
                group_id=group_id,
                proxy_id=proxy_id,
                status="prepared",
                notes=row.notes,
            )
            db.add(account)
            db.flush()
            created_account_ids.append(account.id)

            config = AccountAuthConfig(
                account_id=account.id,
                login_identifier=row.login_identifier,
                cookie_configured=bool(normalized_cookies),
                password_configured=bool(row.password),
                totp_configured=bool(normalized_totp),
                cookie_count=cookie_count,
                cookie_updated_at=utcnow() if normalized_cookies else None,
                password_updated_at=utcnow() if row.password else None,
                totp_updated_at=utcnow() if normalized_totp else None,
            )
            db.add(config)

            if row.password:
                credential_vault.put_text(account_secret_reference(account.id, "password"), row.password)
            if normalized_totp:
                credential_vault.put_text(account_secret_reference(account.id, "totp"), normalized_totp)
            if normalized_cookies:
                credential_vault.put_text(account_secret_reference(account.id, "cookies"), normalized_cookies)

        db.commit()
    except ResourcePoolImportError as exc:
        db.rollback()
        for account_id in created_account_ids:
            clear_account_secrets(account_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CredentialVaultUnavailable as exc:
        db.rollback()
        for account_id in created_account_ids:
            clear_account_secrets(account_id)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CredentialVaultError as exc:
        db.rollback()
        for account_id in created_account_ids:
            clear_account_secrets(account_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "status": "ok",
        "received": len(rows),
        "created": len(created_account_ids),
        "skipped": skipped,
    }


@router.post("/account-pool/batch/assign-proxy")
def auto_assign_account_proxies(
    payload: AccountBatchProxyAssign,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    accounts = list(
        db.scalars(
            select(Account)
            .where(Account.id.in_(payload.account_ids))
            .order_by(Account.id)
        ).all()
    )
    found = {item.id for item in accounts}
    missing = [item for item in payload.account_ids if item not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"未找到账号：{', '.join(map(str, missing[:10]))}")

    targets = [item for item in accounts if payload.replace_existing or item.proxy_id is None]
    if not targets:
        return {"status": "ok", "assigned": 0, "unchanged": len(accounts)}

    used_proxy_ids = set(
        value
        for value in db.scalars(select(Account.proxy_id).where(Account.proxy_id.is_not(None))).all()
        if value is not None
    )
    candidates = list(
        db.scalars(
            select(ProxyEndpoint)
            .where(
                ProxyEndpoint.enabled.is_(True),
                ProxyEndpoint.status != "error",
                ProxyEndpoint.id.not_in(used_proxy_ids) if used_proxy_ids else True,
            )
            .order_by(ProxyEndpoint.id)
        ).all()
    )
    if len(candidates) < len(targets):
        raise HTTPException(
            status_code=409,
            detail=f"未分配可用 IP 只有 {len(candidates)} 个，但当前需要 {len(targets)} 个。",
        )

    mappings: list[dict[str, int]] = []
    for account, endpoint in zip(targets, candidates, strict=True):
        account.proxy_id = endpoint.id
        mappings.append({"account_id": account.id, "proxy_id": endpoint.id})
    db.commit()
    return {
        "status": "ok",
        "assigned": len(mappings),
        "unchanged": len(accounts) - len(targets),
        "mappings": mappings,
    }


def _prepare_account_row(row: AccountImportRow) -> tuple[AccountImportRow, str | None, str | None, int]:
    normalized_totp = normalize_totp_secret(row.totp_secret) if row.totp_secret else None
    normalized_cookies = None
    cookie_count = 0
    if row.cookie_json:
        normalized_cookies, cookie_count = normalize_cookie_payload(row.cookie_json, row.platform)
    return row, normalized_totp, normalized_cookies, cookie_count


def _resolve_proxy_reference(db: Session, value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.isdigit():
        endpoint = db.get(ProxyEndpoint, int(normalized))
        if endpoint is None:
            raise ResourcePoolImportError(f"指定的 IP #{normalized} 不存在。")
        return endpoint.id

    candidate = normalized
    if candidate.lower().startswith("socks5://"):
        candidate = candidate[9:]
        if "@" in candidate:
            candidate = candidate.rsplit("@", 1)[1]
    if ":" not in candidate:
        raise ResourcePoolImportError(f"无法识别 IP 引用：{value}")
    host, port_text = candidate.rsplit(":", 1)
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ResourcePoolImportError(f"无法识别 IP 引用：{value}") from exc

    endpoints = list(
        db.scalars(
            select(ProxyEndpoint).where(
                ProxyEndpoint.host == host,
                ProxyEndpoint.port == port,
            )
        ).all()
    )
    if not endpoints:
        raise ResourcePoolImportError(f"IP池中不存在 {host}:{port}。")
    if len(endpoints) > 1:
        raise ResourcePoolImportError(f"{host}:{port} 对应多条记录，请在 CSV 中填写 IP池 ID。")
    return endpoints[0].id
