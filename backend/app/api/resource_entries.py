from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.account import Account, AccountGroup
from app.models.auth import AccountAuthConfig
from app.models.resource_pool import ProxyEndpoint
from app.schemas.account import AccountRead
from app.schemas.resource_pool import ProxyEndpointRead
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
from app.services.resource_pool import ProxyImportRow

router = APIRouter(tags=["resource-entry"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProxyEndpointCreate(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=1024)
    label: str | None = Field(default=None, max_length=255)

    @field_validator("host", "username", "password", "label")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AccountPoolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    platform: str = Field(default="facebook", min_length=1, max_length=50)
    group_id: int | None = Field(default=None, ge=1)
    proxy_id: int | None = Field(default=None, ge=1)
    login_identifier: str | None = Field(default=None, max_length=512)
    password: str | None = Field(default=None, max_length=4096)
    totp_secret: str | None = Field(default=None, max_length=512)
    cookie_json: str | None = Field(default=None, max_length=5_000_000)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("账号名称不能为空。")
        return normalized

    @field_validator("platform")
    @classmethod
    def normalize_platform(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"facebook", "instagram"}:
            raise ValueError("当前账号池单个录入只支持 Facebook / Instagram。")
        return normalized

    @field_validator("login_identifier", "password", "totp_secret", "cookie_json", "notes")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


@router.post("/proxy-pool", response_model=ProxyEndpointRead, status_code=status.HTTP_201_CREATED)
def create_proxy_endpoint(
    payload: ProxyEndpointCreate,
    db: Session = Depends(get_db),
) -> ProxyEndpointRead:
    if bool(payload.username) != bool(payload.password):
        raise HTTPException(
            status_code=400,
            detail="SOCKS5 用户名和密码必须同时填写，或同时留空。",
        )

    row = ProxyImportRow(
        host=payload.host,
        port=payload.port,
        username=payload.username,
        password=payload.password,
        label=payload.label,
    )
    existing = db.scalar(
        select(ProxyEndpoint).where(ProxyEndpoint.endpoint_key == row.endpoint_key)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="该 SOCKS5 已经存在于 IP池。")

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
    endpoint_id = endpoint.id
    try:
        if row.username:
            credential_vault.put_text(proxy_secret_reference(endpoint_id, "username"), row.username)
        if row.password:
            credential_vault.put_text(proxy_secret_reference(endpoint_id, "password"), row.password)
        db.commit()
    except CredentialVaultUnavailable as exc:
        db.rollback()
        clear_proxy_secrets(endpoint_id)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CredentialVaultError as exc:
        db.rollback()
        clear_proxy_secrets(endpoint_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    db.refresh(endpoint)
    return ProxyEndpointRead.model_validate(endpoint).model_copy(update={"assigned_count": 0})


@router.post("/account-pool", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account_pool_item(
    payload: AccountPoolCreate,
    db: Session = Depends(get_db),
) -> AccountRead:
    if payload.group_id is not None and db.get(AccountGroup, payload.group_id) is None:
        raise HTTPException(status_code=400, detail="账号分组不存在。")
    if payload.proxy_id is not None:
        proxy = db.get(ProxyEndpoint, payload.proxy_id)
        if proxy is None:
            raise HTTPException(status_code=400, detail="IP池中的 SOCKS5 不存在。")
        if not proxy.enabled:
            raise HTTPException(status_code=400, detail="所选 SOCKS5 已停用。")

    if payload.login_identifier:
        duplicate = db.scalar(
            select(Account.id)
            .join(AccountAuthConfig, AccountAuthConfig.account_id == Account.id)
            .where(
                Account.platform == payload.platform,
                AccountAuthConfig.login_identifier == payload.login_identifier,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="相同平台和登录账号已经存在于账号池。")

    try:
        normalized_totp = normalize_totp_secret(payload.totp_secret) if payload.totp_secret else None
        normalized_cookies = None
        cookie_count = 0
        if payload.cookie_json:
            normalized_cookies, cookie_count = normalize_cookie_payload(
                payload.cookie_json,
                payload.platform,
            )
    except (CookieSessionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    account = Account(
        name=payload.name,
        platform=payload.platform,
        ix_profile_id=None,
        group_id=payload.group_id,
        proxy_id=payload.proxy_id,
        status="prepared",
        notes=payload.notes,
    )
    db.add(account)
    db.flush()
    account_id = account.id

    db.add(
        AccountAuthConfig(
            account_id=account_id,
            login_identifier=payload.login_identifier,
            cookie_configured=bool(normalized_cookies),
            password_configured=bool(payload.password),
            totp_configured=bool(normalized_totp),
            cookie_count=cookie_count,
            cookie_updated_at=utcnow() if normalized_cookies else None,
            password_updated_at=utcnow() if payload.password else None,
            totp_updated_at=utcnow() if normalized_totp else None,
        )
    )

    try:
        if payload.password:
            credential_vault.put_text(
                account_secret_reference(account_id, "password"),
                payload.password,
            )
        if normalized_totp:
            credential_vault.put_text(
                account_secret_reference(account_id, "totp"),
                normalized_totp,
            )
        if normalized_cookies:
            credential_vault.put_text(
                account_secret_reference(account_id, "cookies"),
                normalized_cookies,
            )
        db.commit()
    except CredentialVaultUnavailable as exc:
        db.rollback()
        clear_account_secrets(account_id)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CredentialVaultError as exc:
        db.rollback()
        clear_account_secrets(account_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    statement = (
        select(Account)
        .options(
            selectinload(Account.browser_profile),
            selectinload(Account.group),
            selectinload(Account.proxy_endpoint),
        )
        .where(Account.id == account_id)
    )
    created = db.scalar(statement)
    if created is None:
        raise HTTPException(status_code=500, detail="账号已经创建，但读取结果失败。")
    return AccountRead.model_validate(created)
