from __future__ import annotations

from typing import Any

from selenium.webdriver import Chrome

from app.services.platforms.base import PlatformContent
from app.services.platforms.facebook_target import TargetActorFacebookAdapter


def confirm_facebook_composer_entry(
    driver: Chrome,
    *,
    target_id: str,
    target_name: str,
    target_url: str,
    target_type: str | None = None,
) -> dict[str, Any]:
    """Behavior-confirm the real Facebook composer entry for one target actor.

    Personal profiles and Pages use the exact same confirmation flow. The target
    type is carried only as metadata. The confirmation does not type content and
    never clicks the final Post button. A result is successful only when clicking
    an entry produces both a real editable composer and a visible Post button.
    """

    adapter = TargetActorFacebookAdapter()
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
