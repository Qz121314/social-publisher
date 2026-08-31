from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.resource_pools import _prepare_account_row, _resolve_proxy_reference
from app.database import get_db
from app.models.account import Account, AccountGroup
from app.models.auth import AccountAuthConfig
from app.schemas.resource_pool import (
    AccountImportPreview,
    AccountImportPreviewRow,
    AccountPoolImportText,
)
from app.services.cookie_session import CookieSessionError
from app.services.resource_pool import ResourcePoolImportError, parse_account_import_csv

router = APIRouter(tags=["account-import-preview"])


@router.post("/account-pool/import/preview", response_model=AccountImportPreview)
def preview_account_pool_import(
    payload: AccountPoolImportText,
    db: Session = Depends(get_db),
) -> AccountImportPreview:
    """Validate account CSV without persisting rows or returning secrets."""

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
    existing_groups = {item.name.lower() for item in db.scalars(select(AccountGroup)).all()}

    preview_rows: list[AccountImportPreviewRow] = []
    groups_to_create: list[str] = []
    pending_group_names: set[str] = set()
    seen_identifiers: set[tuple[str, str]] = set()
    creatable = 0
    skipped = 0

    try:
        for row, normalized_totp, normalized_cookies, _cookie_count in prepared:
            proxy_id = _resolve_proxy_reference(db, row.proxy)
            identity_key = (
                (row.platform, row.login_identifier.lower())
                if row.login_identifier
                else None
            )
            duplicate = bool(
                identity_key
                and (identity_key in existing_identifiers or identity_key in seen_identifiers)
            )
            if identity_key and not duplicate:
                seen_identifiers.add(identity_key)

            action = "skip" if duplicate else "create"
            reason = "相同平台和登录账号已存在，导入时会跳过。" if duplicate else None
            if duplicate:
                skipped += 1
            else:
                creatable += 1
                if row.group_name:
                    group_key = row.group_name.lower()
                    if group_key not in existing_groups and group_key not in pending_group_names:
                        pending_group_names.add(group_key)
                        groups_to_create.append(row.group_name)

            preview_rows.append(
                AccountImportPreviewRow(
                    name=row.name,
                    platform=row.platform,
                    group_name=row.group_name,
                    proxy_id=proxy_id,
                    login_configured=bool(row.login_identifier),
                    password_configured=bool(row.password),
                    totp_configured=bool(normalized_totp),
                    cookie_configured=bool(normalized_cookies),
                    action=action,
                    reason=reason,
                )
            )
    except ResourcePoolImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return AccountImportPreview(
        received=len(rows),
        creatable=creatable,
        skipped=skipped,
        groups_to_create=groups_to_create,
        rows=preview_rows,
    )
