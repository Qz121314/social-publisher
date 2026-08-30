from __future__ import annotations

from urllib.parse import urlparse

from selenium.webdriver import Chrome

from app.services.platforms.instagram_composite import (
    InstagramCompositeAdapter,
    InstagramIdentityComponent,
)


class InstagramDomainIdentityComponent(InstagramIdentityComponent):
    """Ensure Selenium is on instagram.com before reading Instagram cookies.

    iXBrowser environments can be left on Facebook, a blank tab, or any other
    site between jobs. Selenium cookie lookup is origin-scoped, so reading
    ``ds_user_id`` before entering Instagram can falsely report a logged-in
    account as logged out. This component establishes the Instagram origin first;
    all login/challenge and stable-identity rules remain inherited unchanged.
    """

    def check_login(self, driver: Chrome):
        parsed = urlparse(driver.current_url or "")
        host = parsed.netloc.lower().split(":", 1)[0]
        if host not in {"instagram.com", "www.instagram.com"}:
            driver.get("https://www.instagram.com/")
        return super().check_login(driver)


class InstagramProductionAdapter(InstagramCompositeAdapter):
    """Production Instagram adapter with origin-safe identity inspection."""

    def __init__(self) -> None:
        super().__init__()
        self.identity = InstagramDomainIdentityComponent()
