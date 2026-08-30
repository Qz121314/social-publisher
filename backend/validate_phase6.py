from __future__ import annotations

import json
from datetime import datetime, timezone

from app.database import SessionLocal, init_db

init_db()

from app.api.tasks import confirm_job_published, confirm_not_published_and_retry
from app.models.account import BrowserProfile
from app.models.channel import Channel
from app.models.content import ContentItem, PublishJob
from app.models.publishing import PublishAttempt, PublishAttemptEvent
from app.services.attempt_timeline import _backfill_metrics_and_finalize, record_attempt_event
from app.services.platforms.base import emit_platform_progress, platform_progress
from app.services.platforms.facebook_timeline import TimelineFacebookFlowAdapter
from app.services.platforms.registry import get_platform_adapter
from app.services.publishing_domain import create_publish_plan


PROFILE_A = 990061
PROFILE_B = 990062
NOW = datetime.now(timezone.utc)


with SessionLocal() as db:
    for profile_id, name in ((PROFILE_A, "CI Phase 6 A"), (PROFILE_B, "CI Phase 6 B")):
        profile = db.get(BrowserProfile, profile_id)
        if profile is None:
            db.add(
                BrowserProfile(
                    profile_id=profile_id,
                    name=name,
                    group_name="Phase 6",
                    raw_json="{}",
                    is_available=True,
                )
            )
    db.flush()

    channel_a = Channel(
        profile_id=PROFILE_A,
        platform="facebook",
        target_id="phase6-target-a",
        target_name="Phase 6 Target A",
        target_type="page",
        target_url="https://www.facebook.com/phase6-target-a",
        enabled=True,
        health_status="healthy",
    )
    channel_b = Channel(
        profile_id=PROFILE_B,
        platform="facebook",
        target_id="phase6-target-b",
        target_name="Phase 6 Target B",
        target_type="page",
        target_url="https://www.facebook.com/phase6-target-b",
        enabled=True,
        health_status="healthy",
    )
    content = ContentItem(platform="facebook", text="Phase 6 review test", status="draft")
    db.add_all([channel_a, channel_b, content])
    db.commit()
    db.refresh(channel_a)
    db.refresh(channel_b)
    db.refresh(content)

    plan = create_publish_plan(
        db,
        content_id=content.id,
        channel_ids=[channel_a.id, channel_b.id],
        publish_mode="draft",
        timezone_name="UTC",
        scheduled_at=None,
        interval_seconds=0,
        flow_revision_id=None,
    )
    job_a_id = plan.jobs[0].id
    job_b_id = plan.jobs[1].id

    job_a = db.get(PublishJob, job_a_id)
    job_b = db.get(PublishJob, job_b_id)
    assert job_a is not None and job_b is not None

    job_a.status = "needs_review"
    job_a.stage = "verifying"
    job_a.error_message = "Post click happened but verification was uncertain."
    attempt_a = PublishAttempt(
        job_id=job_a.id,
        attempt_no=1,
        status="needs_review",
        stage="verifying",
        started_at=NOW,
        submitted_at=NOW,
        finished_at=NOW,
        result_json=json.dumps({"submitted": True, "verified": False}),
        error_message=job_a.error_message,
    )
    db.add(attempt_a)

    job_b.status = "needs_review"
    job_b.stage = "verifying"
    job_b.error_message = "Post click happened but verification was uncertain."
    attempt_b = PublishAttempt(
        job_id=job_b.id,
        attempt_no=1,
        status="needs_review",
        stage="verifying",
        started_at=NOW,
        submitted_at=NOW,
        finished_at=NOW,
        result_json=json.dumps({"submitted": True, "verified": False}),
        error_message=job_b.error_message,
    )
    db.add(attempt_b)
    db.commit()
    db.refresh(attempt_a)
    db.refresh(attempt_b)
    attempt_a_id = attempt_a.id
    attempt_b_id = attempt_b.id


# Timeline events are ordered, persist details, and update the current stage.
record_attempt_event(attempt_a_id, "checking_login", "Facebook login ok")
record_attempt_event(
    attempt_a_id,
    "checking_identity",
    "actor gate ok",
    {"target_id": "phase6-target-a"},
)
with SessionLocal() as db:
    events = list(
        db.scalars(
            __import__("sqlalchemy").select(PublishAttemptEvent)
            .where(PublishAttemptEvent.attempt_id == attempt_a_id)
            .order_by(PublishAttemptEvent.sequence)
        ).all()
    )
    assert [item.sequence for item in events] == [1, 2]
    assert events[1].stage == "checking_identity"
    assert json.loads(events[1].details_json or "{}")["target_id"] == "phase6-target-a"


# ContextVar progress stays explicit and isolated from the adapter singleton.
captured: list[tuple[str, str]] = []
with platform_progress(lambda stage, message, details: captured.append((stage, message))):
    emit_platform_progress("opening_composer", "composer opened")
assert captured == [("opening_composer", "composer opened")]
assert isinstance(get_platform_adapter("facebook"), TimelineFacebookFlowAdapter)


# Metrics are backfilled from the instrumented platform result and completion is
# represented as a durable Timeline event.
with SessionLocal() as db:
    attempt = db.get(PublishAttempt, attempt_a_id)
    assert attempt is not None
    attempt.status = "succeeded"
    attempt.stage = "completed"
    attempt.result_json = json.dumps(
        {
            "submitted": True,
            "verified": True,
            "media_duration_ms": 1234,
            "verification_duration_ms": 456,
        }
    )
    db.commit()
_backfill_metrics_and_finalize(attempt_a_id)
with SessionLocal() as db:
    attempt = db.get(PublishAttempt, attempt_a_id)
    assert attempt is not None
    assert attempt.media_ms == 1234
    assert attempt.verification_ms == 456
    assert db.scalar(
        __import__("sqlalchemy").select(PublishAttemptEvent.id).where(
            PublishAttemptEvent.attempt_id == attempt_a_id,
            PublishAttemptEvent.stage == "completed",
        )
    )

# Restore the uncertain state to test the real manual-review endpoint.
with SessionLocal() as db:
    job = db.get(PublishJob, job_a_id)
    attempt = db.get(PublishAttempt, attempt_a_id)
    assert job is not None and attempt is not None
    job.status = "needs_review"
    job.stage = "verifying"
    job.error_message = "uncertain"
    attempt.status = "needs_review"
    attempt.stage = "verifying"
    attempt.error_message = "uncertain"
    db.commit()

with SessionLocal() as db:
    reviewed = confirm_job_published(job_a_id, db)
    assert reviewed.status == "succeeded"
    latest = reviewed.attempts[-1]
    assert latest.status == "succeeded"
    assert latest.stage == "manual_confirmed_published"
    parsed = json.loads(latest.result_json or "{}")
    assert parsed["manual_review"]["decision"] == "confirmed_published"


# The alternative decision is explicit: mark the uncertain Attempt as not
# published, return the Job to scheduled, and let the Scheduler create a new
# Attempt instead of replaying needs_review automatically.
with SessionLocal() as db:
    retried = confirm_not_published_and_retry(job_b_id, db)
    assert retried.status == "scheduled"
    assert retried.stage == "scheduled"
    latest = retried.attempts[-1]
    assert latest.status == "failed"
    assert latest.stage == "manual_confirmed_not_published"
    assert any(event.stage == "manual_confirmed_not_published" for event in latest.events)

print("phase6 timeline manual review ok")
