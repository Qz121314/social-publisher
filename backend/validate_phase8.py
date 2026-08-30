from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal, init_db

init_db()

from app.models.account import BrowserProfile
from app.models.channel import Channel
from app.models.content import ContentItem, MediaAsset
from app.models.flow import Flow
from app.services.platforms.base import (
    PlatformAdapter,
    PlatformContent,
    PlatformMedia,
    PlatformPublishError,
    PlatformValidationError,
    platform_progress,
)
from app.services.platforms.instagram_composite import (
    InstagramCompositeAdapter,
    InstagramIdentityComponent,
)
from app.services.platforms.registry import get_platform_adapter, list_platforms
from app.services.publishing_domain import create_publish_plan


# Registry and Flow bootstrap expose Instagram without changing the top-level domain model.
adapter = get_platform_adapter("instagram")
assert isinstance(adapter, InstagramCompositeAdapter)
assert isinstance(adapter, PlatformAdapter)
assert any(item["name"] == "instagram" for item in list_platforms())
with SessionLocal() as db:
    flow = db.scalar(select(Flow).where(Flow.platform == "instagram", Flow.key == "feed_post"))
    assert flow is not None and flow.current_revision_id
    assert len(flow.revisions[0].steps) == 11


# Feed Post requires media and uses the same shared content contract.
try:
    adapter.validate_content(PlatformContent(text="caption only", media=()))
except PlatformValidationError:
    pass
else:
    raise AssertionError("Instagram Feed Post must reject caption-only content")

media = PlatformMedia(
    media_type="image",
    path=Path("/tmp/phase8-image.jpg"),
    mime_type="image/jpeg",
    original_name="phase8-image.jpg",
)
adapter.validate_content(PlatformContent(text="Phase 8 Instagram", media=(media,)))


# Stable account identity is numeric ds_user_id; username is navigation/display only.
class CookieDriver:
    current_url = "https://www.instagram.com/"
    title = "Instagram"

    def __init__(self, actor: str) -> None:
        self.actor = actor

    def get_cookie(self, name: str):
        if name == "ds_user_id":
            return {"value": self.actor}
        if name == "sessionid":
            return {"value": "session"}
        return None


identity = InstagramIdentityComponent()
content = PlatformContent(
    text="Phase 8 Instagram",
    media=(media,),
    target_type="profile",
    target_id="880081",
    target_name="phase8user",
    target_url="https://www.instagram.com/phase8user/",
)
identity.verify_actor(CookieDriver("880081"), content, stage="test")
try:
    identity.verify_actor(CookieDriver("999999"), content, stage="test")
except PlatformPublishError:
    pass
else:
    raise AssertionError("Instagram actor gate must reject a mismatched ds_user_id")
assert identity._username_from_profile_url("https://www.instagram.com/phase8user/") == "phase8user"
assert identity._username_from_profile_url("https://www.instagram.com/explore/") is None


# Formal Instagram Plan/Job uses the same immutable Channel + Flow Revision snapshots.
PROFILE_ID = 990081
with SessionLocal() as db:
    profile = db.get(BrowserProfile, PROFILE_ID)
    if profile is None:
        profile = BrowserProfile(
            profile_id=PROFILE_ID,
            name="CI Phase 8 Instagram",
            group_name="Phase 8",
            raw_json="{}",
            is_available=True,
        )
        db.add(profile)
        db.flush()

    channel = Channel(
        profile_id=PROFILE_ID,
        platform="instagram",
        target_id="880081",
        target_name="phase8user",
        target_type="profile",
        target_url="https://www.instagram.com/phase8user/",
        enabled=True,
        health_status="healthy",
    )
    asset = ContentItem(platform="instagram", text="Phase 8 Instagram", status="draft")
    db.add_all([channel, asset])
    db.flush()
    db.add(
        MediaAsset(
            content_id=asset.id,
            media_type="image",
            original_name="phase8-image.jpg",
            stored_name=f"phase8-{asset.id}.jpg",
            mime_type="image/jpeg",
            file_size=123,
            sort_order=0,
        )
    )
    db.commit()
    db.refresh(channel)
    db.refresh(asset)

    plan = create_publish_plan(
        db,
        content_id=asset.id,
        channel_ids=[channel.id],
        publish_mode="draft",
        timezone_name="UTC",
        scheduled_at=None,
        interval_seconds=0,
        flow_revision_id=None,
    )
    assert plan.flow_revision.flow.platform == "instagram"
    assert len(plan.jobs) == 1
    job = plan.jobs[0]
    snapshot = json.loads(job.channel_snapshot_json)
    assert snapshot["platform"] == "instagram"
    assert snapshot["target_id"] == "880081"
    assert snapshot["profile_id"] == PROFILE_ID


# No-browser orchestration contract: components own the flow and Timeline stages remain emitted.
class FakeDriver:
    current_url = "https://www.instagram.com/"
    title = "Instagram"


class FakeIdentity:
    def __init__(self) -> None:
        self.gates: list[str] = []

    def check_login(self, driver):
        return {"logged_in": True, "checkpoint": False, "actor_id": "880081"}

    def verify_actor(self, driver, content, *, stage: str):
        assert content.target_id == "880081"
        self.gates.append(stage)


class FakeNavigation:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def open_home(self, driver):
        self.calls.append("navigate")


class FakeComposer:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def open(self, driver):
        self.calls.append("open")
        return object()

    def upload(self, driver, media):
        self.calls.append("upload")
        assert len(tuple(media)) == 1

    def wait_caption_step(self, driver):
        self.calls.append("caption_step")
        return object()

    def write_caption(self, driver, root, text):
        self.calls.append("caption")
        assert text == "Phase 8 Instagram"

    def wait_share_button(self, driver):
        self.calls.append("ready")
        return object()

    def _safe_click(self, driver, button):
        self.calls.append("share")


class FakeVerifier:
    def __init__(self, calls: list[str], verified: bool = True) -> None:
        self.calls = calls
        self.verified = verified

    def verify(self, driver):
        self.calls.append("verify")
        return {
            "verified": self.verified,
            "published_url": "https://www.instagram.com/p/phase8/" if self.verified else None,
            "message": "ok" if self.verified else "uncertain",
        }


composed = InstagramCompositeAdapter()
calls: list[str] = []
fake_identity = FakeIdentity()
composed.identity = fake_identity
composed.navigation = FakeNavigation(calls)
composed.composer = FakeComposer(calls)
composed.verifier = FakeVerifier(calls)
progress: list[str] = []
with platform_progress(lambda stage, message, details: progress.append(stage)):
    result = composed.publish(FakeDriver(), content)
assert result["submitted"] is True and result["verified"] is True
assert calls == ["navigate", "open", "upload", "caption_step", "caption", "ready", "share", "verify"]
assert len(fake_identity.gates) == 3
assert "checking_identity" in progress
assert "uploading_media" in progress
assert "submitting" in progress
assert "verifying" in progress

# A Share that cannot be independently verified stays submitted+unverified so the Worker
# maps it to needs_review instead of automatically replaying the post.
composed.verifier = FakeVerifier(calls := [], verified=False)
composed.navigation = FakeNavigation(calls)
composed.composer = FakeComposer(calls)
uncertain = composed.publish(FakeDriver(), content)
assert uncertain["submitted"] is True
assert uncertain["verified"] is False

print("phase8 instagram adapter contract ok")
