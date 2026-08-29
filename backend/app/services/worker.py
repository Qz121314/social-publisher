from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.content import ContentItem, MediaAsset, PublishJob
from app.models.execution import WorkerTask, utcnow
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
        """Recover conservative state after a local backend restart.

        Queued publish jobs are returned to draft because they did not start.
        Running publish jobs become `needs_review` because the previous process
        may have reached the platform before it died; replaying them could create
        a duplicate post.
        """
        with SessionLocal() as db:
            cleared_locks = profile_locks.clear_all(db)

            worker_statement = select(WorkerTask).where(
                WorkerTask.status.in_(["queued", "running"])
            )
            interrupted_tasks = list(db.scalars(worker_statement).all())
            now = utcnow()
            for task in interrupted_tasks:
                task.status = "interrupted"
                task.finished_at = now
                task.error_message = "Backend restarted before this task completed."

            queued_jobs = list(
                db.scalars(select(PublishJob).where(PublishJob.status == "queued")).all()
            )
            for job in queued_jobs:
                job.status = "draft"
                job.worker_task_id = None
                job.error_message = "Backend restarted before this publish job started."

            running_jobs = list(
                db.scalars(select(PublishJob).where(PublishJob.status == "running")).all()
            )
            affected_content_ids: set[str] = set()
            for job in running_jobs:
                job.status = "needs_review"
                job.error_message = (
                    "Backend restarted during publishing. Review Facebook before retrying "
                    "because the post may already have been submitted."
                )
                affected_content_ids.add(job.content_id)
            affected_content_ids.update(job.content_id for job in queued_jobs)

            db.flush()
            for content_id in affected_content_ids:
                self._refresh_content_status(db, content_id)
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
            if job.status not in {"draft", "failed"}:
                raise ValueError(f"Publish job cannot run from status '{job.status}'.")

            if job.platform == "facebook":
                target = db.scalar(
                    select(PublishTarget).where(
                        PublishTarget.profile_id == job.profile_id,
                        PublishTarget.platform == "facebook",
                    )
                )
                if target is None:
                    raise ValueError(
                        f"iX #{job.profile_id} 尚未设置 Facebook 默认发布主页。"
                    )

            task = WorkerTask(
                task_type="publish",
                profile_id=job.profile_id,
                status="queued",
                payload_json=json.dumps({"publish_job_id": job.id}),
            )
            db.add(task)
            db.flush()

            job.status = "queued"
            job.worker_task_id = task.id
            job.error_message = None
            self._refresh_content_status(db, job.content_id)
            db.commit()
            db.refresh(task)
            task_id = task.id

        self._submit_future(task_id, self._run_publish_job, task_id, job_id)
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

    def _run_publish_job(self, task_id: str, job_id: str) -> None:
        owner_id = f"{self.instance_id}:{task_id}"
        profile_id: int | None = None
        opened_here = False

        with SessionLocal() as db:
            task = db.get(WorkerTask, task_id)
            job = db.get(PublishJob, job_id)
            if task is None or job is None:
                return

            profile_id = job.profile_id
            task.status = "running"
            task.attempts += 1
            task.started_at = utcnow()
            job.status = "running"
            job.error_message = None
            self._refresh_content_status(db, job.content_id)
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

            session = browser_sessions.open(profile_id)
            opened_here = not bool(session.get("already_open"))
            driver = browser_sessions.get_driver(profile_id)

            platform, platform_content = self._load_platform_content(job_id)
            adapter = get_platform_adapter(platform)
            result = adapter.publish(driver, platform_content)

            verified = bool(result.get("verified"))
            submitted = bool(result.get("submitted"))
            if submitted and verified:
                self._mark_publish_result(job_id, task_id, "succeeded", result=result)
            elif submitted:
                self._mark_publish_result(
                    job_id,
                    task_id,
                    "needs_review",
                    result=result,
                    error_message=(
                        str(result.get("verification"))
                        or "Post was submitted but could not be independently verified."
                    ),
                )
            else:
                self._mark_publish_result(
                    job_id,
                    task_id,
                    "failed",
                    result=result,
                    error_message="Platform adapter returned without confirming submission.",
                )
        except ProfileBusyError as exc:
            self._mark_publish_result(job_id, task_id, "draft", task_status="blocked", error_message=str(exc))
        except PlatformNeedsReviewError as exc:
            self._mark_publish_result(
                job_id,
                task_id,
                "needs_review",
                task_status="needs_review",
                result={"submitted": exc.submitted},
                error_message=str(exc),
            )
        except (PlatformPublishError, PlatformValidationError, FileNotFoundError) as exc:
            self._mark_publish_result(job_id, task_id, "failed", error_message=str(exc))
        except Exception as exc:
            self._mark_publish_result(
                job_id,
                task_id,
                "failed",
                error_message=f"Unexpected publish worker error: {exc}",
            )
        finally:
            self._cleanup_profile(profile_id, owner_id, opened_here)

    def _load_platform_content(self, job_id: str) -> tuple[str, PlatformContent]:
        with SessionLocal() as db:
            job = db.get(PublishJob, job_id)
            if job is None:
                raise ValueError("Publish job disappeared before execution.")
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

    def _mark_publish_result(
        self,
        job_id: str,
        task_id: str,
        job_status: str,
        *,
        task_status: str | None = None,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        with SessionLocal() as db:
            job = db.get(PublishJob, job_id)
            task = db.get(WorkerTask, task_id)
            if job is None or task is None:
                return

            final_task_status = task_status or job_status
            if final_task_status == "draft":
                final_task_status = "failed"

            job.status = job_status
            job.error_message = error_message
            if result:
                published_url = result.get("published_url")
                if published_url:
                    job.published_url = str(published_url)

            task.status = final_task_status
            task.result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
            task.error_message = error_message
            task.finished_at = utcnow()

            self._refresh_content_status(db, job.content_id)
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
                select(PublishJob.status).where(PublishJob.content_id == content_id)
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
