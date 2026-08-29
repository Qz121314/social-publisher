from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import BrowserProfile
from app.models.publish_target import PublishTarget
from app.schemas.publish_target import PublishTargetCaptureRequest, PublishTargetRead
from app.services.browser_sessions import BrowserSessionError, browser_sessions
from app.services.profile_locks import ProfileBusyError, profile_locks

router = APIRouter(tags=["publish-targets"])

_FACEBOOK_RESERVED_PATHS = {
    "",
    "home.php",
    "login",
    "login.php",
    "checkpoint",
    "recover",
    "watch",
    "marketplace",
    "groups",
    "messages",
    "notifications",
    "settings",
    "friends",
    "gaming",
    "events",
}


@router.get("/publish-targets", response_model=list[PublishTargetRead])
def list_publish_targets(
    platform: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[PublishTarget]:
    statement = select(PublishTarget).order_by(PublishTarget.profile_id, PublishTarget.platform)
    if platform:
        statement = statement.where(PublishTarget.platform == platform.strip().lower())
    return list(db.scalars(statement).all())


@router.post(
    "/browser-profiles/{profile_id}/facebook-target/capture",
    response_model=PublishTargetRead,
)
def capture_facebook_target(
    profile_id: int,
    payload: PublishTargetCaptureRequest,
    db: Session = Depends(get_db),
) -> PublishTarget:
    profile = db.get(BrowserProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="未找到该 iX 环境，请先同步 iX 环境。")

    try:
        profile_locks.assert_unlocked(db, profile_id)
        session = browser_sessions.probe(profile_id)
    except ProfileBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BrowserSessionError as exc:
        raise HTTPException(
            status_code=409,
            detail="请先打开该 iX 环境，在浏览器中进入正确的 Facebook 主页后再保存默认目标。",
        ) from exc

    current_url = str(session.get("current_url") or "").strip()
    title = str(session.get("title") or "").strip()
    try:
        target_url, target_id = _normalize_facebook_target(current_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    target_name = _clean_facebook_title(title) or profile.name or target_id
    target = db.scalar(
        select(PublishTarget).where(
            PublishTarget.profile_id == profile_id,
            PublishTarget.platform == "facebook",
        )
    )
    if target is None:
        target = PublishTarget(
            profile_id=profile_id,
            platform="facebook",
            target_type=payload.target_type,
            target_id=target_id,
            target_name=target_name,
            target_url=target_url,
        )
        db.add(target)
    else:
        target.target_type = payload.target_type
        target.target_id = target_id
        target.target_name = target_name
        target.target_url = target_url

    db.commit()
    db.refresh(target)
    return target


@router.delete(
    "/browser-profiles/{profile_id}/facebook-target",
    status_code=status.HTTP_204_NO_CONTENT,
)
def clear_facebook_target(profile_id: int, db: Session = Depends(get_db)) -> Response:
    target = db.scalar(
        select(PublishTarget).where(
            PublishTarget.profile_id == profile_id,
            PublishTarget.platform == "facebook",
        )
    )
    if target is not None:
        db.delete(target)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _normalize_facebook_target(raw_url: str) -> tuple[str, str]:
    if not raw_url:
        raise ValueError("当前浏览器没有可识别的 Facebook 页面地址。")

    parsed = urlparse(raw_url)
    host = parsed.netloc.lower().split(":", 1)[0]
    if host not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
        raise ValueError("当前页面不是 Facebook 页面，请先进入要发布的 Facebook 主页。")

    path = parsed.path.strip("/")
    first = path.split("/", 1)[0].lower() if path else ""
    query = parse_qs(parsed.query)

    if first == "profile.php" and query.get("id"):
        target_id = query["id"][0]
        normalized = urlunparse(("https", "www.facebook.com", "/profile.php", "", urlencode({"id": target_id}), ""))
        return normalized, target_id

    if first in _FACEBOOK_RESERVED_PATHS:
        raise ValueError("当前页面不是个人主页或公共主页，请进入具体主页后再保存。")

    # Facebook page/profile slugs are stable enough for navigation. Drop post,
    # photo and tracking suffixes so publishing always starts from the target root.
    target_id = path.split("/", 1)[0]
    normalized = urlunparse(("https", "www.facebook.com", f"/{target_id}", "", "", ""))
    return normalized, target_id


def _clean_facebook_title(value: str) -> str:
    cleaned = value.strip()
    for suffix in (" | Facebook", " - Facebook", " — Facebook"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
    return "" if cleaned.lower() == "facebook" else cleaned
