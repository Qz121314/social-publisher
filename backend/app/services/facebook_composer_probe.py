from __future__ import annotations

from typing import Any

from selenium.webdriver import Chrome

from app.services.platforms.base import PlatformContent
from app.services.platforms.facebook_surface_precise import PreciseFacebookSurfaceAdapter


def confirm_facebook_composer_entry(
    driver: Chrome,
    *,
    target_id: str,
    target_name: str,
    target_url: str,
    target_type: str | None = None,
) -> dict[str, Any]:
    """Behavior-confirm the real Facebook create-post surface for one target actor.

    Personal profiles and Pages use the exact same flow. The target type is only
    display metadata. Confirmation never types content and never clicks the final
    Post action. Success requires the real Facebook create-post surface, a visible
    editor, and a visible Post action; the Post action may be disabled while the
    editor is empty.
    """

    adapter = PreciseFacebookSurfaceAdapter()
    content = PlatformContent(
        text="confirmation-only",
        media=(),
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        target_url=target_url,
    )
    return adapter.confirm_composer_entry(driver, content)


# Backward-compatible alias while the UI/API migrates from "probe" wording to
# the stricter behavior-confirmation model.
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
