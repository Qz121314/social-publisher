from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from selenium.webdriver import Chrome
from selenium.webdriver.remote.webelement import WebElement

from app.services.platforms.base import PlatformContent, PlatformMedia
from app.services.platforms.facebook_flow_config import load_facebook_flow
from app.services.platforms.facebook_unicode_flow import UnicodeFacebookFlowAdapter


class FacebookIdentityComponent:
    """Login state and actor-ID authorization gates."""

    def __init__(self, primitives: UnicodeFacebookFlowAdapter) -> None:
        self._primitives = primitives

    def check_login(self, driver: Chrome) -> dict[str, Any]:
        return self._primitives.check_login(driver)

    def verify_actor(
        self,
        driver: Chrome,
        content: PlatformContent,
        *,
        stage: str,
    ) -> None:
        self._primitives._assert_target_actor(driver, content, stage=stage)

    def current_actor_id(self, driver: Chrome) -> str | None:
        return self._primitives.current_actor_id(driver)


class FacebookNavigationComponent:
    """Prepare the configured actor and navigate to the immutable target snapshot."""

    def __init__(self, primitives: UnicodeFacebookFlowAdapter) -> None:
        self._primitives = primitives

    def open_target(self, driver: Chrome, content: PlatformContent) -> None:
        # This primitive preserves the existing actor switch + actor_id == target_id
        # checks before/after navigation. URL/name remain navigation hints only.
        self._primitives._navigate_to_target(driver, content)


class FacebookComposerComponent:
    """Resolve and behavior-confirm Facebook's visible create-post surface."""

    def __init__(self, primitives: UnicodeFacebookFlowAdapter) -> None:
        self._primitives = primitives

    def open(self, driver: Chrome) -> WebElement:
        return self._primitives._open_composer(driver)

    def confirm_entry(self, driver: Chrome, content: PlatformContent) -> dict[str, Any]:
        return self._primitives.confirm_composer_entry(driver, content)


class FacebookTextInputComponent:
    """Unicode-safe text entry into the confirmed composer editor."""

    def __init__(self, primitives: UnicodeFacebookFlowAdapter) -> None:
        self._primitives = primitives

    def write(self, composer: WebElement, text: str) -> None:
        self._primitives._fill_text(composer, text)


class FacebookMediaComponent:
    """Visible Photo/Video activation, upload and processing readiness."""

    def __init__(self, primitives: UnicodeFacebookFlowAdapter) -> None:
        self._primitives = primitives

    def upload(
        self,
        driver: Chrome,
        composer: WebElement,
        media: Iterable[PlatformMedia],
    ) -> None:
        self._primitives._upload_media(driver, composer, media)


class FacebookSubmitComponent:
    """Bounded Next/Post state machine and final user-visible click."""

    def __init__(self, primitives: UnicodeFacebookFlowAdapter) -> None:
        self._primitives = primitives

    def wait_ready(self, driver: Chrome, composer: WebElement) -> WebElement:
        return self._primitives._wait_post_ready(driver, composer)

    def click(self, driver: Chrome, button: WebElement) -> None:
        self._primitives._safe_click(driver, button)


class FacebookVerifierComponent:
    """Post-click close detection and independent publication verification."""

    def __init__(self, primitives: UnicodeFacebookFlowAdapter) -> None:
        self._primitives = primitives

    def wait_composer_closed(self, driver: Chrome, composer: WebElement) -> None:
        self._primitives._wait_composer_closed(driver, composer)

    def verify(self, driver: Chrome, content: PlatformContent) -> dict[str, Any]:
        return self._primitives._verify_submission(driver, content)


class FacebookDiagnosticsComponent:
    """Advanced diagnostics kept separate from ordinary product UI."""

    def __init__(self, primitives: UnicodeFacebookFlowAdapter) -> None:
        self._primitives = primitives

    def snapshot(
        self,
        driver: Chrome,
        content: PlatformContent | None = None,
    ) -> dict[str, Any]:
        return {
            "current_url": driver.current_url,
            "title": driver.title,
            "current_actor_id": self._primitives.current_actor_id(driver),
            "target_id": content.target_id if content else None,
            "target_name": content.target_name if content else None,
        }


class FacebookConfigComponent:
    """Runtime Facebook keyword configuration used by the constrained workflow."""

    def keyword_groups(self) -> dict[str, list[str]]:
        config = load_facebook_flow()
        return {key: list(value) for key, value in config.items()}


@dataclass(frozen=True)
class FacebookComponentSet:
    identity: FacebookIdentityComponent
    navigation: FacebookNavigationComponent
    composer: FacebookComposerComponent
    text: FacebookTextInputComponent
    media: FacebookMediaComponent
    submit: FacebookSubmitComponent
    verifier: FacebookVerifierComponent
    diagnostics: FacebookDiagnosticsComponent
    config: FacebookConfigComponent

    @classmethod
    def build(
        cls,
        primitives: UnicodeFacebookFlowAdapter,
    ) -> "FacebookComponentSet":
        return cls(
            identity=FacebookIdentityComponent(primitives),
            navigation=FacebookNavigationComponent(primitives),
            composer=FacebookComposerComponent(primitives),
            text=FacebookTextInputComponent(primitives),
            media=FacebookMediaComponent(primitives),
            submit=FacebookSubmitComponent(primitives),
            verifier=FacebookVerifierComponent(primitives),
            diagnostics=FacebookDiagnosticsComponent(primitives),
            config=FacebookConfigComponent(),
        )
