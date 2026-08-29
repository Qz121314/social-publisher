from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor
from threading import RLock
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.execution import WorkerTask, utcnow
from app.services.browser_sessions import browser_sessions
from app.services.profile_locks import ProfileBusyError, profile_locks


class WorkerManager:
    """Small bounded worker pool used by browser automation jobs.

    The worker pool is platform-agnostic. Platform adapters will later submit
    publishing work through this layer rather than owning their own threads.
    """

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
        """Recover database state after a local backend restart.

        Social Publisher is intentionally a single local backend process. Any
        persisted profile lock therefore belongs to a dead previous process and
        can be safely removed at startup. Queued/running diagnostic tasks are
        marked interrupted instead of being executed a second time implicitly.
        """
        with SessionLocal() as db:
            cleared_locks = profile_locks.clear_all(db)
            statement = select(WorkerTask).where(
                WorkerTask.status.in_(["queued", "running"])
            )
            interrupted = list(db.scalars(statement).all())
            now = utcnow()
            for task in interrupted:
                task.status = "interrupted"
                task.finished_at = now
                task.error_message = "Backend restarted before this task completed."
            db.commit()
            return {
                "cleared_locks": cleared_locks,
                "interrupted_tasks": len(interrupted),
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

        future = self._executor.submit(self._run_browser_test, task_id)
        with self._lock:
            self._futures[task_id] = future
        future.add_done_callback(lambda _: self._forget_future(task_id))

        with SessionLocal() as db:
            return db.get(WorkerTask, task_id)  # type: ignore[return-value]

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

            with SessionLocal() as db:
                task = db.get(WorkerTask, task_id)
                if task is not None:
                    task.status = "succeeded"
                    task.result_json = json.dumps(result, ensure_ascii=False)
                    task.finished_at = utcnow()
                    db.commit()
        except ProfileBusyError as exc:
            self._mark_task_error(task_id, "blocked", str(exc))
        except Exception as exc:
            self._mark_task_error(task_id, "failed", str(exc))
        finally:
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

    def _mark_task_error(self, task_id: str, task_status: str, message: str) -> None:
        with SessionLocal() as db:
            task = db.get(WorkerTask, task_id)
            if task is None:
                return
            task.status = task_status
            task.error_message = message
            task.finished_at = utcnow()
            db.commit()

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
    if task.result_json:
        try:
            result = json.loads(task.result_json)
        except json.JSONDecodeError:
            result = task.result_json

    return {
        "id": task.id,
        "task_type": task.task_type,
        "profile_id": task.profile_id,
        "status": task.status,
        "attempts": task.attempts,
        "result": result,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


worker_manager = WorkerManager(max_workers=3)
