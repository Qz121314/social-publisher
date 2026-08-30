from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import BrowserProfile
from app.models.publish_target import PublishTarget
from app.schemas.publish_target import PublishTargetRead
from app.services.browser_sessions import BrowserSessionError, browser_sessions
from app.services.domain_bootstrap import disable_channel_for_target, sync_channel_from_target
from app.services.platforms.base import PlatformNeedsReviewError, PlatformPublishError
from app.services.platforms.instagram_composite import InstagramCompositeAdapter
from app.services.platforms.registry import get_platform_adapter
from app.services.profile_locks import ProfileBusyError, profile_locks

router = APIRouter(tags=["instagram-channels"])


@router.post(
    "/browser-profiles/{profile_id}/instagram-channel/capture",
    response_model=PublishTargetRead,
)
def capture_instagram_channel(
    profile_id: int,
    db: Session = Depends(get_db),
) -> PublishTarget:
    """Capture the logged-in Instagram account using stable ds_user_id identity.

    The iX browser must already be open and logged into Instagram. Username is
    display/navigation metadata only; publish authorization uses ds_user_id.
    """

    profile = db.get(BrowserProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="未找到该 iX 环境，请先同步 iX 环境。")

    try:
        profile_locks.assert_unlocked(db, profile_id)
        browser_sessions.probe(profile_id)
        driver = browser_sessions.get_driver(profile_id)
    except ProfileBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BrowserSessionError as exc:
        raise HTTPException(
            status_code=409,
            detail="请先打开该 iX 环境并登录 Instagram，再捕获当前账号 Channel。",
        ) from exc

    adapter = get_platform_adapter("instagram")
    if not isinstance(adapter, InstagramCompositeAdapter):
        raise HTTPException(status_code=503, detail="Instagram Adapter 尚未正确加载。")

    try:
        identity = adapter.discover_identity(driver)
    except PlatformNeedsReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PlatformPublishError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    target = db.scalar(
        select(PublishTarget).where(
            PublishTarget.profile_id == profile_id,
            PublishTarget.platform == "instagram",
        )
    )
    if target is None:
        target = PublishTarget(
            profile_id=profile_id,
            platform="instagram",
            target_type=identity["target_type"],
            target_id=identity["target_id"],
            target_name=identity["target_name"],
            target_url=identity["target_url"],
        )
        db.add(target)
    else:
        target.target_type = identity["target_type"]
        target.target_id = identity["target_id"]
        target.target_name = identity["target_name"]
        target.target_url = identity["target_url"]

    db.flush()
    channel = sync_channel_from_target(db, target)
    channel.health_status = "healthy"
    db.commit()
    db.refresh(target)
    return target


@router.delete(
    "/browser-profiles/{profile_id}/instagram-channel",
    status_code=status.HTTP_204_NO_CONTENT,
)
def clear_instagram_channel(profile_id: int, db: Session = Depends(get_db)) -> Response:
    target = db.scalar(
        select(PublishTarget).where(
            PublishTarget.profile_id == profile_id,
            PublishTarget.platform == "instagram",
        )
    )
    if target is not None:
        disable_channel_for_target(db, target)
        db.delete(target)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
