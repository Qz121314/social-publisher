from __future__ import annotations

from selenium.webdriver import Chrome

from app.services.platforms.base import PlatformContent
from app.services.platforms.facebook_identity import IdentityAwareFacebookAdapter


class IdentityHomeFacebookAdapter(IdentityAwareFacebookAdapter):
    """Use Facebook Home composer for personal-profile publishing.

    Facebook personal profile pages render the create-post entry inconsistently
    (lazy loading, below-the-fold modules and experiment-specific markup). Once
    the active actor ID is verified as the configured personal target, the Home
    feed composer posts as that same personal actor and is materially more stable.

    Page targets keep the existing target-page navigation flow. In every case,
    the inherited final pre-Post actor-ID gate remains active.
    """

    def _navigate_to_target(self, driver: Chrome, content: PlatformContent) -> None:
        if content.target_type != "profile":
            super()._navigate_to_target(driver, content)
            return

        # Gate 1: switch to and verify the configured personal actor first.
        self._ensure_target_identity(driver, content)
        self._assert_target_actor(driver, content, stage="身份切换后")

        # Personal profile pages do not expose a consistent composer. Open the
        # Facebook Home feed instead; the active actor remains the personal ID.
        self._open_facebook_home(driver)

        # Gate 2: opening Home must not have changed the actor. The inherited
        # Gate 3 runs again immediately before the Post click.
        self._assert_target_actor(driver, content, stage="进入首页发帖区后")
