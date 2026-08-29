from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import BrowserProfile
from app.models.publish_target import PublishTarget
from app.services.browser_sessions import BrowserSessionError, browser_sessions
from app.services.facebook_composer_probe import probe_facebook_composer_entry
from app.services.ixbrowser import IXBrowserError
from app.services.platforms.base import PlatformPublishError
from app.services.profile_locks import ProfileBusyError, profile_locks

router = APIRouter(tags=["facebook-probe"])


@router.post("/browser-profiles/{profile_id}/facebook-composer/probe")
def probe_facebook_composer(
    profile_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    profile = db.get(BrowserProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="未找到该 iX 环境，请先同步 iX 环境。")

    target = db.scalar(
        select(PublishTarget).where(
            PublishTarget.profile_id == profile_id,
            PublishTarget.platform == "facebook",
        )
    )
    if target is None:
        raise HTTPException(status_code=409, detail="该 iX 尚未设置 Facebook 默认发布主页。")

    owner_id = f"facebook-composer-probe:{uuid4().hex[:12]}"
    opened_here = False
    lock_acquired = False
    try:
        profile_locks.acquire(
            db,
            profile_id=profile_id,
            owner_id=owner_id,
            ttl_seconds=180,
        )
        lock_acquired = True

        session = browser_sessions.open(profile_id)
        opened_here = not bool(session.get("already_open"))
        driver = browser_sessions.get_driver(profile_id)

        result = probe_facebook_composer_entry(
            driver,
            target_type=target.target_type,
            target_id=target.target_id,
            target_name=target.target_name,
            target_url=target.target_url,
        )
        return {"profile_id": profile_id, **result}
    except ProfileBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PlatformPublishError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (IXBrowserError, BrowserSessionError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        if opened_here:
            try:
                browser_sessions.close(profile_id)
            except Exception:
                pass
        if lock_acquired:
            try:
                profile_locks.release(db, profile_id, owner_id)
            except ProfileBusyError:
                pass
