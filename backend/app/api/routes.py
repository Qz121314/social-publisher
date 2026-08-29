from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.accounts import router as accounts_router
from app.database import get_db
from app.models.account import BrowserProfile
from app.schemas.account import BrowserProfileRead
from app.services.browser_sessions import BrowserSessionError, browser_sessions
from app.services.ixbrowser import IXBrowserError, IXBrowserService
from app.services.profile_sync import sync_ix_profiles

router = APIRouter()
router.include_router(accounts_router)


@router.get("/status")
def status() -> dict[str, object]:
    ix = IXBrowserService()
    return {
        "app": "ok",
        "ixbrowser": ix.connection_status(),
        "browser_sessions": len(browser_sessions.list_sessions()),
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
        return browser_sessions.open(profile_id)
    except (IXBrowserError, BrowserSessionError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/browser-profiles/{profile_id}/probe")
def probe_browser_profile(
    profile_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_synced_profile(db, profile_id)
    try:
        return browser_sessions.probe(profile_id)
    except BrowserSessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/browser-profiles/{profile_id}/close")
def close_browser_profile(
    profile_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_synced_profile(db, profile_id)
    try:
        return browser_sessions.close(profile_id)
    except IXBrowserError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _require_synced_profile(db: Session, profile_id: int) -> BrowserProfile:
    profile = db.get(BrowserProfile, profile_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="iX profile is not in the local database. Sync profiles first.",
        )
    return profile
