from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterable

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    MoveTargetOutOfBoundsException,
    StaleElementReferenceException,
    WebDriverException,
)
from selenium.webdriver import Chrome
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from app.services.platforms.base import PlatformNeedsReviewError, PlatformPublishError
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
        """Activate the already-confirmed Facebook Photo/Video control.

        Facebook frequently layers an internal transparent container over visible
        composer controls. Native Selenium clicking may therefore be intercepted
        even when the correct role=button/aria-label element has been identified.
        Keep the target fixed, try a normal pointer interaction first, then use a
        DOM click only on that same verified control. Subsequent media-state checks
        still have to succeed before the workflow may continue.
        """

        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                button,
            )
            time.sleep(0.2)
        except WebDriverException:
            pass

        try:
            ActionChains(driver).move_to_element(button).pause(0.15).click().perform()
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
        end = time.monotonic() + 15
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

            if fallback is not None and time.monotonic() + 1.5 >= end:
                return fallback
            time.sleep(0.2)

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

        end = time.monotonic() + 35
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
                if isinstance(count, (int, float)) and count > 0:
                    return
            except (StaleElementReferenceException, WebDriverException):
                pass

            current_media = self._media_signatures(composer)
            if current_media - before_media:
                return

            time.sleep(0.25)

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
        """Detect media-processing state without treating WebDriver as a WebElement."""

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
