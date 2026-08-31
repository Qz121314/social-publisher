from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor
from threading import RLock
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import SessionLocal
from app.models.account import Account, AccountGroup
from app.models.batch_task import BatchTask, TaskJob, utcnow
from app.schemas.batch_task import BatchLoginCreate
from app.services.account_login import (
    AccountLoginError,
    AccountLoginUnsupported,
    recover_account_login,
)
from app.services.account_runtime import (
    AccountRuntimeError,
    AccountRuntimeNeedsAttention,
    ensure_account_runtime,
)
from app.services.browser_sessions import BrowserSessionError
from app.services.ixbrowser import IXBrowserError
from app.services.profile_locks import ProfileBusyError


ACTIVE_JOB_STATUSES = {"queued", "running"}
ATTENTION_JOB_STATUSES = {"needs_attention", "needs_review", "waiting_user", "blocked"}


class BatchTaskError(RuntimeError):
    pass


class BatchTaskRunner:
    """Bounded operation runner for account-level batch tasks.

    PublishJob continues to use the established publish WorkerManager. This
    runner is the Phase 10 operation layer for login/check/maintenance tasks and
    is intentionally bounded so a group click never fans out hundreds of browser
    processes at once.
    """

    def __init__(self, max_workers: int = 3) -> None:
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="social-publisher-operation",
        )
        self._futures: dict[str, Future[Any]] = {}
        self._lock = RLock()

    def submit_login_job(self, job_id: str) -> None:
        key = f"login:{job_id}"
        with self._lock:
            current = self._futures.get(key)
            if current is not None and not current.done():
                return
            future = self._executor.submit(self._run_login_job, job_id)
            self._futures[key] = future
        future.add_done_callback(lambda _: self._forget(key))

    def recover_runtime_state(self) -> dict[str, int]:
        """Recover queued login jobs conservatively after backend restart."""
        queued_ids: list[str] = []
        with SessionLocal() as db:
            now = utcnow()
            running = list(
                db.scalars(
                    select(TaskJob).where(
                        TaskJob.job_type == "login_recover",
                        TaskJob.status == "running",
                    )
                ).all()
            )
            affected_batches: set[str] = set()
            for job in running:
                job.status = "needs_review"
                job.stage = "interrupted"
                job.error_message = "后台在登录过程中重启，请先检查该账号当前登录状态。"
                job.finished_at = now
                affected_batches.add(job.batch_id)
            db.flush()
            for batch_id in affected_batches:
                self._refresh_batch(db, batch_id)

            queued_ids = list(
                db.scalars(
                    select(TaskJob.id).where(
                        TaskJob.job_type == "login_recover",
                        TaskJob.status == "queued",
                    )
                ).all()
            )
            db.commit()

        for job_id in queued_ids:
            self.submit_login_job(job_id)
        return {"review_jobs": len(running), "resumed_jobs": len(queued_ids)}

    def stats(self) -> dict[str, int]:
        with self._lock:
            active = sum(1 for future in self._futures.values() if not future.done())
        return {"max_workers": self.max_workers, "active_tasks": active}

    def shutdown(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def _forget(self, key: str) -> None:
        with self._lock:
            self._futures.pop(key, None)

    def _run_login_job(self, job_id: str) -> None:
        with SessionLocal() as db:
            job = db.get(TaskJob, job_id)
            if job is None or job.status != "queued":
                return
            account = db.get(Account, job.account_id) if job.account_id is not None else None
            if account is None:
                self._finish_job(db, job, "failed", "failed", "账号已不存在。")
                return
            batch = db.get(BatchTask, job.batch_id)
            if batch is not None and batch.started_at is None:
                batch.started_at = utcnow()
                batch.status = "running"
            job.status = "running"
            job.stage = "preparing_runtime"
            job.attempts += 1
            job.started_at = utcnow()
            job.error_message = None
            db.commit()

        try:
            with SessionLocal() as db:
                job = db.get(TaskJob, job_id)
                if job is None or job.account_id is None:
                    return
                account = db.get(Account, job.account_id)
                if account is None:
                    self._finish_job(db, job, "failed", "failed", "账号已不存在。")
                    return

                profile_id = ensure_account_runtime(db, account)
                job.profile_id = profile_id
                job.stage = "recovering_login"
                db.commit()

                execution = recover_account_login(db, account.id)
                payload = execution.to_dict()
                status = execution.status
                if status == "logged_in":
                    self._finish_job(
                        db,
                        job,
                        "succeeded",
                        "completed",
                        None,
                        result=payload,
                    )
                elif status == "failed":
                    self._finish_job(
                        db,
                        job,
                        "failed",
                        "failed",
                        execution.message,
                        result=payload,
                    )
                else:
                    self._finish_job(
                        db,
                        job,
                        "needs_attention",
                        "needs_attention",
                        execution.message,
                        result=payload,
                    )
        except AccountRuntimeNeedsAttention as exc:
            self._finish_from_new_session(job_id, "needs_attention", "preflight", str(exc))
        except AccountLoginUnsupported as exc:
            self._finish_from_new_session(job_id, "needs_attention", "unsupported", str(exc))
        except ProfileBusyError as exc:
            self._finish_from_new_session(job_id, "needs_attention", "blocked", str(exc))
        except (
            AccountRuntimeError,
            AccountLoginError,
            IXBrowserError,
            BrowserSessionError,
        ) as exc:
            self._finish_from_new_session(job_id, "failed", "failed", str(exc))
        except Exception as exc:
            self._finish_from_new_session(
                job_id,
                "failed",
                "failed",
                f"批量登录任务出现未预期错误：{exc}",
            )

    def _finish_from_new_session(
        self,
        job_id: str,
        status: str,
        stage: str,
        message: str,
    ) -> None:
        with SessionLocal() as db:
            job = db.get(TaskJob, job_id)
            if job is None:
                return
            self._finish_job(db, job, status, stage, message)

    def _finish_job(
        self,
        db: Session,
        job: TaskJob,
        status: str,
        stage: str,
        error_message: str | None,
        *,
        result: dict[str, Any] | None = None,
    ) -> None:
        job.status = status
        job.stage = stage
        job.error_message = error_message
        job.result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
        job.finished_at = utcnow()
        db.flush()
        self._refresh_batch(db, job.batch_id)
        db.commit()

    @staticmethod
    def _refresh_batch(db: Session, batch_id: str) -> None:
        batch = db.get(BatchTask, batch_id)
        if batch is None:
            return
        statuses = list(
            db.scalars(select(TaskJob.status).where(TaskJob.batch_id == batch_id)).all()
        )
        total = len(statuses)
        succeeded = sum(value == "succeeded" for value in statuses)
        failed = sum(value == "failed" for value in statuses)
        attention = sum(value in ATTENTION_JOB_STATUSES for value in statuses)
        running = sum(value == "running" for value in statuses)
        queued = sum(value == "queued" for value in statuses)

        batch.total_jobs = total
        batch.succeeded_jobs = succeeded
        batch.failed_jobs = failed
        batch.attention_jobs = attention

        if running or (queued and succeeded + failed + attention > 0):
            batch.status = "running"
            batch.finished_at = None
        elif queued:
            batch.status = "queued"
            batch.finished_at = None
        elif total > 0 and succeeded == total:
            batch.status = "succeeded"
            batch.finished_at = utcnow()
        elif attention and not failed and not succeeded:
            batch.status = "needs_attention"
            batch.finished_at = utcnow()
        elif failed and not attention and not succeeded:
            batch.status = "failed"
            batch.finished_at = utcnow()
        elif total > 0:
            batch.status = "partial"
            batch.finished_at = utcnow()


def create_login_batch(db: Session, payload: BatchLoginCreate) -> BatchTask:
    accounts, source_type, source_selection = _resolve_accounts(db, payload)
    if not accounts:
        raise BatchTaskError("当前选择中没有可执行账号。")

    ids = [account.id for account in accounts]
    active = int(
        db.scalar(
            select(func.count())
            .select_from(TaskJob)
            .where(
                TaskJob.account_id.in_(ids),
                TaskJob.job_type == "login_recover",
                TaskJob.status.in_(ACTIVE_JOB_STATUSES),
            )
        )
        or 0
    )
    if active:
        raise BatchTaskError(f"当前选择中有 {active} 个账号已经在登录任务中，请等待现有任务完成。")

    target_snapshot = [_account_snapshot(account) for account in accounts]
    batch = BatchTask(
        task_type="login_recover",
        source_type=source_type,
        source_selection_json=json.dumps(source_selection, ensure_ascii=False),
        target_snapshot_json=json.dumps(target_snapshot, ensure_ascii=False),
        status="queued",
        total_jobs=len(accounts),
    )
    db.add(batch)
    db.flush()

    job_ids: list[str] = []
    for account, snapshot in zip(accounts, target_snapshot, strict=True):
        job = TaskJob(
            batch_id=batch.id,
            account_id=account.id,
            job_type="login_recover",
            status="queued",
            stage="queued",
            profile_id=account.ix_profile_id,
            account_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        )
        db.add(job)
        db.flush()
        job_ids.append(job.id)

    db.commit()
    db.refresh(batch)
    for job_id in job_ids:
        batch_task_runner.submit_login_job(job_id)
    return get_batch(db, batch.id)


def get_batch(db: Session, batch_id: str) -> BatchTask:
    statement = (
        select(BatchTask)
        .options(selectinload(BatchTask.jobs))
        .where(BatchTask.id == batch_id)
    )
    batch = db.scalar(statement)
    if batch is None:
        raise BatchTaskError("未找到该批量任务。")
    return batch


def list_batches(db: Session, limit: int = 50) -> list[BatchTask]:
    statement = (
        select(BatchTask)
        .options(selectinload(BatchTask.jobs))
        .order_by(BatchTask.created_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    return list(db.scalars(statement).unique().all())


def _resolve_accounts(
    db: Session,
    payload: BatchLoginCreate,
) -> tuple[list[Account], str, dict[str, object]]:
    if payload.group_id is not None:
        group = db.get(AccountGroup, payload.group_id)
        if group is None:
            raise BatchTaskError("账号分组不存在。")
        accounts = list(
            db.scalars(
                select(Account)
                .where(Account.group_id == group.id, Account.enabled.is_(True))
                .order_by(Account.id)
            ).all()
        )
        return accounts, "group", {
            "group_id": group.id,
            "group_name": group.name,
        }

    requested = list(dict.fromkeys(payload.account_ids or []))
    accounts = list(
        db.scalars(
            select(Account)
            .where(Account.id.in_(requested), Account.enabled.is_(True))
            .order_by(Account.id)
        ).all()
    )
    found = {item.id for item in accounts}
    missing = [item for item in requested if item not in found]
    if missing:
        raise BatchTaskError(
            f"有 {len(missing)} 个账号不存在或已停用，请刷新账号池后重试。"
        )
    return accounts, "selection", {"account_ids": requested}


def _account_snapshot(account: Account) -> dict[str, object]:
    return {
        "account_id": account.id,
        "name": account.name,
        "platform": account.platform,
        "group_id": account.group_id,
        "proxy_id": account.proxy_id,
        "ix_profile_id": account.ix_profile_id,
    }


batch_task_runner = BatchTaskRunner(max_workers=3)
