from __future__ import annotations

from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from app.services.platforms.facebook_flow_config import load_facebook_flow
from app.services.platforms.facebook_unified_flow import UnifiedFacebookFlowAdapter


class ConfigurableFacebookFlowAdapter(UnifiedFacebookFlowAdapter):
    """Facebook publishing driven by runtime-editable text keyword groups.

    The automation actions remain constrained and safe: actor-ID validation,
    visible click, text entry, media upload, bounded Next/Continue advancement,
    final Post click, and result verification. Only the localized text used to
    locate Facebook UI states is configurable at runtime.
    """

    @staticmethod
    def _keywords(key: str) -> tuple[str, ...]:
        return tuple(load_facebook_flow()[key])

    @property
    def _PRIMARY_PROMPTS(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("entry_keywords")

    @property
    def _COMPOSER_TEXT(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("entry_keywords")

    @property
    def _SURFACE_TITLES(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("surface_titles")

    @property
    def _MEDIA_TEXT(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("media_keywords")

    @property
    def _NEXT_TEXT(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("next_keywords")

    @property
    def _POST_TEXT(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("post_keywords")

    @property
    def _UPLOAD_BUSY_TEXT(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("upload_busy_keywords")

    @property
    def _SUCCESS_TEXT(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("success_keywords")

    def _media_is_busy(self, driver: Chrome, composer: WebElement) -> bool:
        """Detect media-processing state without treating WebDriver as a WebElement.

        Selenium WebDriver supports ``find_elements`` but does not expose the
        WebElement ``text`` property. For the document-wide fallback we therefore
        read the visible text from ``body`` explicitly.
        """

        for root in (composer, driver):
            try:
                if any(
                    item.is_displayed()
                    for item in root.find_elements(By.CSS_SELECTOR, "[role='progressbar']")
                ):
                    return True

                if isinstance(root, WebElement):
                    visible_text = root.text or ""
                else:
                    body = driver.find_element(By.TAG_NAME, "body")
                    visible_text = body.text or ""

                lowered = visible_text.casefold()
                if any(marker.casefold() in lowered for marker in self._UPLOAD_BUSY_TEXT):
                    return True
            except (StaleElementReferenceException, WebDriverException):
                continue

        return False
