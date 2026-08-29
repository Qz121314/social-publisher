from __future__ import annotations

from typing import Any

from selenium.webdriver import Chrome

from app.services.platforms.base import PlatformContent
from app.services.platforms.facebook_unified_flow import UnifiedFacebookFlowAdapter


def confirm_facebook_composer_entry(
    driver: Chrome,
    *,
    target_id: str,
    target_name: str,
    target_url: str,
    target_type: str | None = None,
) -> dict[str, Any]:
    """Confirm the current Facebook composer flow for one target actor.

    Personal profiles and Pages use the same state machine. The current composer
    may expose a final Post action immediately or a staged Next -> Post flow.
    Confirmation never types content and never clicks the final publish action.
    """

    adapter = UnifiedFacebookFlowAdapter()
    content = PlatformContent(
        text="confirmation-only",
        media=(),
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        target_url=target_url,
    )
    return adapter.confirm_composer_entry(driver, content)


def probe_facebook_composer_entry(
    driver: Chrome,
    *,
    target_type: str,
    target_id: str,
    target_name: str,
    target_url: str,
) -> dict[str, Any]:
    return confirm_facebook_composer_entry(
        driver,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        target_url=target_url,
    )
