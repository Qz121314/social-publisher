import json
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import inspect

from app.database import SessionLocal, engine, init_db
from app.main import app
from app.models.account import Account, AccountGroup
from app.models.batch_task import BatchTask, TaskJob
from app.schemas.batch_task import BatchLoginCreate
from app.services.account_runtime import AccountRuntimeNeedsAttention, ensure_account_runtime
from app.services.batch_tasks import batch_task_runner, create_login_batch


def main() -> None:
    init_db()
    inspector = inspect(engine)
    assert inspector.has_table("batch_tasks")
    assert inspector.has_table("task_jobs")

    paths = set(app.openapi()["paths"])
    assert "/api/batch-tasks/login" in paths
    assert "/api/batch-tasks" in paths
    assert "/api/batch-tasks/{batch_id}" in paths

    try:
        BatchLoginCreate()
    except ValidationError:
        pass
    else:
        raise AssertionError("batch login requires group_id or account_ids")

    try:
        BatchLoginCreate(group_id=1, account_ids=[1])
    except ValidationError:
        pass
    else:
        raise AssertionError("batch login target modes must be mutually exclusive")

    suffix = uuid4().hex[:10]
    submitted: list[str] = []
    original_submit = batch_task_runner.submit_login_job
    batch_task_runner.submit_login_job = submitted.append  # type: ignore[method-assign]
    try:
        with SessionLocal() as db:
            group = AccountGroup(name=f"Batch Login {suffix}")
            db.add(group)
            db.flush()
            first = Account(
                name=f"FB Batch A {suffix}",
                platform="facebook",
                ix_profile_id=None,
                group_id=group.id,
                status="prepared",
            )
            second = Account(
                name=f"FB Batch B {suffix}",
                platform="facebook",
                ix_profile_id=None,
                group_id=group.id,
                status="prepared",
            )
            db.add_all([first, second])
            db.commit()

            batch = create_login_batch(db, BatchLoginCreate(group_id=group.id))
            assert batch.total_jobs == 2
            assert len(batch.jobs) == 2
            assert len(submitted) == 2
            frozen = json.loads(batch.target_snapshot_json)
            assert [item["account_id"] for item in frozen] == [first.id, second.id]
            assert all(item["ix_profile_id"] is None for item in frozen)

            third = Account(
                name=f"FB Batch C {suffix}",
                platform="facebook",
                ix_profile_id=None,
                group_id=group.id,
                status="prepared",
            )
            db.add(third)
            db.commit()
            db.refresh(batch)
            assert len(json.loads(batch.target_snapshot_json)) == 2, "target snapshot must stay frozen"

            try:
                ensure_account_runtime(db, first)
            except AccountRuntimeNeedsAttention as exc:
                assert "SOCKS5" in str(exc)
            else:
                raise AssertionError("prepared account without IP must fail before touching iXBrowser")

            batch_id = batch.id
            db.delete(db.get(BatchTask, batch_id))
            db.delete(first)
            db.delete(second)
            db.delete(third)
            db.delete(group)
            db.commit()
            assert db.get(BatchTask, batch_id) is None
            assert not db.query(TaskJob).filter(TaskJob.batch_id == batch_id).count()
    finally:
        batch_task_runner.submit_login_job = original_submit  # type: ignore[method-assign]

    print("phase10 batch login foundation ok")


if __name__ == "__main__":
    main()
