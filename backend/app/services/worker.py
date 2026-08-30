from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.channel import Channel
from app.models.content import ContentItem, MediaAsset, PublishJob
from app.models.execution import WorkerTask, utcnow
from app.models.publishing import PublishAttempt, PublishPlan
from app.models.publish_target import PublishTarget
from app.services.browser_sessions import browser_sessions
from app.services.content_store import get_media_path
from app.services.platforms.base import (
    PlatformContent,
    PlatformMedia,
    PlatformNeedsReviewError,
    PlatformPublishError,
    PlatformValidationError,
)
from app.services.platforms.registry import get_platform_adapter
from app.services.profile_locks import ProfileBusyError, profile_locks


class WorkerManager:
    """Bounded platform-agnostic worker pool for browser automation jobs."""

    def __init__(self, max_workers: int = 3) -> None:
        self.max_workers = max_workers
        self.instance_id = f"worker-{uuid4().hex[:12]}"
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="social-publisher-worker",
        )
        self._futures: dict[str, Future[Any]] = {}
        self._lock = RLock()

    def recover_runtime_state(self) -> dict[str, int]:
        """Recover conservatively after a local backend restart.

        A job that was only queued is safe to expose for another explicit run.
        A running job becomes needs_review because the previous process may have
        reached the platform before it died; replaying it could duplicate a post.
        """
        with SessionLocal() as db:
            cleared_locks = profile_locks.clear_all(db)

            worker_statement = select(WorkerTask).where(
                WorkerTask.status.in_(["queued", "running"])
            )
            interrupted_tasks = list(db.scalars(worker_statement).all())
            now = utcnow()
            interrupted_task_ids = {task.id for task in interrupted_tasks}
            for task in interrupted_tasks:
                task.status = "interrupted"
                task.finished_at = now
                task.error_message = "Backend restarted before this task completed."

            queued_jobs = list(
                db.scalars(select(PublishJob).where(PublishJob.status == "queued")).all()
            )
            affected_content_ids: set[str] = set()
            affected_plan_ids: set[str] = set()
            for job in queued_jobs:
                job.status = "scheduled" if job.plan_id else "draft"
                job.stage = None
                job.worker_task_id = None
                job.error_message = "Backend restarted before this publish job started."
                if job.content_id:
                    affected_content_ids.add(job.content_id)
                if job.plan_id:
                    affected_plan_ids.add(job.plan_id)

            running_jobs = list(
                db.scalars(select(PublishJob).where(PublishJob.status == "running")).all()
            )
            running_job_ids = {job.id for job in running_jobs}
            for job in running_jobs:
                job.status = "needs_review"
                job.stage = "needs_review"
                job.error_message = (
                    "Backend restarted during publishing. Review Facebook before retrying "
                    "because the post may already have been submitted."
                )
                if job.content_id:
                    affected_content_ids.add(job.content_id)
                if job.plan_id:
                    affected_plan_ids.add(job.plan_id)

            if interrupted_task_ids:
                attempts = list(
                    db.scalars(
                        select(PublishAttempt).where(
                            PublishAttempt.worker_task_id.in_(interrupted_task_ids),
                            PublishAttempt.status.in_(["queued", "running"]),
                        )
                    ).all()
                )
                for attempt in attempts:
                    if attempt.job_id in running_job_ids:
                        attempt.status = "needs_review"
                        attempt.stage = "needs_review"
                        attempt.error_message = (
                            "Backend restarted while this attempt may have been publishing."
                        )
                    else:
                        attempt.status = "interrupted"
                        attempt.stage = "interrupted"
                        attempt.error_message = "Backend restarted before this attempt started."
                    attempt.finished_at = now

            db.flush()
            for content_id in affected_content_ids:
                self._refresh_content_status(db, content_id)
            for plan_id in affected_plan_ids:
                self._refresh_plan_status(db, plan_id)
            db.commit()

            return {
                "cleared_locks": cleared_locks,
                "interrupted_tasks": len(interrupted_tasks),
                "reset_publish_jobs": len(queued_jobs),
                "review_publish_jobs": len(running_jobs),
            }

    def submit_browser_test(self, profile_id: int) -> WorkerTask:
        with SessionLocal() as db:
            task = WorkerTask(
                task_type="browser_test",
                profile_id=profile_id,
                status="queued",
                payload_json="{}",
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            task_id = task.id

        self._submit_future(task_id, self._run_browser_test, task_id)
        with SessionLocal() as db:
            return db.get(WorkerTask, task_id)  # type: ignore[return-value]

    def submit_publish_job(self, job_id: str) -> WorkerTask:
        with SessionLocal() as db:
            job = db.get(PublishJob, job_id)
            if job is None:
                raise ValueError("Publish job not found.")
            if job.status in {"queued", "running"}:
                raise ValueError("Publish job is already queued or running.")
            if job.status == "succeeded":
                raise ValueError("Publish job already succeeded.")
            if job.status == "needs_review":
                raise ValueError(
                    "Publish job needs manual review before it can be retried. This prevents duplicate posts."
                )

            allowed = {"draft", "failed"}
            if job.plan_id is not None:
                allowed.add("scheduled")
            if job.status not in allowed:
                raise ValueError(f"Publish job cannot run from status '{job.status}'.")

            profile_id = self._resolve_job_profile_id(db, job)
            if job.platform == "facebook":
                if job.plan_id is not None:
                    self._validate_formal_facebook_job(job)
                else:
                    target = db.scalar(
                        select(PublishTarget).where(
                            PublishTarget.profile_id == profile_id,
                            PublishTarget.platform == "facebook",
                        )
                    )
                    if target is None:
                        raise ValueError(
                            f"iX #{profile_id} 尚未设置 Facebook 默认发布主页。"
                        )

            task = WorkerTask(
                task_type="publish",
                profile_id=profile_id,
                status="queued",
                payload_json=json.dumps(
                    {
                        "publish_job_id": job.id,
                        "publish_plan_id": job.plan_id,
                        "channel_id": job.channel_id,
                        "flow_revision_id": job.flow_revision_id,
                    },
                    ensure_ascii=False,
                ),
            )
            db.add(task)
            db.flush()

            attempt_no = int(
                db.scalar(
                    select(func.max(PublishAttempt.attempt_no)).where(
                        PublishAttempt.job_id == job.id
                    )
                )
                or 0
            ) + 1
            attempt = PublishAttempt(
                job_id=job.id,
                worker_task_id=task.id,
                attempt_no=attempt_no,
                status="queued",
                stage="queued",
            )
            db.add(attempt)
            db.flush()

            job.status = "queued"
            job.stage = "queued"
            job.worker_task_id = task.id
            job.error_message = None
            if job.content_id:
                self._refresh_content_status(db, job.content_id)
            if job.plan_id:
                self._refresh_plan_status(db, job.plan_id)
            db.commit()
            db.refresh(task)
            task_id = task.id
            attempt_id = attempt.id

        self._submit_future(task_id, self._run_publish_job, task_id, job_id, attempt_id)
        with SessionLocal() as db:
            return db.get(WorkerTask, task_id)  # type: ignore[return-value]

    def _submit_future(self, task_id: str, fn: Any, *args: Any) -> None:
        future = self._executor.submit(fn, *args)
        with self._lock:
            self._futures[task_id] = future
        future.add_done_callback(lambda _: self._forget_future(task_id))

    def _run_browser_test(self, task_id: str) -> None:
        owner_id = f"{self.instance_id}:{task_id}"
        profile_id: int | None = None
        opened_here = False

        with SessionLocal() as db:
            task = db.get(WorkerTask, task_id)
            if task is None:
                return
            profile_id = task.profile_id
            task.status = "running"
            task.attempts += 1
            task.started_at = utcnow()
            db.commit()

        try:
            with SessionLocal() as db:
                profile_locks.acquire(
                    db,
                    profile_id=profile_id,
                    owner_id=owner_id,
                    task_id=task_id,
                    ttl_seconds=300,
                )

            session = browser_sessions.open(profile_id)
            opened_here = not bool(session.get("already_open"))

            result = {
                "profile_id": profile_id,
                "selenium_attached": bool(session.get("alive")),
                "current_url": session.get("current_url"),
                "title": session.get("title"),
                "window_count": session.get("window_count", 0),
                "opened_here": opened_here,
            }

            self._mark_task_success(task_id, result)
        except ProfileBusyError as exc:
            self._mark_task_error(task_id, "blocked", str(exc))
        except Exception as exc:
            self._mark_task_error(task_id, "failed", str(exc))
        finally:
            self._cleanup_profile(profile_id, owner_id, opened_here)

    def _run_publish_job(self, task_id: str, job_id: str, attempt_id: str) -> None:
        owner_id = f"{self.instance_id}:{task_id}"
        profile_id: int | None = None
        opened_here = False
        started_perf = perf_counter()
        browser_open_ms: int | None = None
        platform_ms: int | None = None

        with SessionLocal() as db:
            task = db.get(WorkerTask, task_id)
            job = db.get(PublishJob, job_id)
            attempt = db.get(PublishAttempt, attempt_id)
            if task is None or job is None or attempt is None:
                return

            profile_id = task.profile_id
            now = utcnow()
            task.status = "running"
            task.attempts += 1
            task.started_at = now
            job.status = "running"
            job.stage = "opening_browser"
            job.error_message = None
            attempt.status = "running"
            attempt.stage = "opening_browser"
            attempt.started_at = now
            if job.content_id:
                self._refresh_content_status(db, job.content_id)
            if job.plan_id:
                self._refresh_plan_status(db, job.plan_id)
            db.commit()

        try:
            with SessionLocal() as db:
                profile_locks.acquire(
                    db,
                    profile_id=profile_id,
                    owner_id=owner_id,
                    task_id=task_id,
                    ttl_seconds=7200,
                )

            browser_started = perf_counter()
            session = browser_sessions.open(profile_id)
            browser_open_ms = int((perf_counter() - browser_started) * 1000)
            opened_here = not bool(session.get("already_open"))
            driver = browser_sessions.get_driver(profile_id)

            self._set_publish_stage(job_id, attempt_id, "platform_automation", browser_open_ms=browser_open_ms)
            platform, platform_content = self._load_platform_content(job_id)
            adapter = get_platform_adapter(platform)
            platform_started = perf_counter()
            result = adapter.publish(driver, platform_content)
            platform_ms = int((perf_counter() - platform_started) * 1000)

            verified = bool(result.get("verified"))
            submitted = bool(result.get("submitted"))
            total_ms = int((perf_counter() - started_perf) * 1000)
            if submitted and verified:
                self._mark_publish_result(
                    job_id,
                    task_id,
                    attempt_id,
                    "succeeded",
                    result=result,
                    browser_open_ms=browser_open_ms,
                    platform_ms=platform_ms,
                    total_ms=total_ms,
                )
            elif submitted:
                self._mark_publish_result(
                    job_id,
                    task_id,
                    attempt_id,
                    "needs_review",
                    result=result,
                    error_message=(
                        str(result.get("verification"))
                        or "Post was submitted but could not be independently verified."
                    ),
                    browser_open_ms=browser_open_ms,
                    platform_ms=platform_ms,
                    total_ms=total_ms,
                )
            else:
                self._mark_publish_result(
                    job_id,
                    task_id,
                    attempt_id,
                    "failed",
                    result=result,
                    error_message="Platform adapter returned without confirming submission.",
                    browser_open_ms=browser_open_ms,
                    platform_ms=platform_ms,
                    total_ms=total_ms,
                )
        except ProfileBusyError as exc:
            self._mark_publish_result(
                job_id,
                task_id,
                attempt_id,
                "failed",
                task_status="blocked",
                error_message=str(exc),
                browser_open_ms=browser_open_ms,
                platform_ms=platform_ms,
                total_ms=int((perf_counter() - started_perf) * 1000),
            )
        except PlatformNeedsReviewError as exc:
            self._mark_publish_result(
                job_id,
                task_id,
                attempt_id,
                "needs_review",
                task_status="needs_review",
                result={"submitted": exc.submitted},
                error_message=str(exc),
                browser_open_ms=browser_open_ms,
                platform_ms=platform_ms,
                total_ms=int((perf_counter() - started_perf) * 1000),
            )
        except (PlatformPublishError, PlatformValidationError, FileNotFoundError) as exc:
            self._mark_publish_result(
                job_id,
                task_id,
                attempt_id,
                "failed",
                error_message=str(exc),
                browser_open_ms=browser_open_ms,
                platform_ms=platform_ms,
                total_ms=int((perf_counter() - started_perf) * 1000),
            )
        except Exception as exc:
            self._mark_publish_result(
                job_id,
                task_id,
                attempt_id,
                "failed",
                error_message=f"Unexpected publish worker error: {exc}",
                browser_open_ms=browser_open_ms,
                platform_ms=platform_ms,
                total_ms=int((perf_counter() - started_perf) * 1000),
            )
        finally:
            self._cleanup_profile(profile_id, owner_id, opened_here)

    def _load_platform_content(self, job_id: str) -> tuple[str, PlatformContent]:
        with SessionLocal() as db:
            job = db.get(PublishJob, job_id)
            if job is None:
                raise ValueError("Publish job disappeared before execution.")

            if job.plan_id is not None:
                content_snapshot = self._json_object(job.content_snapshot_json, "content snapshot")
                channel_snapshot = self._json_object(job.channel_snapshot_json, "channel snapshot")
                media_items = content_snapshot.get("media") or []
                if not isinstance(media_items, list):
                    raise PlatformValidationError("Content snapshot media is invalid.")

                media: list[PlatformMedia] = []
                for item in media_items:
                    if not isinstance(item, dict):
                        raise PlatformValidationError("Content snapshot media item is invalid.")
                    stored_name = str(item.get("stored_name") or "").strip()
                    if not stored_name:
                        raise PlatformValidationError("Content snapshot media is missing stored_name.")
                    media.append(
                        PlatformMedia(
                            media_type=str(item.get("media_type") or ""),
                            path=Path(get_media_path(stored_name)),
                            mime_type=str(item.get("mime_type") or "application/octet-stream"),
                            original_name=str(item.get("original_name") or stored_name),
                        )
                    )

                target_id = str(channel_snapshot.get("target_id") or "").strip() or None
                target_url = str(channel_snapshot.get("target_url") or "").strip() or None
                if job.platform == "facebook" and (not target_id or not target_url):
                    raise PlatformValidationError(
                        "Formal Facebook job is missing its immutable channel target snapshot."
                    )

                return job.platform, PlatformContent(
                    text=str(content_snapshot.get("text") or ""),
                    media=tuple(media),
                    target_type=str(channel_snapshot.get("target_type") or "").strip() or None,
                    target_id=target_id,
                    target_name=str(channel_snapshot.get("target_name") or "").strip() or None,
                    target_url=target_url,
                )

            if job.content_id is None or job.profile_id is None:
                raise ValueError("Legacy publish job is missing content/profile identity.")
            content = db.get(ContentItem, job.content_id)
            if content is None:
                raise ValueError("Content disappeared before execution.")

            assets = list(
                db.scalars(
                    select(MediaAsset)
                    .where(MediaAsset.content_id == content.id)
                    .order_by(MediaAsset.sort_order.asc())
                ).all()
            )
            media = tuple(
                PlatformMedia(
                    media_type=asset.media_type,
                    path=Path(get_media_path(asset.stored_name)),
                    mime_type=asset.mime_type,
                    original_name=asset.original_name,
                )
                for asset in assets
            )

            target = db.scalar(
                select(PublishTarget).where(
                    PublishTarget.profile_id == job.profile_id,
                    PublishTarget.platform == job.platform,
                )
            )
            if job.platform == "facebook" and target is None:
                raise PlatformValidationError(
                    f"iX #{job.profile_id} 尚未设置 Facebook 默认发布主页。"
                )

            return job.platform, PlatformContent(
                text=content.text,
                media=media,
                target_type=target.target_type if target else None,
                target_id=target.target_id if target else None,
                target_name=target.target_name if target else None,
                target_url=target.target_url if target else None,
            )

    def _resolve_job_profile_id(self, db: Session, job: PublishJob) -> int:
        if job.profile_id is not None:
            return job.profile_id
        if job.plan_id is not None:
            snapshot = self._json_object(job.channel_snapshot_json, "channel snapshot")
            value = snapshot.get("profile_id")
            try:
                profile_id = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("Formal publish job channel snapshot has no valid profile_id.") from exc
            if profile_id <= 0:
                raise ValueError("Formal publish job channel snapshot has no valid profile_id.")
            return profile_id
        if job.channel_id:
            channel = db.get(Channel, job.channel_id)
            if channel is not None:
                return channel.profile_id
        raise ValueError("Publish job has no executable iX profile identity.")

    def _validate_formal_facebook_job(self, job: PublishJob) -> None:
        snapshot = self._json_object(job.channel_snapshot_json, "channel snapshot")
        if str(snapshot.get("platform") or "").lower() != "facebook":
            raise ValueError("Formal Facebook job channel snapshot platform mismatch.")
        if not str(snapshot.get("target_id") or "").strip():
            raise ValueError("Formal Facebook job is missing target_id in its channel snapshot.")
        if not str(snapshot.get("target_url") or "").strip():
            raise ValueError("Formal Facebook job is missing target_url in its channel snapshot.")
        try:
            profile_id = int(snapshot.get("profile_id"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Formal Facebook job is missing profile_id in its channel snapshot.") from exc
        if profile_id <= 0:
            raise ValueError("Formal Facebook job is missing profile_id in its channel snapshot.")

    @staticmethod
    def _json_object(raw: str | None, label: str) -> dict[str, Any]:
        try:
            value = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid {label} JSON.") from exc
        if not isinstance(value, dict):
            raise ValueError(f"Invalid {label} JSON object.")
        return value

    def _set_publish_stage(
        self,
        job_id: str,
        attempt_id: str,
        stage: str,
        *,
        browser_open_ms: int | None = None,
    ) -> None:
        with SessionLocal() as db:
            job = db.get(PublishJob, job_id)
            attempt = db.get(PublishAttempt, attempt_id)
            if job is None or attempt is None:
                return
            job.stage = stage
            attempt.stage = stage
            if browser_open_ms is not None:
                attempt.browser_open_ms = browser_open_ms
            db.commit()

    def _mark_publish_result(
        self,
        job_id: str,
        task_id: str,
        attempt_id: str,
        job_status: str,
        *,
        task_status: str | None = None,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
        browser_open_ms: int | None = None,
        platform_ms: int | None = None,
        total_ms: int | None = None,
    ) -> None:
        with SessionLocal() as db:
            job = db.get(PublishJob, job_id)
            task = db.get(WorkerTask, task_id)
            attempt = db.get(PublishAttempt, attempt_id)
            if job is None or task is None or attempt is None:
                return

            final_task_status = task_status or job_status
            if final_task_status == "draft":
                final_task_status = "failed"

            final_stage = (
                "completed"
                if job_status == "succeeded"
                else "needs_review"
                if job_status == "needs_review"
                else "failed"
            )
            now = utcnow()
            job.status = job_status
            job.stage = final_stage
            job.error_message = error_message
            if result:
                published_url = result.get("published_url")
                if published_url:
                    job.published_url = str(published_url)

            attempt.status = job_status
            attempt.stage = final_stage
            attempt.result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
            attempt.error_message = error_message
            attempt.browser_open_ms = browser_open_ms
            attempt.platform_ms = platform_ms
            attempt.total_ms = total_ms
            if result and bool(result.get("submitted")):
                attempt.submitted_at = now
            attempt.finished_at = now

            task.status = final_task_status
            task.result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
            task.error_message = error_message
            task.finished_at = now

            if job.channel_id:
                channel = db.get(Channel, job.channel_id)
                if channel is not None:
                    if job_status == "succeeded":
                        channel.health_status = "healthy"
                    elif job_status == "needs_review":
                        channel.health_status = "warning"
                    elif job_status == "failed":
                        channel.health_status = "error"
                    channel.last_checked_at = now

            if job.content_id:
                self._refresh_content_status(db, job.content_id)
            if job.plan_id:
                self._refresh_plan_status(db, job.plan_id)
            db.commit()

    def _mark_task_success(self, task_id: str, result: dict[str, Any]) -> None:
        with SessionLocal() as db:
            task = db.get(WorkerTask, task_id)
            if task is None:
                return
            task.status = "succeeded"
            task.result_json = json.dumps(result, ensure_ascii=False)
            task.finished_at = utcnow()
            db.commit()

    def _mark_task_error(self, task_id: str, task_status: str, message: str) -> None:
        with SessionLocal() as db:
            task = db.get(WorkerTask, task_id)
            if task is None:
                return
            task.status = task_status
            task.error_message = message
            task.finished_at = utcnow()
            db.commit()

    def _cleanup_profile(
        self,
        profile_id: int | None,
        owner_id: str,
        opened_here: bool,
    ) -> None:
        if opened_here and profile_id is not None:
            try:
                browser_sessions.close(profile_id)
            except Exception:
                pass

        if profile_id is not None:
            with SessionLocal() as db:
                try:
                    profile_locks.release(db, profile_id, owner_id)
                except ProfileBusyError:
                    pass

    @staticmethod
    def _refresh_content_status(db: Session, content_id: str) -> None:
        content = db.get(ContentItem, content_id)
        if content is None:
            return
        statuses = list(
            db.scalars(
                select(PublishJob.status).where(
                    PublishJob.content_id == content_id,
                    PublishJob.plan_id.is_(None),
                )
            ).all()
        )
        if not statuses or all(value == "draft" for value in statuses):
            content.status = "draft"
        elif any(value == "running" for value in statuses):
            content.status = "running"
        elif any(value == "queued" for value in statuses):
            content.status = "queued"
        elif any(value == "needs_review" for value in statuses):
            content.status = "needs_review"
        elif all(value == "succeeded" for value in statuses):
            content.status = "succeeded"
        elif any(value == "failed" for value in statuses) and any(
            value == "succeeded" for value in statuses
        ):
            content.status = "partial"
        elif any(value == "failed" for value in statuses):
            content.status = "failed"
        else:
            content.status = "draft"

    @staticmethod
    def _refresh_plan_status(db: Session, plan_id: str) -> None:
        plan = db.get(PublishPlan, plan_id)
        if plan is None:
            return
        statuses = list(
            db.scalars(select(PublishJob.status).where(PublishJob.plan_id == plan_id)).all()
        )
        if not statuses:
            return
        if any(value == "running" for value in statuses):
            plan.status = "running"
        elif any(value == "queued" for value in statuses):
            plan.status = "queued"
        elif any(value == "needs_review" for value in statuses):
            plan.status = "needs_review"
        elif all(value == "succeeded" for value in statuses):
            plan.status = "succeeded"
        elif any(value == "failed" for value in statuses) and any(
            value == "succeeded" for value in statuses
        ):
            plan.status = "partial"
        elif any(value == "failed" for value in statuses):
            plan.status = "failed"
        elif all(value == "draft" for value in statuses):
            plan.status = "draft"
        elif any(value == "scheduled" for value in statuses):
            plan.status = "scheduled"

    def get_task(self, db: Session, task_id: str) -> WorkerTask | None:
        return db.get(WorkerTask, task_id)

    def list_tasks(self, db: Session, limit: int = 50) -> list[WorkerTask]:
        statement = (
            select(WorkerTask)
            .order_by(WorkerTask.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        return list(db.scalars(statement).all())

    def stats(self) -> dict[str, int]:
        with self._lock:
            active = sum(1 for future in self._futures.values() if not future.done())
        return {
            "max_workers": self.max_workers,
            "active_tasks": active,
        }

    def shutdown(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def _forget_future(self, task_id: str) -> None:
        with self._lock:
            self._futures.pop(task_id, None)


def worker_task_to_dict(task: WorkerTask) -> dict[str, Any]:
    result: Any = None
    payload: Any = None
    if task.result_json:
        try:
            result = json.loads(task.result_json)
        except json.JSONDecodeError:
            result = task.result_json
    if task.payload_json:
        try:
            payload = json.loads(task.payload_json)
        except json.JSONDecodeError:
            payload = task.payload_json

    return {
        "id": task.id,
        "task_type": task.task_type,
        "profile_id": task.profile_id,
        "status": task.status,
        "attempts": task.attempts,
        "payload": payload,
        "result": result,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


worker_manager = WorkerManager(max_workers=3)
