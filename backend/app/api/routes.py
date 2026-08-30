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
from app.schemas.account import BrowserProfileRead
from app.services.browser_sessions import BrowserSessionError, browser_sessions
from app.services.ixbrowser import IXBrowserError, IXBrowserService
from app.services.profile_locks import ProfileBusyError, profile_locks
from app.services.profile_sync import sync_ix_profiles
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
    profiles = ix.get_profiles()
    return {"items": profiles, "count": len(profiles)}


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


@router.post("/worker/browser-tests/{profile_id}", status_code=http_status.HTTP_202_ACCEPTED)
def queue_browser_test(profile_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    _require_synced_profile(db, profile_id)
    try:
        task = worker_manager.submit_browser_test(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return worker_task_to_dict(task)


@router.get("/worker/tasks")
def worker_tasks(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    return worker_manager.list_tasks(db, limit=limit)


def _require_synced_profile(db: Session, profile_id: int) -> BrowserProfile:
    profile = db.get(BrowserProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Browser profile not found. Sync iXBrowser first.")
    return profile
