from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import BrowserProfile
from app.models.publish_target import PublishTarget, PublishTargetCandidate
from app.schemas.publish_target import (
    FacebookPageScanRead,
    PublishTargetCandidateRead,
    PublishTargetCaptureRequest,
    PublishTargetRead,
)
from app.services.browser_sessions import BrowserSessionError, browser_sessions
from app.services.domain_bootstrap import disable_channel_for_target, sync_channel_from_target
from app.services.facebook_pages import FacebookPageDiscoveryError, discover_managed_facebook_pages
from app.services.ixbrowser import IXBrowserError
from app.services.profile_locks import ProfileBusyError, profile_locks

router = APIRouter(tags=["publish-targets"])

_FACEBOOK_RESERVED_PATHS = {
    "",
    "ad_center",
    "ads",
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
    "latest",
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


@router.get("/facebook-page-candidates", response_model=list[PublishTargetCandidateRead])
def list_facebook_page_candidates(
    profile_id: int | None = Query(default=None),
    include_unavailable: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[PublishTargetCandidate]:
    statement = select(PublishTargetCandidate).where(
        PublishTargetCandidate.platform == "facebook",
        PublishTargetCandidate.target_type.in_(["profile", "page"]),
    )
    if profile_id is not None:
        statement = statement.where(PublishTargetCandidate.profile_id == profile_id)
    if not include_unavailable:
        statement = statement.where(PublishTargetCandidate.is_available.is_(True))
    statement = statement.order_by(
        PublishTargetCandidate.profile_id,
        PublishTargetCandidate.target_type,
        PublishTargetCandidate.target_name,
    )
    return list(db.scalars(statement).all())


@router.post(
    "/browser-profiles/{profile_id}/facebook-pages/scan",
    response_model=FacebookPageScanRead,
)
def scan_facebook_pages(
    profile_id: int,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    profile = db.get(BrowserProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="未找到该 iX 环境，请先同步 iX 环境。")

    owner_id = f"facebook-target-scan:{uuid4().hex[:12]}"
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
        discovered = discover_managed_facebook_pages(driver)

        now = datetime.now(timezone.utc)
        existing = list(
            db.scalars(
                select(PublishTargetCandidate).where(
                    PublishTargetCandidate.profile_id == profile_id,
                    PublishTargetCandidate.platform == "facebook",
                )
            ).all()
        )
        existing_by_id = {item.target_id: item for item in existing}
        for item in existing:
            item.is_available = False

        for discovered_target in discovered:
            candidate = existing_by_id.get(discovered_target["target_id"])
            if candidate is None:
                candidate = PublishTargetCandidate(
                    profile_id=profile_id,
                    platform="facebook",
                    target_type=discovered_target["target_type"],
                    target_id=discovered_target["target_id"],
                    target_name=discovered_target["target_name"],
                    target_url=discovered_target["target_url"],
                    source=discovered_target["source"],
                    is_available=True,
                    last_seen_at=now,
                )
                db.add(candidate)
            else:
                candidate.target_type = discovered_target["target_type"]
                candidate.target_name = discovered_target["target_name"]
                candidate.target_url = discovered_target["target_url"]
                candidate.source = discovered_target["source"]
                candidate.is_available = True
                candidate.last_seen_at = now

        db.commit()
        items = list(
            db.scalars(
                select(PublishTargetCandidate)
                .where(
                    PublishTargetCandidate.profile_id == profile_id,
                    PublishTargetCandidate.platform == "facebook",
                    PublishTargetCandidate.target_type.in_(["profile", "page"]),
                    PublishTargetCandidate.is_available.is_(True),
                )
                .order_by(PublishTargetCandidate.target_type, PublishTargetCandidate.target_name)
            ).all()
        )
        return {"profile_id": profile_id, "count": len(items), "items": items}
    except ProfileBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FacebookPageDiscoveryError as exc:
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


@router.post(
    "/browser-profiles/{profile_id}/facebook-target/select/{candidate_id}",
    response_model=PublishTargetRead,
)
def select_facebook_page_target(
    profile_id: int,
    candidate_id: int,
    db: Session = Depends(get_db),
) -> PublishTarget:
    profile = db.get(BrowserProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="未找到该 iX 环境，请先同步 iX 环境。")

    candidate = db.get(PublishTargetCandidate, candidate_id)
    if (
        candidate is None
        or candidate.profile_id != profile_id
        or candidate.platform != "facebook"
        or candidate.target_type not in {"profile", "page"}
    ):
        raise HTTPException(status_code=404, detail="没有找到这个 Facebook 发布主页候选项。")
    if not candidate.is_available:
        raise HTTPException(status_code=409, detail="这个发布主页已不在最近一次扫描结果中，请重新扫描。")

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
            target_type=candidate.target_type,
            target_id=candidate.target_id,
            target_name=candidate.target_name,
            target_url=candidate.target_url,
        )
        db.add(target)
    else:
        target.target_type = candidate.target_type
        target.target_id = candidate.target_id
        target.target_name = candidate.target_name
        target.target_url = candidate.target_url

    db.flush()
    sync_channel_from_target(db, target)
    db.commit()
    db.refresh(target)
    return target


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

    db.flush()
    sync_channel_from_target(db, target)
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
        disable_channel_for_target(db, target)
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

    target_id = path.split("/", 1)[0]
    normalized = urlunparse(("https", "www.facebook.com", f"/{target_id}", "", "", ""))
    return normalized, target_id


def _clean_facebook_title(value: str) -> str:
    cleaned = value.strip()
    for suffix in (" | Facebook", " - Facebook", " — Facebook"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
    return "" if cleaned.lower() == "facebook" else cleaned
