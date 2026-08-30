from __future__ import annotations

from typing import Any

from selenium.webdriver import Chrome

from app.services.platforms.base import PlatformContent, PlatformPublishError
from app.services.platforms.facebook_composite import FacebookCompositeAdapter
from app.services.platforms.registry import get_platform_adapter


def confirm_facebook_composer_entry(
    driver: Chrome,
    *,
    target_id: str,
    target_name: str,
    target_url: str,
    target_type: str | None = None,
) -> dict[str, Any]:
    """Confirm the configured Facebook composer through the production adapter.

    Confirmation and real publishing now share the same composed Identity /
    Navigation / Composer stack. It never types content and never clicks the final
    publish action.
    """

    adapter = get_platform_adapter("facebook")
    if not isinstance(adapter, FacebookCompositeAdapter):
        raise PlatformPublishError("Facebook production adapter is not available.")
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
