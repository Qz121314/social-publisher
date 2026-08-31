from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.accounts import router as accounts_router
from app.api.contents import router as contents_router
from app.api.domain import router as domain_router
from app.api.facebook_flow_config import router as facebook_flow_config_router
from app.api.facebook_probe import router as facebook_probe_router
from app.api.instagram_channels import router as instagram_channels_router
from app.api.publish_targets import router as publish_targets_router
from app.database import get_db
from app.models.account import BrowserProfile
from app.schemas.account import AccountProxyCreate, BrowserProfileRead
from app.services.browser_sessions import BrowserSessionError, browser_sessions
from app.services.ixbrowser import IXBrowserError, IXBrowserService
from app.services.profile_locks import ProfileBusyError, profile_locks
from app.services.profile_sync import sanitize_profile_payload, sync_ix_profiles
from app.services.runtime_settings import (
    MAX_WARM_SESSION_TTL_SECONDS,
    get_warm_session_ttl_seconds,
    set_warm_session_ttl_seconds,
)
from app.services.scheduler import publish_scheduler
from app.services.worker import worker_manager, worker_task_to_dict

router = APIRouter()
router.include_router(accounts_router)
router.include_router(contents_router)
router.include_router(domain_router)
router.include_router(publish_targets_router)
router.include_router(facebook_probe_router)
router.include_router(facebook_flow_config_router)
router.include_router(instagram_channels_router)


class RuntimeSettingsUpdate(BaseModel):
    warm_session_ttl_seconds: int = Field(
        ge=0,
        le=MAX_WARM_SESSION_TTL_SECONDS,
    )


class IXBrowserProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    site_url: str = Field(default="chrome://newtab", min_length=1, max_length=2048)
    group_id: int | None = Field(default=None, ge=1)
    proxy: AccountProxyCreate = Field(default_factory=AccountProxyCreate)
    open_after_create: bool = True


class IXBrowserProxyUpdate(BaseModel):
    enabled: bool = True
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=1024)


@router.get("/status")
def status() -> dict[str, object]:
    ix = IXBrowserService()
    sessions = browser_sessions.list_sessions()
    return {
        "app": "ok",
        "ixbrowser": ix.connection_status(),
        "browser_sessions": len(sessions),
        "browser_pool": {
            **browser_sessions.stats(),
            "warm_session_ttl_seconds": get_warm_session_ttl_seconds(),
        },
        "worker": worker_manager.stats(),
        "scheduler": publish_scheduler.stats(),
    }


@router.get("/settings/runtime")
def runtime_settings(db: Session = Depends(get_db)) -> dict[str, object]:
    return {
        "warm_session_ttl_seconds": get_warm_session_ttl_seconds(db),
        "worker_max_workers": worker_manager.max_workers,
        "scheduler_poll_interval_seconds": publish_scheduler.poll_interval_seconds,
        "scheduler_batch_size": publish_scheduler.batch_size,
    }


@router.put("/settings/runtime")
def update_runtime_settings(
    payload: RuntimeSettingsUpdate,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    ttl = set_warm_session_ttl_seconds(payload.warm_session_ttl_seconds, db)
    return {
        "warm_session_ttl_seconds": ttl,
        "worker_max_workers": worker_manager.max_workers,
        "scheduler_poll_interval_seconds": publish_scheduler.poll_interval_seconds,
        "scheduler_batch_size": publish_scheduler.batch_size,
    }


@router.get("/ixbrowser/profiles")
def ixbrowser_profiles() -> dict[str, object]:
    ix = IXBrowserService()
    profiles = [sanitize_profile_payload(item) for item in ix.get_profiles()]
    return {"items": profiles, "count": len(profiles)}


@router.post(
    "/ixbrowser/profiles",
    status_code=http_status.HTTP_201_CREATED,
)
def create_ixbrowser_profile(
    payload: IXBrowserProfileCreate,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Create a persistent iX Profile and optionally open its real window.

    Creation and opening are intentionally reported separately. Once iX says
    the Profile was created we never report the whole request as a create
    failure merely because the follow-up open/attach step failed.
    """

    ix = IXBrowserService()
    proxy = payload.proxy
    try:
        created = ix.create_profile(
            name=payload.name,
            site_url=payload.site_url,
            group_id=payload.group_id,
            proxy_type=proxy.proxy_type if proxy.enabled else None,
            proxy_ip=proxy.host if proxy.enabled else None,
            proxy_port=proxy.port if proxy.enabled else None,
            proxy_user=proxy.username if proxy.enabled else None,
            proxy_password=proxy.password if proxy.enabled else None,
        )
    except IXBrowserError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    profile_id = created.get("profile_id")
    sync_error: str | None = None
    try:
        sync_ix_profiles(db)
    except (RuntimeError, IXBrowserError) as exc:
        sync_error = str(exc)

    if profile_id is None:
        try:
            match = ix.find_profile_by_name(payload.name)
            if match is not None:
                profile_id = int(match["profile_id"])
        except (IXBrowserError, KeyError, TypeError, ValueError):
            profile_id = None

    local_profile = db.get(BrowserProfile, profile_id) if isinstance(profile_id, int) else None
    if local_profile is None and isinstance(profile_id, int):
        try:
            remote = ix.get_profile(profile_id)
            if remote is not None:
                local_profile = BrowserProfile(
                    profile_id=profile_id,
                    name=str(remote.get("name") or payload.name),
                    group_id=_optional_int(remote.get("group_id")),
                    group_name=_optional_str(remote.get("group_name")),
                    raw_json="{}",
                    is_available=True,
                )
                db.merge(local_profile)
                db.commit()
                local_profile = db.get(BrowserProfile, profile_id)
        except IXBrowserError as exc:
            sync_error = sync_error or str(exc)

    opened = False
    open_error: str | None = None
    if payload.open_after_create and isinstance(profile_id, int):
        try:
            result = browser_sessions.open(profile_id)
            opened = bool(result.get("alive"))
        except (IXBrowserError, BrowserSessionError) as exc:
            open_error = str(exc)

    return {
        "status": "created",
        "profile_id": profile_id,
        "name": created["name"],
        "site_url": created["site_url"],
        "proxy_configured": bool(created.get("proxy_configured")),
        "synced": local_profile is not None,
        "opened": opened,
        "sync_error": sync_error,
        "open_error": open_error,
    }


@router.post("/ixbrowser/sync")
def ixbrowser_sync(db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        result = sync_ix_profiles(db)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok", **result}


@router.get("/browser-profiles", response_model=list[BrowserProfileRead])
def browser_profiles(db: Session = Depends(get_db)) -> list[BrowserProfile]:
    statement = select(BrowserProfile).order_by(BrowserProfile.name, BrowserProfile.profile_id)
    return list(db.scalars(statement).all())


@router.put("/browser-profiles/{profile_id}/proxy", response_model=BrowserProfileRead)
def update_browser_profile_proxy(
    profile_id: int,
    payload: IXBrowserProxyUpdate,
    db: Session = Depends(get_db),
) -> BrowserProfile:
    profile = _require_synced_profile(db, profile_id)
    try:
        profile_locks.assert_unlocked(db, profile_id)
    except ProfileBusyError as exc:
        raise HTTPException(status_code=409, detail="该环境正在执行任务，不能修改网络配置。") from exc

    active_session = next(
        (
            item
            for item in browser_sessions.list_sessions()
            if item.get("profile_id") == profile_id and item.get("alive")
        ),
        None,
    )
    if active_session is not None:
        raise HTTPException(status_code=409, detail="请先关闭该 iX 环境，再修改 SOCKS5。")

    ix = IXBrowserService()
    try:
        if payload.enabled:
            host = (payload.host or "").strip()
            if not host or payload.port is None:
                raise HTTPException(status_code=400, detail="SOCKS5 需要同时填写 Host 和 Port。")
            ix.update_profile_socks5_proxy(
                profile_id,
                proxy_ip=host,
                proxy_port=payload.port,
                proxy_user=payload.username,
                proxy_password=payload.password,
            )
        else:
            ix.clear_profile_proxy(profile_id)
        sync_ix_profiles(db)
    except IXBrowserError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return db.get(BrowserProfile, profile_id) or profile


@router.get("/browser-sessions")
def list_browser_sessions() -> dict[str, object]:
    sessions = browser_sessions.list_sessions()
    return {"items": sessions, "count": len(sessions), "pool": browser_sessions.stats()}


@router.post("/browser-profiles/{profile_id}/open")
def open_browser_profile(
    profile_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_synced_profile(db, profile_id)
    try:
        profile_locks.assert_unlocked(db, profile_id)
        return browser_sessions.open(profile_id)
    except ProfileBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (IXBrowserError, BrowserSessionError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/browser-profiles/{profile_id}/probe")
def probe_browser_profile(
    profile_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_synced_profile(db, profile_id)
    try:
        profile_locks.assert_unlocked(db, profile_id)
        return browser_sessions.probe(profile_id)
    except ProfileBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BrowserSessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/browser-profiles/{profile_id}/close")
def close_browser_profile(
    profile_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_synced_profile(db, profile_id)
    try:
        profile_locks.assert_unlocked(db, profile_id)
        return browser_sessions.close(profile_id, force=True)
    except ProfileBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IXBrowserError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/profile-locks")
def list_profile_locks(db: Session = Depends(get_db)) -> dict[str, object]:
    items = profile_locks.list_active(db)
    return {
        "items": [
            {
                "profile_id": item.profile_id,
                "owner_id": item.owner_id,
                "task_id": item.task_id,
                "acquired_at": item.acquired_at.isoformat(),
                "heartbeat_at": item.heartbeat_at.isoformat(),
                "expires_at": item.expires_at.isoformat(),
            }
            for item in items
        ],
        "count": len(items),
    }


@router.post("/profile-locks/cleanup")
def cleanup_profile_locks(db: Session = Depends(get_db)) -> dict[str, int]:
    return {"removed": profile_locks.cleanup_expired(db)}


@router.get("/worker/tasks")
def list_worker_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    tasks = worker_manager.list_tasks(db, limit=limit)
    return {
        "items": [worker_task_to_dict(task) for task in tasks],
        "count": len(tasks),
        "worker": worker_manager.stats(),
    }


@router.get("/worker/tasks/{task_id}")
def get_worker_task(task_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    task = worker_manager.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Worker task not found.")
    return worker_task_to_dict(task)


@router.post(
    "/worker/test/{profile_id}",
    status_code=http_status.HTTP_202_ACCEPTED,
)
def run_worker_test(
    profile_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_synced_profile(db, profile_id)
    task = worker_manager.submit_browser_test(profile_id)
    return worker_task_to_dict(task)


def _require_synced_profile(db: Session, profile_id: int) -> BrowserProfile:
    profile = db.get(BrowserProfile, profile_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="iX profile is not in the local database. Sync profiles first.",
        )
    return profile


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
