from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.content import PublishJob
from app.models.publishing import PublishAttempt
from app.schemas.domain import DomainPublishJobRead
from app.services.attempt_timeline import record_attempt_event
from app.services.scheduler import PublishScheduler, publish_scheduler

router = APIRouter(prefix="/tasks", tags=["tasks"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _job_statement():
    return select(PublishJob).options(
        selectinload(PublishJob.attempts).selectinload(PublishAttempt.events)
    )


def _get_job(db: Session, job_id: str) -> PublishJob:
    job = db.scalar(_job_statement().where(PublishJob.id == job_id))
    if job is None or job.plan_id is None:
        raise HTTPException(status_code=404, detail="Publish job not found.")
    return job


def _review_attempt(job: PublishJob) -> PublishAttempt:
    if job.status != "needs_review":
        raise HTTPException(
            status_code=409,
            detail="Only needs_review jobs can receive a manual review decision.",
        )
    attempts = sorted(job.attempts, key=lambda item: item.attempt_no)
    if not attempts or attempts[-1].status != "needs_review":
        raise HTTPException(
            status_code=409,
            detail="The latest PublishAttempt is not waiting for manual review.",
        )
    return attempts[-1]


def _merge_review_result(
    raw: str | None,
    *,
    decision: str,
    reviewed_at: datetime,
) -> str:
    value: dict[str, object] = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                value = parsed
        except json.JSONDecodeError:
            value = {}
    value["manual_review"] = {
        "decision": decision,
        "reviewed_at": reviewed_at.isoformat(),
    }
    return json.dumps(value, ensure_ascii=False)


def _platform_name(job: PublishJob) -> str:
    if job.platform == "facebook":
        return "Facebook"
    if job.platform == "instagram":
        return "Instagram"
    return job.platform or "平台"


@router.get("/publish-jobs", response_model=list[DomainPublishJobRead])
def list_task_jobs(
    job_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[PublishJob]:
    statement = (
        _job_statement()
        .where(PublishJob.plan_id.is_not(None))
        .order_by(PublishJob.created_at.desc())
        .limit(limit)
    )
    if job_status:
        statement = statement.where(PublishJob.status == job_status.strip().lower())
    return list(db.scalars(statement).unique().all())


@router.get("/publish-jobs/{job_id}", response_model=DomainPublishJobRead)
def read_task_job(job_id: str, db: Session = Depends(get_db)) -> PublishJob:
    return _get_job(db, job_id)


@router.post("/publish-jobs/{job_id}/run", response_model=DomainPublishJobRead)
def run_task_job(job_id: str, db: Session = Depends(get_db)) -> PublishJob:
    """Move one safe formal Job to now; Scheduler remains the only dispatcher."""

    job = _get_job(db, job_id)
    if job.status == "needs_review":
        raise HTTPException(
            status_code=409,
            detail="This job needs manual review before any retry is allowed.",
        )
    if job.status not in {"draft", "scheduled", "failed"}:
        raise HTTPException(
            status_code=409,
            detail=f"Publish job cannot run from status '{job.status}'.",
        )

    job.status = "scheduled"
    job.stage = "scheduled"
    job.scheduled_at = utcnow()
    job.worker_task_id = None
    job.error_message = None
    db.flush()
    if job.plan_id:
        PublishScheduler._refresh_plan_status(db, job.plan_id)
    db.commit()
    publish_scheduler.wake()
    return _get_job(db, job_id)


@router.post(
    "/publish-jobs/{job_id}/review/confirm-published",
    response_model=DomainPublishJobRead,
)
def confirm_job_published(job_id: str, db: Session = Depends(get_db)) -> PublishJob:
    """Resolve an uncertain submission after the user verifies the platform manually."""

    job = _get_job(db, job_id)
    attempt = _review_attempt(job)
    now = utcnow()
    platform_name = _platform_name(job)

    attempt.status = "succeeded"
    attempt.stage = "manual_confirmed_published"
    attempt.error_message = None
    attempt.finished_at = attempt.finished_at or now
    attempt.result_json = _merge_review_result(
        attempt.result_json,
        decision="confirmed_published",
        reviewed_at=now,
    )
    job.status = "succeeded"
    job.stage = "completed"
    job.error_message = None
    db.flush()
    if job.plan_id:
        PublishScheduler._refresh_plan_status(db, job.plan_id)
    attempt_id = attempt.id
    db.commit()

    record_attempt_event(
        attempt_id,
        "manual_confirmed_published",
        f"人工确认：{platform_name} 已成功发布，本任务按成功收口",
        {"decision": "confirmed_published", "platform": job.platform},
        update_stage=False,
    )
    return _get_job(db, job_id)


@router.post(
    "/publish-jobs/{job_id}/review/retry",
    response_model=DomainPublishJobRead,
)
def confirm_not_published_and_retry(
    job_id: str,
    db: Session = Depends(get_db),
) -> PublishJob:
    """Explicitly confirm no post exists, then schedule a safe new attempt."""

    job = _get_job(db, job_id)
    attempt = _review_attempt(job)
    now = utcnow()
    platform_name = _platform_name(job)

    attempt.status = "failed"
    attempt.stage = "manual_confirmed_not_published"
    attempt.error_message = f"人工确认 {platform_name} 未发布，可安全创建下一次执行。"
    attempt.finished_at = attempt.finished_at or now
    attempt.result_json = _merge_review_result(
        attempt.result_json,
        decision="confirmed_not_published_retry",
        reviewed_at=now,
    )
    job.status = "scheduled"
    job.stage = "scheduled"
    job.scheduled_at = now
    job.worker_task_id = None
    job.error_message = None
    db.flush()
    if job.plan_id:
        PublishScheduler._refresh_plan_status(db, job.plan_id)
    attempt_id = attempt.id
    db.commit()

    record_attempt_event(
        attempt_id,
        "manual_confirmed_not_published",
        f"人工确认：{platform_name} 未发布，已允许创建新的安全重试 Attempt",
        {"decision": "confirmed_not_published_retry", "platform": job.platform},
        update_stage=False,
    )
    publish_scheduler.wake()
    return _get_job(db, job_id)
