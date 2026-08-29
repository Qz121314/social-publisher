from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterable

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.services.platforms.base import (
    PlatformAdapter,
    PlatformCapabilities,
    PlatformContent,
    PlatformNeedsReviewError,
    PlatformPublishError,
)


class FacebookAdapter(PlatformAdapter):
    """Facebook desktop-web publishing adapter.

    This adapter automates normal Facebook composer controls in an already
    authenticated iXBrowser profile. It deliberately does not handle CAPTCHA,
    checkpoint, account recovery, or any other platform security challenge.
    Such states are surfaced as `needs_review` to the worker layer.
    """

    capabilities = PlatformCapabilities(
        name="facebook",
        display_name="Facebook",
        supports_text=True,
        media_types=("image", "video"),
    )

    HOME_URL = "https://www.facebook.com/"
    DEFAULT_TIMEOUT = 25
    MEDIA_TIMEOUT = 900
    VERIFY_TIMEOUT = 20

    _COMPOSER_TEXT = (
        "What's on your mind",
        "What’s on your mind",
        "在想些什么",
        "有什么新鲜事",
        "创建帖子",
        "Create a post",
    )
    _MEDIA_TEXT = (
        "Photo/video",
        "Photo/Video",
        "照片/视频",
        "照片／视频",
        "图片/视频",
    )
    _POST_TEXT = ("Post", "发布")
    _UPLOAD_BUSY_TEXT = (
        "Uploading",
        "Processing",
        "正在上传",
        "正在处理",
    )
    _SUCCESS_TEXT = (
        "Your post was shared",
        "Post published",
        "Your post is being processed",
        "帖子已发布",
        "你的帖子已发布",
        "帖子正在处理中",
    )

    def check_login(self, driver: Chrome) -> dict[str, Any]:
        self._ensure_facebook(driver)
        current_url = driver.current_url or ""
        lowered = current_url.lower()

        needs_login = any(marker in lowered for marker in ("/login", "login.php"))
        checkpoint = any(
            marker in lowered
            for marker in (
                "/checkpoint",
                "/recover",
                "/two_step_verification",
            )
        )

        if not needs_login and not checkpoint:
            needs_login = bool(
                driver.find_elements(By.CSS_SELECTOR, "input[name='email'], input[name='pass']")
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

        login = self.check_login(driver)
        if login["checkpoint"]:
            raise PlatformNeedsReviewError(
                "Facebook requires account review/checkpoint in this iX profile. Complete it manually before retrying."
            )
        if not login["logged_in"]:
            raise PlatformNeedsReviewError(
                "Facebook is not logged in for this iX profile. Log in manually before retrying."
            )

        try:
            composer = self._open_composer(driver)
            self._fill_text(composer, content.text)
            if content.media:
                self._upload_media(driver, composer, content.media)

            post_button = self._wait_post_ready(driver, composer)
            self._safe_click(driver, post_button)
        except PlatformNeedsReviewError:
            raise
        except TimeoutException as exc:
            raise PlatformPublishError(
                "Facebook composer did not become ready before timeout. The page layout may have changed or media may still be processing."
            ) from exc
        except WebDriverException as exc:
            raise PlatformPublishError(f"Facebook browser automation failed before submission: {exc}") from exc

        try:
            self._wait_composer_closed(driver, composer)
        except TimeoutException as exc:
            raise PlatformNeedsReviewError(
                "Facebook received the Post click, but the composer did not close in time. Review the account before retrying to avoid a duplicate post.",
                submitted=True,
            ) from exc

        verification = self._verify_submission(driver, content)
        return {
            "platform": "facebook",
            "submitted": True,
            "verified": verification["verified"],
            "published_url": verification.get("published_url"),
            "verification": verification["message"],
            "current_url": driver.current_url,
            "title": driver.title,
        }

    def _ensure_facebook(self, driver: Chrome) -> None:
        current_url = driver.current_url or ""
        if "facebook.com" not in current_url.lower():
            driver.get(self.HOME_URL)

        WebDriverWait(driver, self.DEFAULT_TIMEOUT).until(
            lambda browser: browser.execute_script("return document.readyState") in ("interactive", "complete")
        )

    def _open_composer(self, driver: Chrome) -> WebElement:
        dialog_before = self._visible_dialogs(driver)
        opener = self._find_by_text_role(
            driver,
            role="button",
            texts=self._COMPOSER_TEXT,
            timeout=self.DEFAULT_TIMEOUT,
        )
        self._safe_click(driver, opener)

        def new_dialog(browser: Chrome) -> WebElement | bool:
            dialogs = self._visible_dialogs(browser)
            for dialog in dialogs:
                if dialog not in dialog_before:
                    return dialog
            return dialogs[-1] if dialogs else False

        return WebDriverWait(driver, self.DEFAULT_TIMEOUT).until(new_dialog)

    def _fill_text(self, composer: WebElement, text: str) -> None:
        if not text:
            return

        textbox = self._find_descendant(
            composer,
            (
                (By.CSS_SELECTOR, "div[role='textbox'][contenteditable='true']"),
                (By.CSS_SELECTOR, "[contenteditable='true'][data-lexical-editor='true']"),
            ),
            timeout=self.DEFAULT_TIMEOUT,
        )
        textbox.click()
        textbox.send_keys(text)

    def _upload_media(
        self,
        driver: Chrome,
        composer: WebElement,
        media: Iterable[Any],
    ) -> None:
        paths = [str(Path(item.path).resolve()) for item in media]
        missing = [path for path in paths if not Path(path).is_file()]
        if missing:
            raise PlatformPublishError(f"Local media file is missing: {missing[0]}")

        file_input = self._find_file_input(composer)
        if file_input is None:
            media_button = self._find_by_text_role(
                composer,
                role="button",
                texts=self._MEDIA_TEXT,
                timeout=8,
            )
            self._safe_click(driver, media_button)
            file_input = self._wait_file_input(composer)

        try:
            if file_input.get_attribute("multiple") is not None:
                file_input.send_keys("\n".join(paths))
            else:
                for path in paths:
                    file_input.send_keys(path)
                    if path != paths[-1]:
                        file_input = self._wait_file_input(composer)
        except WebDriverException as exc:
            raise PlatformPublishError(f"Facebook could not accept the selected media files: {exc}") from exc

        self._wait_media_processing(driver, composer)

    def _wait_media_processing(self, driver: Chrome, composer: WebElement) -> None:
        start = time.monotonic()
        last_busy_at = start

        while time.monotonic() - start < self.MEDIA_TIMEOUT:
            if self._has_security_challenge(driver):
                raise PlatformNeedsReviewError(
                    "Facebook opened a security/checkpoint flow while media was uploading. Review the profile manually."
                )

            busy = False
            try:
                busy = any(
                    element.is_displayed()
                    for element in composer.find_elements(By.CSS_SELECTOR, "[role='progressbar']")
                )
                if not busy:
                    composer_text = composer.text.lower()
                    busy = any(marker.lower() in composer_text for marker in self._UPLOAD_BUSY_TEXT)
            except StaleElementReferenceException:
                raise PlatformPublishError("Facebook composer disappeared while media was uploading.")

            if busy:
                last_busy_at = time.monotonic()
            else:
                try:
                    button = self._find_post_button(composer)
                    if button is not None and self._is_enabled(button):
                        return
                except StaleElementReferenceException:
                    pass

                # Some uploads do not expose a progressbar. Give the DOM a short
                # stabilization window before treating the enabled Post button as ready.
                if time.monotonic() - last_busy_at >= 2.0:
                    button = self._find_post_button(composer)
                    if button is not None and self._is_enabled(button):
                        return

            time.sleep(0.5)

        raise TimeoutException("Facebook media processing timed out.")

    def _wait_post_ready(self, driver: Chrome, composer: WebElement) -> WebElement:
        def ready(_: Chrome) -> WebElement | bool:
            if self._has_security_challenge(driver):
                raise PlatformNeedsReviewError(
                    "Facebook opened a security/checkpoint flow before publishing. Review the profile manually."
                )
            button = self._find_post_button(composer)
            if button is not None and self._is_enabled(button):
                return button
            return False

        return WebDriverWait(driver, self.MEDIA_TIMEOUT if self._composer_has_media(composer) else self.DEFAULT_TIMEOUT).until(ready)

    def _wait_composer_closed(self, driver: Chrome, composer: WebElement) -> None:
        WebDriverWait(driver, 45).until(EC.staleness_of(composer))

    def _verify_submission(self, driver: Chrome, content: PlatformContent) -> dict[str, Any]:
        end = time.monotonic() + self.VERIFY_TIMEOUT
        text_probe = " ".join(content.text.split())[:80].lower()

        while time.monotonic() < end:
            if self._has_security_challenge(driver):
                return {
                    "verified": False,
                    "published_url": None,
                    "message": "Facebook opened a checkpoint after submission; manual review is required.",
                }

            body_text = ""
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text
            except WebDriverException:
                pass

            lowered_body = body_text.lower()
            if any(marker.lower() in lowered_body for marker in self._SUCCESS_TEXT):
                return {
                    "verified": True,
                    "published_url": self._find_recent_permalink(driver, text_probe),
                    "message": "Facebook displayed a post-submission success/processing confirmation.",
                }

            if text_probe:
                for article in driver.find_elements(By.CSS_SELECTOR, "div[role='article']")[:12]:
                    try:
                        article_text = " ".join(article.text.split()).lower()
                    except StaleElementReferenceException:
                        continue
                    if text_probe in article_text:
                        return {
                            "verified": True,
                            "published_url": self._extract_permalink(article),
                            "message": "The submitted text was found in a Facebook feed article.",
                        }

            time.sleep(1.0)

        return {
            "verified": False,
            "published_url": None,
            "message": "The composer closed after submission, but the new post could not be independently located in the feed within the verification window.",
        }

    def _find_recent_permalink(self, driver: Chrome, text_probe: str) -> str | None:
        for article in driver.find_elements(By.CSS_SELECTOR, "div[role='article']")[:12]:
            try:
                if text_probe:
                    article_text = " ".join(article.text.split()).lower()
                    if text_probe not in article_text:
                        continue
                url = self._extract_permalink(article)
                if url:
                    return url
            except StaleElementReferenceException:
                continue
        return None

    @staticmethod
    def _extract_permalink(article: WebElement) -> str | None:
        candidates = article.find_elements(By.CSS_SELECTOR, "a[href]")
        markers = ("/posts/", "/videos/", "/reel/", "story_fbid=", "/permalink/")
        for link in candidates:
            href = link.get_attribute("href") or ""
            if any(marker in href for marker in markers):
                return href
        return None

    def _find_post_button(self, composer: WebElement) -> WebElement | None:
        for text in self._POST_TEXT:
            xpath = (
                ".//*[@role='button' and "
                f"(normalize-space(@aria-label)={self._xpath_literal(text)} or normalize-space(.)={self._xpath_literal(text)})]"
            )
            for element in composer.find_elements(By.XPATH, xpath):
                try:
                    if element.is_displayed():
                        return element
                except StaleElementReferenceException:
                    continue
        return None

    @staticmethod
    def _is_enabled(element: WebElement) -> bool:
        disabled = (element.get_attribute("aria-disabled") or "").lower() == "true"
        return element.is_enabled() and not disabled

    @staticmethod
    def _composer_has_media(composer: WebElement) -> bool:
        try:
            return bool(composer.find_elements(By.CSS_SELECTOR, "img, video, [role='progressbar']"))
        except StaleElementReferenceException:
            return False

    @staticmethod
    def _visible_dialogs(driver: Chrome) -> list[WebElement]:
        result: list[WebElement] = []
        for element in driver.find_elements(By.CSS_SELECTOR, "div[role='dialog']"):
            try:
                if element.is_displayed():
                    result.append(element)
            except StaleElementReferenceException:
                continue
        return result

    @staticmethod
    def _find_file_input(root: WebElement) -> WebElement | None:
        for element in root.find_elements(By.CSS_SELECTOR, "input[type='file']"):
            accept = (element.get_attribute("accept") or "").lower()
            if not accept or "image" in accept or "video" in accept:
                return element
        return None

    def _wait_file_input(self, root: WebElement) -> WebElement:
        return WebDriverWait(root, self.DEFAULT_TIMEOUT).until(
            lambda current: self._find_file_input(current) or False
        )

    def _find_descendant(
        self,
        root: WebElement,
        selectors: tuple[tuple[str, str], ...],
        *,
        timeout: int,
    ) -> WebElement:
        def locate(_: Any) -> WebElement | bool:
            for by, selector in selectors:
                for element in root.find_elements(by, selector):
                    try:
                        if element.is_displayed():
                            return element
                    except StaleElementReferenceException:
                        continue
            return False

        return WebDriverWait(root, timeout).until(locate)

    def _find_by_text_role(
        self,
        root: Chrome | WebElement,
        *,
        role: str,
        texts: tuple[str, ...],
        timeout: int,
    ) -> WebElement:
        def locate(_: Any) -> WebElement | bool:
            for text in texts:
                literal = self._xpath_literal(text)
                xpath = (
                    f".//*[@role='{role}' and ("
                    f"contains(normalize-space(@aria-label), {literal}) or "
                    f"contains(normalize-space(.), {literal})"
                    ")]"
                )
                for element in root.find_elements(By.XPATH, xpath):
                    try:
                        if element.is_displayed():
                            return element
                    except StaleElementReferenceException:
                        continue
            return False

        try:
            return WebDriverWait(root, timeout).until(locate)
        except TimeoutException as exc:
            raise PlatformPublishError(
                f"Facebook UI control not found for role={role}. The desktop composer layout or language may have changed."
            ) from exc

    @staticmethod
    def _safe_click(driver: Chrome, element: WebElement) -> None:
        try:
            element.click()
            return
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.2)
            element.click()

    @staticmethod
    def _has_security_challenge(driver: Chrome) -> bool:
        lowered = (driver.current_url or "").lower()
        return any(
            marker in lowered
            for marker in (
                "/checkpoint",
                "/recover",
                "/two_step_verification",
            )
        )

    @staticmethod
    def _xpath_literal(value: str) -> str:
        if "'" not in value:
            return f"'{value}'"
        if '"' not in value:
            return f'"{value}"'
        parts = value.split("'")
        return "concat(" + ", \"'\", ".join(f"'{part}'" for part in parts) + ")"
