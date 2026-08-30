from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.channel import Channel
from app.models.content import ContentItem, PublishJob
from app.models.flow import Flow, FlowRevision
from app.models.publishing import PublishAttempt, PublishPlan
from app.schemas.content import ContentRead
from app.schemas.domain import (
    AssetCreate,
    ChannelRead,
    FlowRead,
    PublishAttemptRead,
    PublishPlanCreate,
    PublishPlanRead,
)
from app.services.publishing_domain import create_publish_plan, get_publish_plan

router = APIRouter(tags=["v1-domain"])


@router.get("/domain/status")
def domain_status(db: Session = Depends(get_db)) -> dict[str, object]:
    def count(model: type) -> int:
        return int(db.scalar(select(func.count()).select_from(model)) or 0)

    formal_jobs = int(
        db.scalar(
            select(func.count()).select_from(PublishJob).where(PublishJob.plan_id.is_not(None))
        )
        or 0
    )
    legacy_jobs = int(
        db.scalar(
            select(func.count()).select_from(PublishJob).where(PublishJob.plan_id.is_(None))
        )
        or 0
    )
    return {
        "phase": 2,
        "channels": count(Channel),
        "flows": count(Flow),
        "flow_revisions": count(FlowRevision),
        "publish_plans": count(PublishPlan),
        "publish_jobs": {"formal": formal_jobs, "legacy": legacy_jobs},
        "publish_attempts": count(PublishAttempt),
        "compatibility_mode": True,
    }


@router.get("/assets", response_model=list[ContentRead])
def list_assets(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[ContentItem]:
    statement = (
        select(ContentItem)
        .options(selectinload(ContentItem.media), selectinload(ContentItem.jobs))
        .order_by(ContentItem.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(statement).unique().all())


@router.post("/assets", response_model=ContentRead, status_code=status.HTTP_201_CREATED)
def create_asset(payload: AssetCreate, db: Session = Depends(get_db)) -> ContentItem:
    platform = payload.platform.strip().lower()
    if not platform:
        raise HTTPException(status_code=400, detail="platform is required.")
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="text is required for a text asset.")
    content = ContentItem(platform=platform, text=payload.text, status="draft")
    db.add(content)
    db.commit()
    db.refresh(content)
    return content


@router.get("/channels", response_model=list[ChannelRead])
def list_channels(
    platform: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Channel]:
    statement = select(Channel).order_by(Channel.platform, Channel.profile_id, Channel.target_name)
    if platform:
        statement = statement.where(Channel.platform == platform.strip().lower())
    if enabled is not None:
        statement = statement.where(Channel.enabled.is_(enabled))
    return list(db.scalars(statement).all())


@router.get("/flows", response_model=list[FlowRead])
def list_flows(db: Session = Depends(get_db)) -> list[Flow]:
    statement = (
        select(Flow)
        .options(selectinload(Flow.revisions).selectinload(FlowRevision.steps))
        .order_by(Flow.platform, Flow.name)
    )
    return list(db.scalars(statement).unique().all())


@router.get("/publish-plans", response_model=list[PublishPlanRead])
def list_publish_plans(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[PublishPlan]:
    statement = (
        select(PublishPlan)
        .options(selectinload(PublishPlan.jobs).selectinload(PublishJob.attempts))
        .order_by(PublishPlan.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(statement).unique().all())


@router.get("/publish-plans/{plan_id}", response_model=PublishPlanRead)
def read_publish_plan(plan_id: str, db: Session = Depends(get_db)) -> PublishPlan:
    try:
        return get_publish_plan(db, plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/publish-plans",
    response_model=PublishPlanRead,
    status_code=status.HTTP_201_CREATED,
)
def create_plan(payload: PublishPlanCreate, db: Session = Depends(get_db)) -> PublishPlan:
    try:
        return create_publish_plan(
            db,
            content_id=payload.content_id,
            channel_ids=payload.channel_ids,
            publish_mode=payload.publish_mode,
            timezone_name=payload.timezone,
            scheduled_at=payload.scheduled_at,
            interval_seconds=payload.interval_seconds,
            flow_revision_id=payload.flow_revision_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/publish-attempts", response_model=list[PublishAttemptRead])
def list_publish_attempts(
    job_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[PublishAttempt]:
    statement = select(PublishAttempt).order_by(PublishAttempt.created_at.desc()).limit(limit)
    if job_id:
        statement = statement.where(PublishAttempt.job_id == job_id)
    return list(db.scalars(statement).all())
