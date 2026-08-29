from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.accounts import router as accounts_router
from app.database import get_db
from app.models.account import BrowserProfile
from app.schemas.account import BrowserProfileRead
from app.services.ixbrowser import IXBrowserService
from app.services.profile_sync import sync_ix_profiles

router = APIRouter()
router.include_router(accounts_router)


@router.get("/status")
def status() -> dict[str, object]:
    ix = IXBrowserService()
    return {
        "app": "ok",
        "ixbrowser": ix.connection_status(),
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
