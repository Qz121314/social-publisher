from datetime import datetime, timedelta, timezone

from app.database import SessionLocal, init_db

init_db()

from app.models.account import BrowserProfile
from app.models.channel import Channel
from app.models.content import ContentItem, PublishJob
from app.models.publishing import PublishPlan
from app.services.publishing_domain import create_publish_plan
from app.services.scheduler import PublishScheduler


PROFILE_ID = 990004
NOW = datetime.now(timezone.utc)


class FakeWorker:
    def __init__(self) -> None:
        self.submitted: list[str] = []

    def stats(self) -> dict[str, int]:
        return {"max_workers": 20, "active_tasks": 0}

    def submit_publish_job(self, job_id: str):
        with SessionLocal() as db:
            job = db.get(PublishJob, job_id)
            assert job is not None
            assert job.status == "scheduled"
            job.status = "queued"
            job.stage = "queued"
            if job.plan_id:
                plan = db.get(PublishPlan, job.plan_id)
                if plan is not None:
                    plan.status = "queued"
            db.commit()
        self.submitted.append(job_id)
        return object()


with SessionLocal() as db:
    profile = db.get(BrowserProfile, PROFILE_ID)
    if profile is None:
        profile = BrowserProfile(
            profile_id=PROFILE_ID,
            name="CI Phase 4",
            group_name="CI",
            raw_json="{}",
            is_available=True,
        )
        db.add(profile)
        db.flush()

    channel = Channel(
        profile_id=PROFILE_ID,
        platform="facebook",
        target_id="phase4-ci-target",
        target_name="Phase 4 CI Target",
        target_type="page",
        target_url="https://www.facebook.com/phase4-ci-target",
        enabled=True,
        health_status="healthy",
    )
    db.add(channel)
    immediate_content = ContentItem(platform="facebook", text="Phase 4 immediate", status="draft")
    future_content = ContentItem(platform="facebook", text="Phase 4 scheduled", status="draft")
    db.add_all([immediate_content, future_content])
    db.commit()
    db.refresh(channel)
    db.refresh(immediate_content)
    db.refresh(future_content)

    immediate_plan = create_publish_plan(
        db,
        content_id=immediate_content.id,
        channel_ids=[channel.id],
        publish_mode="immediate",
        timezone_name="UTC",
        scheduled_at=None,
        interval_seconds=0,
        flow_revision_id=None,
    )
    future_time = NOW + timedelta(hours=6)
    future_plan = create_publish_plan(
        db,
        content_id=future_content.id,
        channel_ids=[channel.id],
        publish_mode="scheduled",
        timezone_name="UTC",
        scheduled_at=future_time,
        interval_seconds=0,
        flow_revision_id=None,
    )
    immediate_job_id = immediate_plan.jobs[0].id
    future_job_id = future_plan.jobs[0].id

fake = FakeWorker()
scheduler = PublishScheduler(fake, poll_interval_seconds=1, batch_size=20)  # type: ignore[arg-type]
first = scheduler.run_once(now=NOW + timedelta(seconds=5))
assert immediate_job_id in fake.submitted
assert future_job_id not in fake.submitted
assert first["dispatched"] >= 1

with SessionLocal() as db:
    immediate_job = db.get(PublishJob, immediate_job_id)
    future_job = db.get(PublishJob, future_job_id)
    assert immediate_job is not None and immediate_job.status == "queued"
    assert future_job is not None and future_job.status == "scheduled"

second = scheduler.run_once(now=future_time + timedelta(seconds=1))
assert future_job_id in fake.submitted
assert second["dispatched"] >= 1

# Simulate a backend restart after a job was queued but before it ran. Runtime
# recovery must return formal queued jobs to SQLite scheduled state so a new
# scheduler process can discover them again.
from app.services.worker import worker_manager
worker_manager.recover_runtime_state()

with SessionLocal() as db:
    immediate_job = db.get(PublishJob, immediate_job_id)
    future_job = db.get(PublishJob, future_job_id)
    assert immediate_job is not None and immediate_job.status == "scheduled"
    assert future_job is not None and future_job.status == "scheduled"

restart_fake = FakeWorker()
restart_scheduler = PublishScheduler(restart_fake, poll_interval_seconds=1, batch_size=20)  # type: ignore[arg-type]
restart = restart_scheduler.run_once(now=future_time + timedelta(seconds=2))
assert immediate_job_id in restart_fake.submitted
assert future_job_id in restart_fake.submitted
assert restart["dispatched"] >= 2

print("phase4 sqlite scheduler ok")
