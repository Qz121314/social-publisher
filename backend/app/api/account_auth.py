from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Account
from app.models.auth import AccountAuthConfig
from app.schemas.auth import AccountAuthRead, AccountAuthUpdate
from app.services.cookie_session import CookieSessionError, normalize_cookie_payload
from app.services.credential_vault import (
    CredentialVaultError,
    CredentialVaultUnavailable,
    account_secret_reference,
    credential_vault,
)
from app.services.login_engine import LoginCapabilities, build_login_plan, normalize_totp_secret

router = APIRouter(prefix="/auth", tags=["account-auth"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="未找到该社交账号。")
    return account


def _get_or_create_config(db: Session, account_id: int) -> AccountAuthConfig:
    config = db.get(AccountAuthConfig, account_id)
    if config is None:
        config = AccountAuthConfig(account_id=account_id)
        db.add(config)
        db.flush()
    return config


def _to_read(config: AccountAuthConfig) -> AccountAuthRead:
    capabilities = LoginCapabilities(
        cookie_configured=config.cookie_configured,
        password_configured=config.password_configured,
        totp_configured=config.totp_configured,
        allow_cookie_restore=config.allow_cookie_restore,
        allow_password_login=config.allow_password_login,
        allow_totp=config.allow_totp,
    )
    vault_status = credential_vault.status()
    return AccountAuthRead(
        account_id=config.account_id,
        login_identifier=config.login_identifier,
        allow_cookie_restore=config.allow_cookie_restore,
        allow_password_login=config.allow_password_login,
        allow_totp=config.allow_totp,
        password_configured=config.password_configured,
        totp_configured=config.totp_configured,
        cookie_configured=config.cookie_configured,
        cookie_count=config.cookie_count,
        password_updated_at=config.password_updated_at,
        totp_updated_at=config.totp_updated_at,
        cookie_updated_at=config.cookie_updated_at,
        updated_at=config.updated_at,
        vault_supported=bool(vault_status["supported"]),
        vault_backend=str(vault_status["backend"]),
        login_plan=list(build_login_plan(capabilities).steps),
    )


@router.get("/{account_id}", response_model=AccountAuthRead)
def get_account_auth(account_id: int, db: Session = Depends(get_db)) -> AccountAuthRead:
    _require_account(db, account_id)
    config = _get_or_create_config(db, account_id)
    db.commit()
    db.refresh(config)
    return _to_read(config)


@router.patch("/{account_id}", response_model=AccountAuthRead)
def update_account_auth(
    account_id: int,
    payload: AccountAuthUpdate,
    db: Session = Depends(get_db),
) -> AccountAuthRead:
    account = _require_account(db, account_id)
    config = _get_or_create_config(db, account_id)
    now = utcnow()

    if payload.login_identifier is not None:
        identifier = payload.login_identifier.strip()
        config.login_identifier = identifier or None
    if payload.allow_cookie_restore is not None:
        config.allow_cookie_restore = payload.allow_cookie_restore
    if payload.allow_password_login is not None:
        config.allow_password_login = payload.allow_password_login
    if payload.allow_totp is not None:
        config.allow_totp = payload.allow_totp

    try:
        if payload.clear_password:
            credential_vault.delete(account_secret_reference(account_id, "password"))
            config.password_configured = False
            config.password_updated_at = None
        if payload.clear_totp:
            credential_vault.delete(account_secret_reference(account_id, "totp"))
            config.totp_configured = False
            config.totp_updated_at = None
        if payload.clear_cookies:
            credential_vault.delete(account_secret_reference(account_id, "cookies"))
            config.cookie_configured = False
            config.cookie_count = 0
            config.cookie_updated_at = None

        if payload.password is not None:
            credential_vault.put_text(
                account_secret_reference(account_id, "password"),
                payload.password,
            )
            config.password_configured = True
            config.password_updated_at = now

        if payload.totp_secret is not None:
            normalized_totp = normalize_totp_secret(payload.totp_secret)
            credential_vault.put_text(
                account_secret_reference(account_id, "totp"),
                normalized_totp,
            )
            config.totp_configured = True
            config.totp_updated_at = now

        if payload.cookie_json is not None:
            normalized_cookies, cookie_count = normalize_cookie_payload(
                payload.cookie_json,
                account.platform,
            )
            credential_vault.put_text(
                account_secret_reference(account_id, "cookies"),
                normalized_cookies,
            )
            config.cookie_configured = True
            config.cookie_count = cookie_count
            config.cookie_updated_at = now

    except CookieSessionError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CredentialVaultUnavailable as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CredentialVaultError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    db.commit()
    db.refresh(config)
    return _to_read(config)
