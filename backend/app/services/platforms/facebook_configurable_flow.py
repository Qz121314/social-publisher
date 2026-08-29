from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterable

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    MoveTargetOutOfBoundsException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import Chrome
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from app.services.platforms.base import (
    PlatformContent,
    PlatformNeedsReviewError,
    PlatformPublishError,
)
from app.services.platforms.facebook import FacebookAdapter
from app.services.platforms.facebook_flow_config import load_facebook_flow
from app.services.platforms.facebook_unified_flow import UnifiedFacebookFlowAdapter


class ConfigurableFacebookFlowAdapter(UnifiedFacebookFlowAdapter):
    """Facebook publishing driven by runtime-editable text keyword groups.

    The automation actions remain constrained and safe: actor-ID validation,
    visible click, text entry, media upload, bounded Next/Continue advancement,
    final Post click, and result verification. Only the localized text used to
    locate Facebook UI states is configurable at runtime.
    """

    def publish(self, driver: Chrome, content: PlatformContent) -> dict[str, Any]:
        started = time.monotonic()
        result = super().publish(driver, content)
        result["automation_duration_ms"] = int((time.monotonic() - started) * 1000)
        return result

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

    # ------------------------------------------------------------------
    # Target preparation hot path.
    # Keep the ID safety gates, but avoid reloading an already-correct target URL.
    # ------------------------------------------------------------------
    def _navigate_to_target(self, driver: Chrome, content: PlatformContent) -> None:
        self._ensure_target_actor(driver, content)
        self._assert_target_actor(driver, content, stage="身份切换后")

        target_url = (content.target_url or "").strip()
        current_url = driver.current_url or ""
        if target_url and self._target_matches(target_url, current_url):
            self._assert_target_actor(driver, content, stage="复用当前目标页面时")
            return

        # Call the base navigation primitive directly so the TargetActor wrapper
        # does not perform the same preparation twice.
        FacebookAdapter._navigate_to_target(self, driver, content)
        self._assert_target_actor(driver, content, stage="进入目标页面后")

    def _wait_for_actor(self, driver: Chrome, expected: str) -> None:
        """Poll the Facebook actor cookie directly instead of nesting 3s waits."""

        end = time.monotonic() + 25
        last_actor: str | None = None
        while time.monotonic() < end:
            try:
                last_actor = self.current_actor_id(driver)
            except WebDriverException:
                last_actor = None
            if last_actor == expected:
                return
            time.sleep(0.2)

        raise PlatformPublishError(
            "已点击 Facebook 身份切换项，但身份 ID 校验没有通过，已停止发布。"
            f" 当前身份={last_actor or '-'}，目标身份={expected}。"
        )

    # ------------------------------------------------------------------
    # Media workflow.
    # ------------------------------------------------------------------
    def _upload_media(
        self,
        driver: Chrome,
        composer: WebElement,
        media: Iterable[Any],
    ) -> None:
        """Follow Facebook's visible media workflow before advancing the composer.

        Facebook can keep hidden file inputs in the DOM before the user activates
        the Photo/Video action. Sending files to one of those inputs can be ignored
        by the current composer. For configured media posts we therefore always
        activate the visible media action first, then send files to the input owned
        by that state, and finally require evidence that Facebook actually attached
        the media before Next/Post is allowed to advance.
        """

        paths = [str(Path(item.path).resolve()) for item in media]
        missing = [path for path in paths if not Path(path).is_file()]
        if missing:
            raise PlatformPublishError(f"本地媒体文件不存在：{missing[0]}")
        if not paths:
            return

        before_media = self._media_signatures(composer)
        before_input_ids = {item.id for item in self._acceptable_file_inputs(driver)}

        media_button = self._find_media_button(driver, composer)
        if media_button is None:
            configured = " / ".join(self._MEDIA_TEXT[:6])
            raise PlatformPublishError(
                "Facebook 发帖界面已打开，但没有找到媒体入口。"
                f"当前配置关键词：{configured or '-'}。"
            )

        self._activate_media_button(driver, media_button)
        file_input = self._wait_media_file_input_after_activation(
            driver,
            composer,
            before_input_ids,
        )

        try:
            if file_input.get_attribute("multiple") is not None:
                file_input.send_keys("\n".join(paths))
            else:
                for index, path in enumerate(paths):
                    file_input.send_keys(path)
                    if index < len(paths) - 1:
                        file_input = self._wait_any_composer_file_input(driver, composer)
        except WebDriverException as exc:
            raise PlatformPublishError(f"Facebook 无法接收所选媒体文件：{exc}") from exc

        self._wait_media_attached(driver, composer, file_input, before_media)
        self._wait_media_processing(driver, composer)

    def _activate_media_button(self, driver: Chrome, button: WebElement) -> None:
        """Activate the already-confirmed Facebook Photo/Video control."""

        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                button,
            )
        except WebDriverException:
            pass

        try:
            ActionChains(driver).move_to_element(button).pause(0.05).click().perform()
            return
        except (
            ElementClickInterceptedException,
            MoveTargetOutOfBoundsException,
            WebDriverException,
        ):
            pass

        try:
            button.click()
            return
        except (ElementClickInterceptedException, WebDriverException):
            pass

        try:
            clicked = driver.execute_script(
                """
                const el = arguments[0];
                if (!el || !el.isConnected) return false;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') return false;
                el.click();
                return true;
                """,
                button,
            )
        except WebDriverException as exc:
            raise PlatformPublishError(
                f"Facebook 已定位到“照片/视频”按钮，但无法触发该按钮：{exc}"
            ) from exc

        if not clicked:
            raise PlatformPublishError(
                "Facebook 已定位到“照片/视频”按钮，但该按钮当前不可交互。"
            )

    def _wait_media_file_input_after_activation(
        self,
        driver: Chrome,
        composer: WebElement,
        before_ids: set[str],
    ) -> WebElement:
        """Prefer a newly-created input, but quickly reuse Facebook's activated one.

        Older logic waited almost the full 15-second timeout when Facebook reused
        an existing hidden input. The media button is now always activated first,
        so an existing eligible input can safely be tried after a short grace
        period; attachment verification still prevents the workflow from advancing
        if Facebook did not actually accept the media.
        """

        started = time.monotonic()
        end = started + 6.0
        fallback: WebElement | None = None

        while time.monotonic() < end:
            local_inputs = self._acceptable_file_inputs(composer)
            global_inputs = self._acceptable_file_inputs(driver)

            for item in reversed(local_inputs + global_inputs):
                try:
                    if item.id not in before_ids:
                        return item
                    if fallback is None:
                        fallback = item
                except StaleElementReferenceException:
                    continue

            if fallback is not None and time.monotonic() - started >= 0.8:
                return fallback
            time.sleep(0.1)

        if fallback is not None:
            return fallback
        raise PlatformPublishError(
            "已点击 Facebook“照片/视频”入口，但没有出现可用的文件上传控件。"
        )

    def _wait_media_attached(
        self,
        driver: Chrome,
        composer: WebElement,
        file_input: WebElement,
        before_media: set[str],
    ) -> None:
        """Require attachment evidence before allowing Next/Post to proceed."""

        end = time.monotonic() + 20
        files_seen_at: float | None = None
        while time.monotonic() < end:
            if self._has_security_challenge(driver):
                raise PlatformNeedsReviewError(
                    "Facebook 在添加媒体时打开了安全验证，请人工处理后再继续。"
                )

            try:
                count = driver.execute_script(
                    "return arguments[0].files ? arguments[0].files.length : 0;",
                    file_input,
                )
                if isinstance(count, (int, float)) and count > 0 and files_seen_at is None:
                    files_seen_at = time.monotonic()
            except (StaleElementReferenceException, WebDriverException):
                pass

            current_media = self._media_signatures(composer)
            if current_media - before_media:
                return

            # Some Facebook builds render previews using CSS/background layers rather
            # than a new img/video node. A populated input that stays attached for a
            # short interval is therefore accepted, then processing readiness is
            # checked separately before Next/Post can advance.
            if files_seen_at is not None and time.monotonic() - files_seen_at >= 0.9:
                return

            time.sleep(0.15)

        raise PlatformPublishError(
            "图片/视频文件已发送给 Facebook，但没有检测到媒体已附加或出现新的媒体预览，"
            "因此没有继续点击“下一页”。"
        )

    @staticmethod
    def _media_signatures(root: WebElement) -> set[str]:
        signatures: set[str] = set()
        try:
            elements = root.find_elements(
                By.CSS_SELECTOR,
                "img[src], video[src], video[poster], video source[src]",
            )
        except (StaleElementReferenceException, WebDriverException):
            return signatures

        for element in elements:
            try:
                value = (
                    element.get_attribute("src")
                    or element.get_attribute("poster")
                    or ""
                ).strip()
                if value:
                    signatures.add(value)
            except StaleElementReferenceException:
                continue
        return signatures

    def _media_is_busy(self, driver: Chrome, composer: WebElement) -> bool:
        """Detect upload/processing state inside the active composer only."""

        try:
            if any(
                item.is_displayed()
                for item in composer.find_elements(By.CSS_SELECTOR, "[role='progressbar']")
            ):
                return True

            visible_text = composer.text or ""
            lowered = visible_text.casefold()
            return any(marker.casefold() in lowered for marker in self._UPLOAD_BUSY_TEXT)
        except (StaleElementReferenceException, WebDriverException):
            return False

    def _wait_media_processing(self, driver: Chrome, composer: WebElement) -> None:
        """Advance as soon as Facebook reports a stable enabled primary action."""

        start = time.monotonic()
        quiet_since: float | None = None

        while time.monotonic() - start < self.MEDIA_TIMEOUT:
            if self._has_security_challenge(driver):
                raise PlatformNeedsReviewError(
                    "Facebook 在媒体上传期间打开了安全验证，请人工处理后再继续。"
                )

            if self._media_is_busy(driver, composer):
                quiet_since = None
            else:
                action = self._find_enabled_post_or_next(driver, composer)
                if action is not None:
                    if quiet_since is None:
                        quiet_since = time.monotonic()
                    elif time.monotonic() - quiet_since >= 0.45:
                        return
                else:
                    quiet_since = None
            time.sleep(0.18)

        raise TimeoutException("Facebook media processing timed out.")

    # ------------------------------------------------------------------
    # Faster success verification. Keep the same 20s safety window, but poll the
    # high-confidence signals frequently and avoid reading the full page every tick.
    # ------------------------------------------------------------------
    def _verify_submission(
        self,
        driver: Chrome,
        content: PlatformContent,
    ) -> dict[str, Any]:
        end = time.monotonic() + self.VERIFY_TIMEOUT
        text_probe = " ".join(content.text.split())[:80].casefold()
        next_body_scan = 0.0

        while time.monotonic() < end:
            if self._has_security_challenge(driver):
                return {
                    "verified": False,
                    "published_url": None,
                    "message": "Facebook opened a checkpoint after submission; manual review is required.",
                }

            try:
                status_texts: list[str] = []
                for element in driver.find_elements(By.CSS_SELECTOR, "[role='alert'], [role='status']"):
                    try:
                        if element.is_displayed():
                            value = (element.text or "").strip()
                            if value:
                                status_texts.append(value)
                    except StaleElementReferenceException:
                        continue
                status_text = "\n".join(status_texts).casefold()
            except WebDriverException:
                status_text = ""

            if status_text and any(
                marker.casefold() in status_text for marker in self._SUCCESS_TEXT
            ):
                return {
                    "verified": True,
                    "published_url": None,
                    "message": "Facebook displayed a post-submission success/processing confirmation.",
                }

            try:
                articles = driver.find_elements(By.CSS_SELECTOR, "div[role='article']")[:12]
            except WebDriverException:
                articles = []

            if text_probe:
                for article in articles:
                    try:
                        article_text = " ".join(article.text.split()).casefold()
                    except StaleElementReferenceException:
                        continue
                    if text_probe in article_text:
                        return {
                            "verified": True,
                            "published_url": self._extract_permalink(article),
                            "message": "The submitted text was found in a Facebook feed article.",
                        }

            now = time.monotonic()
            if now >= next_body_scan:
                next_body_scan = now + 1.2
                try:
                    body_text = driver.find_element(By.TAG_NAME, "body").text.casefold()
                except WebDriverException:
                    body_text = ""
                if body_text and any(
                    marker.casefold() in body_text for marker in self._SUCCESS_TEXT
                ):
                    return {
                        "verified": True,
                        "published_url": self._find_recent_permalink(articles, text_probe),
                        "message": "Facebook displayed a post-submission success/processing confirmation.",
                    }

            time.sleep(0.25)

        return {
            "verified": False,
            "published_url": None,
            "message": "The composer closed after submission, but the new post could not be independently located in the feed within the verification window.",
        }
