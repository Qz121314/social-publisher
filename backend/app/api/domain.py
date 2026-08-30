from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.channel import Channel
from app.models.content import ContentItem, MediaAsset, PublishJob
from app.models.flow import Flow, FlowRevision
from app.models.publishing import PublishAttempt, PublishPlan
from app.schemas.content import ContentRead
from app.schemas.domain import (
    AssetCreate,
    ChannelRead,
    DomainPublishJobRead,
    FlowRead,
    PublishAttemptRead,
    PublishPlanCreate,
    PublishPlanRead,
)
from app.services.content_store import MediaValidationError, delete_media, media_type_from_mime, save_upload
from app.services.platforms.base import PlatformContent, PlatformMedia, PlatformValidationError
from app.services.platforms.registry import get_platform_adapter
from app.services.publishing_domain import create_publish_plan, get_publish_plan
from app.services.worker import worker_manager, worker_task_to_dict

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
        "phase": 3,
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
    return _get_asset(db, content.id)


@router.post("/assets/upload", response_model=ContentRead, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    platform: str = Form(default="facebook"),
    text: str = Form(default=""),
    files: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
) -> ContentItem:
    normalized_platform = platform.strip().lower()
    try:
        adapter = get_platform_adapter(normalized_platform)
    except PlatformValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    uploads = files or []
    try:
        preview_media = tuple(
            PlatformMedia(
                media_type=media_type_from_mime(upload.content_type),
                path=Path(upload.filename or "media"),
                mime_type=upload.content_type or "application/octet-stream",
                original_name=Path(upload.filename or "media").name,
            )
            for upload in uploads
        )
        adapter.validate_content(PlatformContent(text=text, media=preview_media))
    except (MediaValidationError, PlatformValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved_names: list[str] = []
    content = ContentItem(platform=normalized_platform, text=text, status="draft")
    db.add(content)
    db.flush()
    try:
        for sort_order, upload in enumerate(uploads):
            metadata = await save_upload(upload)
            stored_name = str(metadata["stored_name"])
            saved_names.append(stored_name)
            db.add(
                MediaAsset(
                    content_id=content.id,
                    media_type=str(metadata["media_type"]),
                    original_name=str(metadata["original_name"]),
                    stored_name=stored_name,
                    mime_type=str(metadata["mime_type"]),
                    file_size=int(metadata["file_size"]),
                    sort_order=sort_order,
                )
            )
        db.commit()
    except MediaValidationError as exc:
        db.rollback()
        for stored_name in saved_names:
            delete_media(stored_name)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        for stored_name in saved_names:
            delete_media(stored_name)
        raise
    return _get_asset(db, content.id)


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


@router.post("/publish-plans/{plan_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run_publish_plan(plan_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        plan = get_publish_plan(db, plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    runnable = [job.id for job in plan.jobs if job.status in {"draft", "scheduled", "failed"}]
    if not runnable:
        review_count = sum(1 for job in plan.jobs if job.status == "needs_review")
        detail = "No runnable jobs remain for this publish plan."
        if review_count:
            detail += f" {review_count} job(s) require manual review before retrying."
        raise HTTPException(status_code=409, detail=detail)

    queued: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for job_id in runnable:
        try:
            queued.append(worker_task_to_dict(worker_manager.submit_publish_job(job_id)))
        except ValueError as exc:
            errors.append({"job_id": job_id, "error": str(exc)})

    if not queued:
        raise HTTPException(status_code=409, detail="No publish jobs could be queued.")
    return {
        "plan_id": plan_id,
        "queued": queued,
        "queued_count": len(queued),
        "errors": errors,
    }


@router.get("/domain/publish-jobs", response_model=list[DomainPublishJobRead])
def list_domain_publish_jobs(
    job_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[PublishJob]:
    statement = (
        select(PublishJob)
        .options(selectinload(PublishJob.attempts))
        .where(PublishJob.plan_id.is_not(None))
        .order_by(PublishJob.created_at.desc())
        .limit(limit)
    )
    if job_status:
        statement = statement.where(PublishJob.status == job_status.strip().lower())
    return list(db.scalars(statement).unique().all())


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


def _get_asset(db: Session, content_id: str) -> ContentItem:
    statement = (
        select(ContentItem)
        .options(selectinload(ContentItem.media), selectinload(ContentItem.jobs))
        .where(ContentItem.id == content_id)
    )
    content = db.scalar(statement)
    if content is None:
        raise HTTPException(status_code=404, detail="Asset not found.")
    return content
