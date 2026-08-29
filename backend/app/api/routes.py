from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.accounts import router as accounts_router
from app.api.contents import router as contents_router
from app.api.facebook_probe import router as facebook_probe_router
from app.api.publish_targets import router as publish_targets_router
from app.database import get_db
from app.models.account import BrowserProfile
from app.schemas.account import BrowserProfileRead
from app.services.browser_sessions import BrowserSessionError, browser_sessions
from app.services.ixbrowser import IXBrowserError, IXBrowserService
from app.services.profile_locks import ProfileBusyError, profile_locks
from app.services.profile_sync import sync_ix_profiles
from app.services.worker import worker_manager, worker_task_to_dict

router = APIRouter()
router.include_router(accounts_router)
router.include_router(contents_router)
router.include_router(publish_targets_router)
router.include_router(facebook_probe_router)


@router.get("/status")
def status() -> dict[str, object]:
    ix = IXBrowserService()
    return {
        "app": "ok",
        "ixbrowser": ix.connection_status(),
        "browser_sessions": len(browser_sessions.list_sessions()),
        "worker": worker_manager.stats(),
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
    return {"items": sessions, "count": len(sessions)}


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
        return browser_sessions.close(profile_id)
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
