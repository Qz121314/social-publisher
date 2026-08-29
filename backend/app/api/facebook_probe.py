from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import BrowserProfile
from app.models.publish_target import PublishTarget, PublishTargetConfirmation
from app.schemas.publish_target import PublishTargetConfirmationRead
from app.services.browser_sessions import BrowserSessionError, browser_sessions
from app.services.facebook_composer_probe import confirm_facebook_composer_entry
from app.services.ixbrowser import IXBrowserError
from app.services.platforms.base import PlatformPublishError
from app.services.profile_locks import ProfileBusyError, profile_locks

router = APIRouter(tags=["facebook-target-confirmation"])


@router.get(
    "/facebook-target-confirmations",
    response_model=list[PublishTargetConfirmationRead],
)
def list_facebook_target_confirmations(
    profile_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[PublishTargetConfirmation]:
    statement = select(PublishTargetConfirmation).where(
        PublishTargetConfirmation.platform == "facebook"
    )
    if profile_id is not None:
        statement = statement.where(PublishTargetConfirmation.profile_id == profile_id)
    statement = statement.order_by(
        PublishTargetConfirmation.profile_id,
        PublishTargetConfirmation.target_id,
    )
    return list(db.scalars(statement).all())


@router.post("/browser-profiles/{profile_id}/facebook-composer/confirm")
@router.post("/browser-profiles/{profile_id}/facebook-composer/probe", include_in_schema=False)
def confirm_facebook_composer(
    profile_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Behavior-confirm the composer entry for the configured Facebook target.

    The flow is target-type agnostic. It validates the current actor ID, switches
    to the configured target ID when needed, opens the configured target URL, and
    accepts the entry only when a click produces both a real editor and a Post
    button. It never types content and never clicks Post.
    """

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
        raise HTTPException(status_code=409, detail="该 iX 尚未设置 Facebook 默认发布目标。")

    owner_id = f"facebook-composer-confirm:{uuid4().hex[:12]}"
    opened_here = False
    lock_acquired = False
    try:
        profile_locks.acquire(
            db,
            profile_id=profile_id,
            owner_id=owner_id,
            ttl_seconds=240,
        )
        lock_acquired = True

        session = browser_sessions.open(profile_id)
        opened_here = not bool(session.get("already_open"))
        driver = browser_sessions.get_driver(profile_id)

        result = confirm_facebook_composer_entry(
            driver,
            target_type=target.target_type,
            target_id=target.target_id,
            target_name=target.target_name,
            target_url=target.target_url,
        )

        actor_id = str(result.get("current_actor_id") or "")
        if actor_id != target.target_id:
            raise PlatformPublishError(
                "发帖入口确认完成后，Facebook 当前身份 ID 与目标 ID 不一致，确认结果已丢弃。"
            )

        confirmation = db.scalar(
            select(PublishTargetConfirmation).where(
                PublishTargetConfirmation.profile_id == profile_id,
                PublishTargetConfirmation.platform == "facebook",
                PublishTargetConfirmation.target_id == target.target_id,
            )
        )
        now = datetime.now(timezone.utc)
        signature_json = json.dumps(result.get("entry") or {}, ensure_ascii=False)
        if confirmation is None:
            confirmation = PublishTargetConfirmation(
                profile_id=profile_id,
                platform="facebook",
                target_id=target.target_id,
                actor_id=actor_id,
                entry_signature_json=signature_json,
                confirmed_at=now,
                updated_at=now,
            )
            db.add(confirmation)
        else:
            confirmation.actor_id = actor_id
            confirmation.entry_signature_json = signature_json
            confirmation.confirmed_at = now
            confirmation.updated_at = now
        db.commit()
        db.refresh(confirmation)

        return {
            "profile_id": profile_id,
            "target_id": target.target_id,
            "target_name": target.target_name,
            "confirmed": True,
            "actor_id": actor_id,
            "entry": result.get("entry"),
            "editor_confirmed": result.get("editor_confirmed"),
            "post_button_confirmed": result.get("post_button_confirmed"),
            "confirmed_at": confirmation.confirmed_at.isoformat(),
        }
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
