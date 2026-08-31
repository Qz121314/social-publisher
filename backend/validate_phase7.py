from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.platforms.base import (
    PlatformAdapter,
    PlatformContent,
    PlatformMedia,
    platform_progress,
)
from app.services.platforms.facebook_composite import FacebookCompositeAdapter
from app.services.platforms.facebook_surface import _ACTIVE_SURFACE_CONTENT
from app.services.platforms.facebook_target import _ACTIVE_PUBLISH_CONTENT
from app.services.platforms.facebook_timeline import TimelineFacebookFlowAdapter
from app.services.platforms.registry import get_platform_adapter


class FakeDriver:
    current_url = "https://www.facebook.com/phase7-target"
    title = "Phase 7 Facebook"


class FakePrimitives:
    """No-browser contract test for the Phase 7 orchestration boundary."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._expected_content: PlatformContent | None = None

    def expect(self, content: PlatformContent) -> None:
        self._expected_content = content

    def _scope_ok(self) -> None:
        assert self._expected_content is not None
        assert _ACTIVE_PUBLISH_CONTENT.get() is self._expected_content
        assert _ACTIVE_SURFACE_CONTENT.get() is self._expected_content

    def check_login(self, driver: Any) -> dict[str, Any]:
        self._scope_ok()
        self.calls.append("identity.check_login")
        return {
            "platform": "facebook",
            "logged_in": True,
            "needs_login": False,
            "checkpoint": False,
            "current_url": driver.current_url,
            "title": driver.title,
        }

    def _assert_target_actor(
        self,
        driver: Any,
        content: PlatformContent,
        *,
        stage: str,
    ) -> None:
        self._scope_ok()
        assert content is self._expected_content
        self.calls.append(f"identity.verify:{stage}")

    def current_actor_id(self, driver: Any) -> str:
        self._scope_ok()
        self.calls.append("identity.current_actor")
        return str(self._expected_content.target_id)

    def _navigate_to_target(self, driver: Any, content: PlatformContent) -> None:
        self._scope_ok()
        assert content is self._expected_content
        self.calls.append("navigation.open_target")

    def _open_composer(self, driver: Any) -> object:
        self._scope_ok()
        self.calls.append("composer.open")
        return object()

    def confirm_composer_entry(self, driver: Any, content: PlatformContent) -> dict[str, Any]:
        self._scope_ok()
        assert content is self._expected_content
        self.calls.append("composer.confirm")
        return {"confirmed": True, "current_actor_id": content.target_id}

    def _fill_text(self, composer: Any, text: str) -> None:
        self._scope_ok()
        assert text == "Phase 7 composition ✅"
        self.calls.append("text.write")

    def _upload_media(self, driver: Any, composer: Any, media: Any) -> None:
        self._scope_ok()
        assert len(tuple(media)) == 1
        self.calls.append("media.upload")

    def _wait_post_ready(self, driver: Any, composer: Any) -> object:
        self._scope_ok()
        self.calls.append("submit.wait_ready")
        return object()

    def _safe_click(self, driver: Any, button: Any) -> None:
        self._scope_ok()
        self.calls.append("submit.click")

    def _resolve_post_submit_interstitial(
        self,
        driver: Any,
        composer: Any,
        content: PlatformContent,
    ) -> dict[str, Any]:
        self._scope_ok()
        assert content is self._expected_content
        self.calls.append("submit.resolve_interstitial")
        return {"handled": False, "reason": "no_interstitial"}

    def _wait_composer_closed(self, driver: Any, composer: Any) -> None:
        self._scope_ok()
        self.calls.append("verifier.wait_closed")

    def _verify_submission(self, driver: Any, content: PlatformContent) -> dict[str, Any]:
        self._scope_ok()
        assert content is self._expected_content
        self.calls.append("verifier.verify")
        return {
            "verified": True,
            "published_url": "https://www.facebook.com/phase7-target/posts/1",
            "message": "verified",
        }


production = get_platform_adapter("facebook")
assert isinstance(production, FacebookCompositeAdapter)
assert production.__class__.__bases__ == (PlatformAdapter,)
assert not any(
    name in {base.__name__ for base in production.__class__.__mro__}
    for name in {
        "AdaptiveFacebookAdapter",
        "TargetActorFacebookAdapter",
        "FacebookSurfaceAdapter",
        "PreciseFacebookSurfaceAdapter",
        "UnifiedFacebookFlowAdapter",
        "ConfigurableFacebookFlowAdapter",
        "UnicodeFacebookFlowAdapter",
    }
)

assert TimelineFacebookFlowAdapter is FacebookCompositeAdapter

component_names = {
    production.components.identity.__class__.__name__,
    production.components.navigation.__class__.__name__,
    production.components.composer.__class__.__name__,
    production.components.text.__class__.__name__,
    production.components.media.__class__.__name__,
    production.components.submit.__class__.__name__,
    production.components.verifier.__class__.__name__,
    production.components.diagnostics.__class__.__name__,
    production.components.config.__class__.__name__,
}
assert component_names == {
    "FacebookIdentityComponent",
    "FacebookNavigationComponent",
    "FacebookComposerComponent",
    "FacebookTextInputComponent",
    "FacebookMediaComponent",
    "FacebookSubmitComponent",
    "FacebookVerifierComponent",
    "FacebookDiagnosticsComponent",
    "FacebookConfigComponent",
}
assert production.components.config.keyword_groups().get("entry_keywords")
assert production.components.config.keyword_groups().get("publish_original_keywords")

fake = FakePrimitives()
adapter = FacebookCompositeAdapter(primitives=fake)  # type: ignore[arg-type]
content = PlatformContent(
    text="Phase 7 composition ✅",
    media=(
        PlatformMedia(
            media_type="image",
            path=Path("phase7-fake.jpg"),
            mime_type="image/jpeg",
            original_name="phase7-fake.jpg",
        ),
    ),
    target_type="page",
    target_id="phase7-target",
    target_name="Phase 7 Target",
    target_url="https://www.facebook.com/phase7-target",
)
fake.expect(content)

progress: list[str] = []
with platform_progress(lambda stage, message, details: progress.append(stage)):
    result = adapter.publish(FakeDriver(), content)  # type: ignore[arg-type]

assert result["submitted"] is True
assert result["verified"] is True
assert result["published_url"].endswith("/posts/1")
assert isinstance(result["media_duration_ms"], int)
assert isinstance(result["verification_duration_ms"], int)
assert fake.calls == [
    "identity.check_login",
    "navigation.open_target",
    "composer.open",
    "text.write",
    "media.upload",
    "submit.wait_ready",
    "submit.click",
    "submit.resolve_interstitial",
    "verifier.wait_closed",
    "verifier.verify",
    "identity.current_actor",
]
assert progress == [
    "checking_login",
    "checking_login",
    "checking_identity",
    "navigating",
    "checking_identity",
    "opening_composer",
    "opening_composer",
    "writing_text",
    "writing_text",
    "uploading_media",
    "waiting_media",
    "advancing",
    "checking_identity",
    "ready_to_submit",
    "submitting",
    "submitting",
    "verifying",
    "verifying",
    "verifying",
]

assert _ACTIVE_PUBLISH_CONTENT.get() is None
assert _ACTIVE_SURFACE_CONTENT.get() is None

fake.calls.clear()
fake.expect(content)
confirmed = adapter.confirm_composer_entry(FakeDriver(), content)  # type: ignore[arg-type]
assert confirmed["confirmed"] is True
assert fake.calls == ["composer.confirm"]
assert _ACTIVE_PUBLISH_CONTENT.get() is None
assert _ACTIVE_SURFACE_CONTENT.get() is None

print("phase7 facebook composition ok")
