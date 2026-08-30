from __future__ import annotations

import json
from datetime import datetime
from threading import RLock
from typing import Any

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.content import PublishJob
from app.models.publishing import PublishAttempt, PublishAttemptEvent
from app.services.browser_sessions import browser_sessions
from app.services.platforms.base import emit_platform_progress, platform_progress
from app.services.worker import WorkerManager


_install_lock = RLock()
_installed = False


def record_attempt_event(
    attempt_id: str,
    stage: str,
    message: str,
    details: dict[str, Any] | None = None,
    *,
    created_at: datetime | None = None,
    update_stage: bool = True,
) -> PublishAttemptEvent | None:
    """Append one ordered Timeline event and optionally expose it as current stage."""

    with SessionLocal() as db:
        attempt = db.get(PublishAttempt, attempt_id)
        if attempt is None:
            return None
        job = db.get(PublishJob, attempt.job_id)
        sequence = int(
            db.scalar(
                select(func.max(PublishAttemptEvent.sequence)).where(
                    PublishAttemptEvent.attempt_id == attempt_id
                )
            )
            or 0
        ) + 1
        event = PublishAttemptEvent(
            attempt_id=attempt_id,
            sequence=sequence,
            stage=stage,
            message=message,
            details_json=(json.dumps(details, ensure_ascii=False) if details else None),
        )
        if created_at is not None:
            event.created_at = created_at
        db.add(event)
        if update_stage and attempt.status in {"queued", "running"}:
            attempt.stage = stage
            if job is not None:
                job.stage = stage
        db.commit()
        db.refresh(event)
        return event


def _ensure_queued_event(attempt_id: str) -> None:
    with SessionLocal() as db:
        attempt = db.get(PublishAttempt, attempt_id)
        if attempt is None:
            return
        exists = db.scalar(
            select(PublishAttemptEvent.id).where(
                PublishAttemptEvent.attempt_id == attempt_id,
                PublishAttemptEvent.stage == "queued",
            )
        )
        created_at = attempt.created_at
    if exists is None:
        record_attempt_event(
            attempt_id,
            "queued",
            "任务进入 Worker 队列",
            created_at=created_at,
            update_stage=False,
        )


def _backfill_metrics_and_finalize(attempt_id: str) -> None:
    with SessionLocal() as db:
        attempt = db.get(PublishAttempt, attempt_id)
        if attempt is None:
            return

        result: dict[str, Any] = {}
        if attempt.result_json:
            try:
                parsed = json.loads(attempt.result_json)
                if isinstance(parsed, dict):
                    result = parsed
            except json.JSONDecodeError:
                result = {}

        if attempt.media_ms is None and result.get("media_duration_ms") is not None:
            try:
                attempt.media_ms = max(0, int(result["media_duration_ms"]))
            except (TypeError, ValueError):
                pass
        if attempt.verification_ms is None and result.get("verification_duration_ms") is not None:
            try:
                attempt.verification_ms = max(0, int(result["verification_duration_ms"]))
            except (TypeError, ValueError):
                pass

        status = attempt.status
        error_message = attempt.error_message
        db.commit()

    if status == "succeeded":
        record_attempt_event(
            attempt_id,
            "completed",
            "发布任务执行成功",
            update_stage=False,
        )
    elif status == "needs_review":
        record_attempt_event(
            attempt_id,
            "needs_review",
            "系统无法安全确认最终发布结果，需要人工确认",
            {"reason": error_message} if error_message else None,
            update_stage=False,
        )
    elif status == "failed":
        record_attempt_event(
            attempt_id,
            "failed",
            "发布任务执行失败",
            {"reason": error_message} if error_message else None,
            update_stage=False,
        )
    elif status == "interrupted":
        record_attempt_event(
            attempt_id,
            "interrupted",
            "Backend 重启导致本次执行中断",
            update_stage=False,
        )


def install_phase6_worker_hooks() -> None:
    """Install non-invasive Timeline hooks around the existing verified Worker.

    Phase 6 observes the existing worker/browser/adapter pipeline rather than
    replacing its safety behavior. ContextVar-backed platform progress keeps
    concurrent Worker threads isolated.
    """

    global _installed
    with _install_lock:
        if _installed:
            return

        original_run_publish_job = WorkerManager._run_publish_job
        original_browser_open = browser_sessions.open

        def run_publish_job_with_timeline(
            self: WorkerManager,
            task_id: str,
            job_id: str,
            attempt_id: str,
        ) -> None:
            _ensure_queued_event(attempt_id)

            def progress_handler(
                stage: str,
                message: str,
                details: dict[str, Any] | None,
            ) -> None:
                record_attempt_event(attempt_id, stage, message, details)

            with platform_progress(progress_handler):
                try:
                    original_run_publish_job(self, task_id, job_id, attempt_id)
                finally:
                    _backfill_metrics_and_finalize(attempt_id)

        def browser_open_with_timeline(profile_id: int, *args: Any, **kwargs: Any):
            emit_platform_progress(
                "opening_browser",
                f"启动或复用 iXBrowser 环境 #{profile_id}",
                {"profile_id": profile_id},
            )
            result = original_browser_open(profile_id, *args, **kwargs)
            emit_platform_progress(
                "opening_browser",
                "Selenium 已连接到 iXBrowser",
                {
                    "profile_id": profile_id,
                    "reused_session": bool(result.get("already_open")),
                },
            )
            return result

        WorkerManager._run_publish_job = run_publish_job_with_timeline  # type: ignore[method-assign]
        browser_sessions.open = browser_open_with_timeline  # type: ignore[method-assign]
        _installed = True
