from __future__ import annotations

from typing import Any

from selenium.webdriver import Chrome

from app.services.platforms.base import (
    PlatformAdapter,
    PlatformCapabilities,
    PlatformContent,
)


class FacebookAdapter(PlatformAdapter):
    capabilities = PlatformCapabilities(
        name="facebook",
        display_name="Facebook",
        supports_text=True,
        media_types=("image", "video"),
    )

    def check_login(self, driver: Chrome) -> dict[str, Any]:
        current_url = driver.current_url or ""
        if "facebook.com" not in current_url.lower():
            driver.get("https://www.facebook.com/")
            current_url = driver.current_url or ""

        lowered = current_url.lower()
        needs_login = any(
            marker in lowered
            for marker in (
                "/login",
                "login.php",
            )
        )
        checkpoint = any(
            marker in lowered
            for marker in (
                "/checkpoint",
                "/recover",
            )
        )

        return {
            "platform": "facebook",
            "logged_in": not needs_login and not checkpoint and "facebook.com" in lowered,
            "needs_login": needs_login,
            "checkpoint": checkpoint,
            "current_url": current_url,
            "title": driver.title,
        }

    def publish(self, driver: Chrome, content: PlatformContent) -> dict[str, Any]:
        self.validate_content(content)
        raise NotImplementedError(
            "Facebook publishing DOM automation is the next milestone. "
            "This adapter currently provides capabilities, validation, and login checks."
        )
