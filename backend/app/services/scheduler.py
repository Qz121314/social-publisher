from __future__ import annotations

from datetime import datetime, timezone
from threading import Event, RLock, Thread
from typing import Any

from sqlalchemy import select

from app.database import SessionLocal
from app.models.content import PublishJob
from app.models.publishing import PublishPlan
from app.services.worker import WorkerManager, worker_manager


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PublishScheduler:
    """SQLite-backed dispatcher for formal PublishJobs.

    SQLite is the source of truth. The scheduler keeps no durable in-memory
    schedule; every tick re-discovers due jobs from the database and dispatches
    only as many as the bounded WorkerManager currently has capacity for.
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
        """Request an early tick after a new immediate job or manual run-now."""
        self._wake_event.set()

    def run_once(self, *, now: datetime | None = None) -> dict[str, Any]:
        tick_at = now or utcnow()
        worker_stats = self.worker.stats()
        available_slots = max(
            0,
            int(worker_stats.get("max_workers", 0)) - int(worker_stats.get("active_tasks", 0)),
        )
        limit = min(self.batch_size, available_slots)

        due_job_ids: list[str] = []
        if limit > 0:
            with SessionLocal() as db:
                due_job_ids = list(
                    db.scalars(
                        select(PublishJob.id)
                        .where(
                            PublishJob.plan_id.is_not(None),
                            PublishJob.status == "scheduled",
                            PublishJob.scheduled_at.is_not(None),
                            PublishJob.scheduled_at <= tick_at,
                        )
                        .order_by(PublishJob.scheduled_at.asc(), PublishJob.created_at.asc())
                        .limit(limit)
                    ).all()
                )

        dispatched: list[str] = []
        errors: list[dict[str, str]] = []
        for job_id in due_job_ids:
            try:
                self.worker.submit_publish_job(job_id)
                dispatched.append(job_id)
            except ValueError as exc:
                message = str(exc)
                if "already queued or running" not in message:
                    self._mark_dispatch_failure(job_id, message)
                    errors.append({"job_id": job_id, "error": message})
            except Exception as exc:
                # A scheduler/runtime infrastructure error must not silently turn
                # a scheduled job into failed. Leave it scheduled for a later tick.
                errors.append({"job_id": job_id, "error": str(exc)})

        with self._lock:
            self._last_tick_at = tick_at
            if dispatched:
                self._last_dispatch_at = utcnow()
            self._dispatched_total += len(dispatched)
            self._dispatch_errors_total += len(errors)
            self._last_error = errors[-1]["error"] if errors else None

        return {
            "due": len(due_job_ids),
            "dispatched": len(dispatched),
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
                "last_error": self._last_error,
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

    @staticmethod
    def _mark_dispatch_failure(job_id: str, message: str) -> None:
        with SessionLocal() as db:
            job = db.get(PublishJob, job_id)
            if job is None or job.status != "scheduled":
                return
            job.status = "failed"
            job.stage = "dispatch_failed"
            job.error_message = message
            if job.plan_id:
                plan = db.get(PublishPlan, job.plan_id)
                if plan is not None:
                    statuses = list(
                        db.scalars(
                            select(PublishJob.status).where(PublishJob.plan_id == job.plan_id)
                        ).all()
                    )
                    if all(value == "failed" for value in statuses):
                        plan.status = "failed"
                    elif any(value == "failed" for value in statuses):
                        plan.status = "partial"
            db.commit()


publish_scheduler = PublishScheduler()
