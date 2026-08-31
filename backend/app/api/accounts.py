import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.account_auth import router as account_auth_router
from app.api.account_groups import router as account_groups_router
from app.api.account_login import router as account_login_router
from app.database import get_db
from app.models.account import Account, AccountGroup, BrowserProfile
from app.models.resource_pool import ProxyEndpoint
from app.schemas.account import (
    AccountBatchMove,
    AccountCreate,
    AccountOnboardCreate,
    AccountOnboardRead,
    AccountRead,
    AccountUpdate,
)
from app.services.browser_sessions import BrowserSessionError, browser_sessions
from app.services.credential_vault import clear_account_secrets
from app.services.ixbrowser import IXBrowserError, IXBrowserService
from app.services.profile_sync import sanitize_profile_payload, sync_ix_profiles

router = APIRouter(prefix="/accounts", tags=["accounts"])
router.include_router(account_groups_router)
router.include_router(account_auth_router)
router.include_router(account_login_router)


@router.get("", response_model=list[AccountRead])
def list_accounts(
    platform: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    group_id: int | None = Query(default=None),
    ungrouped: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[Account]:
    statement = (
        select(Account)
        .options(
            selectinload(Account.browser_profile),
            selectinload(Account.group),
            selectinload(Account.proxy_endpoint),
        )
        .order_by(Account.created_at.desc())
    )
    if platform:
        statement = statement.where(Account.platform == platform.strip().lower())
    if enabled is not None:
        statement = statement.where(Account.enabled == enabled)
    if group_id is not None:
        statement = statement.where(Account.group_id == group_id)
    elif ungrouped:
        statement = statement.where(Account.group_id.is_(None))
    return list(db.scalars(statement).all())


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)) -> Account:
    if payload.ix_profile_id is not None:
        _require_profile(db, payload.ix_profile_id)
    _require_group(db, payload.group_id)
    if payload.proxy_id is not None:
        _require_proxy(db, payload.proxy_id)

    account = Account(**payload.model_dump())
    db.add(account)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该 iX 环境已经绑定了同平台账号。",
        ) from exc

    return _get_account_or_404(db, account.id)


@router.post(
    "/onboard",
    response_model=AccountOnboardRead,
    status_code=status.HTTP_201_CREATED,
)
def onboard_account(
    payload: AccountOnboardCreate,
    db: Session = Depends(get_db),
) -> AccountOnboardRead:
    """Compatibility path for manually creating one account + iX environment.

    Phase 10 primary onboarding is now resource-pool preparation followed by a
    batch login task. This endpoint remains available for one-off/manual imports.
    """

    _require_group(db, payload.group_id)
    profile_created = payload.environment_mode == "new"
    open_error: str | None = None
    opened = False

    if payload.environment_mode == "existing":
        profile_id = int(payload.ix_profile_id or 0)
        _require_profile(db, profile_id)
    else:
        ix = IXBrowserService()
        proxy = payload.proxy
        profile_name = (payload.profile_name or payload.name).strip()
        try:
            created = ix.create_profile(
                name=profile_name,
                site_url=_platform_start_url(payload.platform),
                proxy_type=proxy.proxy_type if proxy.enabled else None,
                proxy_ip=proxy.host if proxy.enabled else None,
                proxy_port=proxy.port if proxy.enabled else None,
                proxy_user=proxy.username if proxy.enabled else None,
                proxy_password=proxy.password if proxy.enabled else None,
            )
        except IXBrowserError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        profile_id_value = created.get("profile_id")
        profile_id = int(profile_id_value) if isinstance(profile_id_value, int) else 0
        if profile_id <= 0:
            raise HTTPException(
                status_code=503,
                detail=(
                    "iXBrowser 已创建环境，但未返回可绑定的 Profile ID。"
                    "请先同步 iX 环境，再使用“绑定已有环境”；不要重复点击创建。"
                ),
            )
        _sync_or_materialize_profile(db, ix, profile_id, profile_name)

    account = Account(
        name=payload.name,
        platform=payload.platform,
        ix_profile_id=profile_id,
        group_id=payload.group_id,
        status="needs_login",
    )
    db.add(account)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该 iX 环境已经绑定了同平台账号。",
        ) from exc

    if payload.open_after_create:
        try:
            result = browser_sessions.open(profile_id)
            opened = bool(result.get("alive"))
        except (IXBrowserError, BrowserSessionError) as exc:
            open_error = str(exc)

    account_record = _get_account_or_404(db, account.id)
    return AccountOnboardRead(
        account=AccountRead.model_validate(account_record),
        profile_created=profile_created,
        opened=opened,
        open_error=open_error,
    )


@router.post("/batch/group")
def move_accounts_to_group(
    payload: AccountBatchMove,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_group(db, payload.group_id)

    requested_ids = list(dict.fromkeys(payload.account_ids))
    accounts = list(db.scalars(select(Account).where(Account.id.in_(requested_ids))).all())
    found_ids = {account.id for account in accounts}
    missing = [account_id for account_id in requested_ids if account_id not in found_ids]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"未找到账号：{', '.join(str(item) for item in missing[:10])}",
        )

    for account in accounts:
        account.group_id = payload.group_id
    db.commit()
    return {
        "status": "ok",
        "moved": len(accounts),
        "group_id": payload.group_id,
    }


@router.patch("/{account_id}", response_model=AccountRead)
def update_account(
    account_id: int,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="未找到该社交账号。")

    changes = payload.model_dump(exclude_unset=True)
    if "ix_profile_id" in changes and changes["ix_profile_id"] is not None:
        _require_profile(db, changes["ix_profile_id"])
    if "group_id" in changes:
        _require_group(db, changes["group_id"])
    if "proxy_id" in changes and changes["proxy_id"] is not None:
        _require_proxy(db, changes["proxy_id"])

    for key, value in changes.items():
        setattr(account, key, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该 iX 环境已经绑定了同平台账号。",
        ) from exc

    return _get_account_or_404(db, account_id)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, db: Session = Depends(get_db)) -> Response:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="未找到该社交账号。")
    clear_account_secrets(account_id)
    db.delete(account)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _platform_start_url(platform: str) -> str:
    return {
        "facebook": "https://www.facebook.com/",
        "instagram": "https://www.instagram.com/",
    }.get(platform, "chrome://newtab")


def _sync_or_materialize_profile(
    db: Session,
    ix: IXBrowserService,
    profile_id: int,
    fallback_name: str,
) -> BrowserProfile:
    try:
        sync_ix_profiles(db)
    except (RuntimeError, IXBrowserError):
        pass

    profile = db.get(BrowserProfile, profile_id)
    if profile is not None:
        return profile

    try:
        remote = ix.get_profile(profile_id)
    except IXBrowserError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"iX #{profile_id} 已创建，但本地同步失败：{exc}. "
                "请同步 iX 环境后再绑定已有环境。"
            ),
        ) from exc

    if remote is None:
        raise HTTPException(
            status_code=503,
            detail=f"iX #{profile_id} 已创建，但无法读取其环境信息。",
        )

    profile = BrowserProfile(
        profile_id=profile_id,
        name=str(remote.get("name") or fallback_name),
        group_id=_optional_int(remote.get("group_id")),
        group_name=_optional_str(remote.get("group_name")),
        raw_json=json.dumps(
            sanitize_profile_payload(remote),
            ensure_ascii=False,
            default=str,
        ),
        is_available=True,
    )
    db.merge(profile)
    db.commit()
    return db.get(BrowserProfile, profile_id) or profile


def _require_profile(db: Session, profile_id: int) -> BrowserProfile:
    profile = db.get(BrowserProfile, profile_id)
    if profile is None:
        raise HTTPException(
            status_code=400,
            detail="该 iX 环境尚未同步，请先同步 iXBrowser 环境。",
        )
    return profile


def _require_group(db: Session, group_id: int | None) -> AccountGroup | None:
    if group_id is None:
        return None
    group = db.get(AccountGroup, group_id)
    if group is None:
        raise HTTPException(status_code=400, detail="账号分组不存在。")
    return group


def _require_proxy(db: Session, proxy_id: int) -> ProxyEndpoint:
    endpoint = db.get(ProxyEndpoint, proxy_id)
    if endpoint is None:
        raise HTTPException(status_code=400, detail="IP池中的 SOCKS5 不存在。")
    return endpoint


def _get_account_or_404(db: Session, account_id: int) -> Account:
    statement = (
        select(Account)
        .options(
            selectinload(Account.browser_profile),
            selectinload(Account.group),
            selectinload(Account.proxy_endpoint),
        )
        .where(Account.id == account_id)
    )
    account = db.scalar(statement)
    if account is None:
        raise HTTPException(status_code=404, detail="未找到该社交账号。")
    return account


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
