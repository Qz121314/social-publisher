from datetime import datetime, timedelta, timezone
from threading import Thread

from app.database import SessionLocal, init_db

init_db()

from app.models.account import BrowserProfile
from app.models.channel import Channel
from app.models.content import ContentItem, PublishJob
from app.models.publishing import PublishPlan
from app.services.publishing_domain import create_publish_plan
from app.services.runtime_settings import (
    get_warm_session_ttl_seconds,
    set_warm_session_ttl_seconds,
)
from app.services.scheduler import PublishScheduler


NOW = datetime.now(timezone.utc)
PROFILE_A = 990051
PROFILE_B = 990052


class FakeWorker:
    def __init__(self) -> None:
        self.submitted: list[str] = []

    def stats(self) -> dict[str, int]:
        return {"max_workers": 3, "active_tasks": 0}

    def submit_publish_job(self, job_id: str):
        with SessionLocal() as db:
            job = db.get(PublishJob, job_id)
            assert job is not None and job.status == "scheduled"
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
    for profile_id, name in ((PROFILE_A, "CI Batch A"), (PROFILE_B, "CI Batch B")):
        profile = db.get(BrowserProfile, profile_id)
        if profile is None:
            db.add(
                BrowserProfile(
                    profile_id=profile_id,
                    name=name,
                    group_id=505,
                    group_name="Phase 5 Batch Group",
                    raw_json="{}",
                    is_available=True,
                )
            )
    db.flush()

    channels = [
        Channel(
            profile_id=PROFILE_A,
            platform="facebook",
            target_id="phase5-a-1",
            target_name="Phase 5 A1",
            target_type="page",
            target_url="https://www.facebook.com/phase5-a-1",
            enabled=True,
            health_status="healthy",
        ),
        Channel(
            profile_id=PROFILE_A,
            platform="facebook",
            target_id="phase5-a-2",
            target_name="Phase 5 A2",
            target_type="page",
            target_url="https://www.facebook.com/phase5-a-2",
            enabled=True,
            health_status="healthy",
        ),
        Channel(
            profile_id=PROFILE_B,
            platform="facebook",
            target_id="phase5-b-1",
            target_name="Phase 5 B1",
            target_type="page",
            target_url="https://www.facebook.com/phase5-b-1",
            enabled=True,
            health_status="healthy",
        ),
    ]
    db.add_all(channels)
    content = ContentItem(platform="facebook", text="Phase 5 grouped batch", status="draft")
    db.add(content)
    db.commit()
    for channel in channels:
        db.refresh(channel)
    db.refresh(content)

    plan = create_publish_plan(
        db,
        content_id=content.id,
        channel_ids=[channel.id for channel in channels],
        publish_mode="immediate",
        timezone_name="UTC",
        scheduled_at=None,
        interval_seconds=7,
        flow_revision_id=None,
    )
    assert len(plan.jobs) == 3
    job_ids = [job.id for job in plan.jobs]
    scheduled_times = [job.scheduled_at for job in plan.jobs]
    assert scheduled_times[0] is not None
    assert scheduled_times[1] is not None
    assert scheduled_times[2] is not None
    assert int((scheduled_times[1] - scheduled_times[0]).total_seconds()) == 7
    assert int((scheduled_times[2] - scheduled_times[1]).total_seconds()) == 7

fake = FakeWorker()
scheduler = PublishScheduler(fake, poll_interval_seconds=1, batch_size=10)  # type: ignore[arg-type]
first = scheduler.run_once(now=NOW + timedelta(minutes=5))
assert first["dispatched"] == 2, first
assert first["deferred_busy_profiles"] >= 1, first
assert job_ids[0] in fake.submitted
assert job_ids[1] not in fake.submitted
assert job_ids[2] in fake.submitted

# Finish the two different-profile jobs. The remaining job on PROFILE_A should
# become eligible on the next scheduler tick, proving same-profile serialization
# without sacrificing cross-profile concurrency.
with SessionLocal() as db:
    for job_id in (job_ids[0], job_ids[2]):
        job = db.get(PublishJob, job_id)
        assert job is not None
        job.status = "succeeded"
        job.stage = "completed"
    db.commit()

second = scheduler.run_once(now=NOW + timedelta(minutes=6))
assert second["dispatched"] == 1, second
assert job_ids[1] in fake.submitted

# Runtime Warm Session TTL must persist in SQLite rather than living only in the
# current Python process.
with SessionLocal() as db:
    previous_ttl = get_warm_session_ttl_seconds(db)
    set_warm_session_ttl_seconds(2, db)
with SessionLocal() as db:
    assert get_warm_session_ttl_seconds(db) == 2

# Validate the managed warm lifecycle without opening iXBrowser or Selenium.
import app.services.browser_sessions as browser_module
from app.services.browser_sessions import BrowserSession, BrowserSessionManager


class FakeService:
    def stop(self) -> None:
        pass


class FakeDriver:
    current_url = "https://www.facebook.com/"
    title = "Facebook"
    window_handles = ["one"]
    service = FakeService()


class FakeIXBrowserService:
    closed: list[int] = []

    def close_profile(self, profile_id: int) -> dict[str, object]:
        self.closed.append(profile_id)
        return {"profile_id": profile_id, "closed": True}


manager = BrowserSessionManager()
warm_profile_id = 990059
manager._sessions[warm_profile_id] = BrowserSession(  # noqa: SLF001 - CI lifecycle probe
    profile_id=warm_profile_id,
    driver=FakeDriver(),  # type: ignore[arg-type]
    debugging_address="127.0.0.1:9999",
    opened_at=NOW,
    last_used_at=NOW,
    managed_by_worker=True,
)

result_holder: list[dict[str, object]] = []


def worker_cleanup() -> None:
    result_holder.append(manager.close(warm_profile_id))


worker_thread = Thread(target=worker_cleanup, name="social-publisher-worker-phase5-ci")
worker_thread.start()
worker_thread.join()
assert result_holder and result_holder[0]["warm"] is True
assert warm_profile_id in manager._sessions  # noqa: SLF001
manager._sessions[warm_profile_id].warm_until = NOW - timedelta(seconds=1)  # noqa: SLF001

original_ix = browser_module.IXBrowserService
browser_module.IXBrowserService = FakeIXBrowserService  # type: ignore[assignment]
try:
    assert manager.expire_warm_sessions() == 1
    assert warm_profile_id not in manager._sessions  # noqa: SLF001
    assert warm_profile_id in FakeIXBrowserService.closed
finally:
    browser_module.IXBrowserService = original_ix
    with SessionLocal() as db:
        set_warm_session_ttl_seconds(previous_ttl, db)

print("phase5 batch scheduling and warm session ttl ok")
