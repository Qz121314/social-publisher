from app.database import SessionLocal, init_db

init_db()

from app.models.account import BrowserProfile
from app.models.channel import Channel
from app.models.content import ContentItem
from app.services.publishing_domain import create_publish_plan
from app.services.worker import WorkerManager


PROFILE_ID = 990001

with SessionLocal() as db:
    profile = db.get(BrowserProfile, PROFILE_ID)
    if profile is None:
        profile = BrowserProfile(
            profile_id=PROFILE_ID,
            name="CI Phase 3",
            group_name="CI",
            raw_json="{}",
            is_available=True,
        )
        db.add(profile)
        db.flush()

    channel = Channel(
        profile_id=PROFILE_ID,
        platform="facebook",
        target_id="phase3-ci-target",
        target_name="Phase 3 CI Target",
        target_type="page",
        target_url="https://www.facebook.com/phase3-ci-target",
        enabled=True,
        health_status="healthy",
    )
    db.add(channel)
    content = ContentItem(platform="facebook", text="Phase 3 formal execution snapshot", status="draft")
    db.add(content)
    db.commit()
    db.refresh(channel)
    db.refresh(content)

    plan = create_publish_plan(
        db,
        content_id=content.id,
        channel_ids=[channel.id],
        publish_mode="immediate",
        timezone_name="UTC",
        scheduled_at=None,
        interval_seconds=0,
        flow_revision_id=None,
    )
    assert len(plan.jobs) == 1
    job = plan.jobs[0]
    assert job.plan_id == plan.id
    assert job.channel_id == channel.id
    assert job.profile_id is None
    assert job.content_id is None

    manager = WorkerManager(max_workers=1)
    try:
        assert manager._resolve_job_profile_id(db, job) == PROFILE_ID
        platform, payload = manager._load_platform_content(job.id)
        assert platform == "facebook"
        assert payload.text == "Phase 3 formal execution snapshot"
        assert payload.target_id == "phase3-ci-target"
        assert payload.target_url == "https://www.facebook.com/phase3-ci-target"
    finally:
        manager.shutdown(wait=False)

print("phase3 formal execution bridge ok")
