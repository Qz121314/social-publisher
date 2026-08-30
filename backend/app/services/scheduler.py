from __future__ import annotations

import json
from datetime import datetime, timezone
from threading import Event, RLock, Thread
from typing import Any

from sqlalchemy import select

from app.database import SessionLocal
from app.models.channel import Channel
from app.models.content import PublishJob
from app.models.publishing import PublishPlan
from app.services.browser_sessions import browser_sessions
from app.services.profile_locks import profile_locks
from app.services.worker import WorkerManager, worker_manager


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PublishScheduler:
    """SQLite-backed dispatcher for formal PublishJobs.

    SQLite is the source of truth. Phase 5 also guarantees that at most one
    PublishJob per iX profile is dispatched at a time, while different profiles
    may still use the bounded Worker Pool concurrently.
    """

    def __init__(
        self,
        worker: WorkerManager = worker_manager,
        *,
        poll_interval_seconds: float = 1.0,
        batch_size: int = 50,
    ) -> None:
        self.worker = worker
        self.poll_interval_seconds = max(0.25, float(poll_interval_seconds))
        self.batch_size = max(1, int(batch_size))
        self._stop_event = Event()
        self._wake_event = Event()
        self._thread: Thread | None = None
        self._lock = RLock()
        self._running = False
        self._last_tick_at: datetime | None = None
        self._last_dispatch_at: datetime | None = None
        self._last_error: str | None = None
        self._dispatched_total = 0
        self._dispatch_errors_total = 0
        self._deferred_busy_profiles_total = 0
        self._expired_warm_sessions_total = 0

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._wake_event.clear()
            self._running = True
            self._thread = Thread(
                target=self._run_loop,
                name="social-publisher-scheduler",
                daemon=True,
            )
            self._thread.start()

    def shutdown(self, wait: bool = True) -> None:
        with self._lock:
            thread = self._thread
            self._running = False
            self._stop_event.set()
            self._wake_event.set()
        if wait and thread is not None and thread.is_alive():
            thread.join(timeout=max(2.0, self.poll_interval_seconds * 2))
        with self._lock:
            if self._thread is thread:
                self._thread = None

    def wake(self) -> None:
        self._wake_event.set()

    def run_once(self, *, now: datetime | None = None) -> dict[str, Any]:
        tick_at = now or utcnow()
        expired_warm_sessions = browser_sessions.expire_warm_sessions()
        worker_stats = self.worker.stats()
        available_slots = max(
            0,
            int(worker_stats.get("max_workers", 0)) - int(worker_stats.get("active_tasks", 0)),
        )
        limit = min(self.batch_size, available_slots)

        due_job_ids: list[str] = []
        deferred_busy = 0
        candidate_count = 0
        if limit > 0:
            with SessionLocal() as db:
                busy_profile_ids = self._busy_profile_ids(db)
                candidate_limit = min(max(self.batch_size * 5, limit * 5, 50), 500)
                candidates = list(
                    db.scalars(
                        select(PublishJob)
                        .where(
                            PublishJob.plan_id.is_not(None),
                            PublishJob.status == "scheduled",
                            PublishJob.scheduled_at.is_not(None),
                            PublishJob.scheduled_at <= tick_at,
                        )
                        .order_by(PublishJob.scheduled_at.asc(), PublishJob.created_at.asc())
                        .limit(candidate_limit)
                    ).all()
                )
                candidate_count = len(candidates)

                for job in candidates:
                    profile_id = self._profile_id_for_job(db, job)
                    if profile_id is not None and profile_id in busy_profile_ids:
                        deferred_busy += 1
                        continue
                    due_job_ids.append(job.id)
                    if profile_id is not None:
                        # Reserve this profile for the remainder of this tick so
                        # two due jobs from the same iX environment are never
                        # submitted concurrently.
                        busy_profile_ids.add(profile_id)
                    if len(due_job_ids) >= limit:
                        break

        dispatched: list[str] = []
        errors: list[dict[str, str]] = []
        for job_id in due_job_ids:
            validation_error = self._dispatch_validation_error(job_id)
            if validation_error:
                self._mark_dispatch_failure(job_id, validation_error)
                errors.append({"job_id": job_id, "error": validation_error})
                continue
            try:
                self.worker.submit_publish_job(job_id)
                dispatched.append(job_id)
            except ValueError as exc:
                message = str(exc)
                if "already queued or running" not in message:
                    self._mark_dispatch_failure(job_id, message)
                    errors.append({"job_id": job_id, "error": message})
            except Exception as exc:
                # Infrastructure errors remain scheduled so a later tick can
                # retry without converting a temporary runtime issue into a
                # permanent publish failure.
                errors.append({"job_id": job_id, "error": str(exc)})

        with self._lock:
            self._last_tick_at = tick_at
            if dispatched:
                self._last_dispatch_at = utcnow()
            self._dispatched_total += len(dispatched)
            self._dispatch_errors_total += len(errors)
            self._deferred_busy_profiles_total += deferred_busy
            self._expired_warm_sessions_total += expired_warm_sessions
            self._last_error = errors[-1]["error"] if errors else None

        return {
            "candidates": candidate_count,
            "due": len(due_job_ids),
            "dispatched": len(dispatched),
            "deferred_busy_profiles": deferred_busy,
            "expired_warm_sessions": expired_warm_sessions,
            "errors": errors,
            "available_slots": available_slots,
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            thread_alive = bool(self._thread and self._thread.is_alive())
            return {
                "running": self._running and thread_alive,
                "poll_interval_seconds": self.poll_interval_seconds,
                "batch_size": self.batch_size,
                "last_tick_at": self._last_tick_at.isoformat() if self._last_tick_at else None,
                "last_dispatch_at": self._last_dispatch_at.isoformat() if self._last_dispatch_at else None,
                "dispatched_total": self._dispatched_total,
                "dispatch_errors_total": self._dispatch_errors_total,
                "deferred_busy_profiles_total": self._deferred_busy_profiles_total,
                "expired_warm_sessions_total": self._expired_warm_sessions_total,
                "last_error": self._last_error,
                "browser_sessions": browser_sessions.stats(),
            }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                with self._lock:
                    self._last_tick_at = utcnow()
                    self._last_error = str(exc)
                    self._dispatch_errors_total += 1
            self._wake_event.wait(self.poll_interval_seconds)
            self._wake_event.clear()
        with self._lock:
            self._running = False

    @classmethod
    def _busy_profile_ids(cls, db) -> set[int]:
        busy: set[int] = set()
        active_jobs = list(
            db.scalars(
                select(PublishJob).where(
                    PublishJob.plan_id.is_not(None),
                    PublishJob.status.in_(["queued", "running"]),
                )
            ).all()
        )
        for job in active_jobs:
            profile_id = cls._profile_id_for_job(db, job)
            if profile_id is not None:
                busy.add(profile_id)

        # Browser tests, target scans, or other manual operations also use the
        # database-backed ProfileLock. Defer scheduled publishing instead of
        # turning a temporarily busy environment into a failed job.
        for lock in profile_locks.list_active(db):
            busy.add(lock.profile_id)
        return busy

    @staticmethod
    def _profile_id_for_job(db, job: PublishJob) -> int | None:
        if job.channel_id:
            channel = db.get(Channel, job.channel_id)
            if channel is not None:
                return channel.profile_id
        try:
            snapshot = json.loads(job.channel_snapshot_json or "{}")
            value = snapshot.get("profile_id") if isinstance(snapshot, dict) else None
            profile_id = int(value)
            return profile_id if profile_id > 0 else None
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _dispatch_validation_error(job_id: str) -> str | None:
        """Apply current operational kill-switches without mutating snapshots."""
        with SessionLocal() as db:
            job = db.get(PublishJob, job_id)
            if job is None:
                return "Publish job not found."
            if job.status != "scheduled":
                return None
            if job.channel_id:
                channel = db.get(Channel, job.channel_id)
                if channel is None:
                    return "Publish Channel no longer exists."
                if not channel.enabled:
                    return "Publish Channel is disabled. Re-enable it before running this plan."
            return None

    @staticmethod
    def _mark_dispatch_failure(job_id: str, message: str) -> None:
        with SessionLocal() as db:
            job = db.get(PublishJob, job_id)
            if job is None or job.status != "scheduled":
                return
            job.status = "failed"
            job.stage = "dispatch_failed"
            job.error_message = message
            db.flush()
            if job.plan_id:
                PublishScheduler._refresh_plan_status(db, job.plan_id)
            db.commit()

    @staticmethod
    def _refresh_plan_status(db, plan_id: str) -> None:
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
        elif any(value == "scheduled" for value in statuses):
            plan.status = "scheduled"
        elif all(value == "succeeded" for value in statuses):
            plan.status = "succeeded"
        elif any(value == "failed" for value in statuses) and any(
            value == "succeeded" for value in statuses
        ):
            plan.status = "partial"
        elif any(value == "failed" for value in statuses):
            plan.status = "failed"
        elif all(value == "cancelled" for value in statuses):
            plan.status = "cancelled"
        elif all(value == "draft" for value in statuses):
            plan.status = "draft"


publish_scheduler = PublishScheduler()
