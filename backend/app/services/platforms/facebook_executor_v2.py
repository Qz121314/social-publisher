from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterable

from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from app.services.platforms.base import (
    PlatformNeedsReviewError,
    PlatformPublishError,
    emit_platform_progress,
)
from app.services.platforms.facebook_surface import _ACTIVE_SURFACE_CONTENT
from app.services.platforms.facebook_unicode_flow import UnicodeFacebookFlowAdapter


class FacebookExecutorV2(UnicodeFacebookFlowAdapter):
    """Stable Facebook browser executor built around observable UI states.

    This executor deliberately does not implement anti-detection or platform-evasion
    techniques. It does not mask WebDriver, alter browser fingerprints, bypass
    checkpoints/CAPTCHA, or synthesize human-like behavior. Its responsibility is
    deterministic browser control, conservative failure handling and clear runtime
    diagnostics.

    The two main differences from the legacy flow are:

    1. Native file chooser dialogs are intercepted at the Chrome DevTools layer
       before any media-entry control may be activated. Project assets are assigned
       directly to Facebook's ``input[type=file]``. If interception is unavailable,
       the executor refuses to click the media control instead of risking a Windows
       file picker.
    2. Next/Post progression is driven by an explicit observable state machine so
       Timeline can say which Facebook UI state was actually seen.
    """

    FILE_INPUT_TIMEOUT = 8.0
    POST_CLOSE_TIMEOUT = 25.0
    UNKNOWN_DIALOG_GRACE = 2.5

    # ------------------------------------------------------------------
    # Media workflow: never allow an OS-native file picker to become the control
    # plane. Existing inputs are preferred; media activation is permitted only
    # while Chrome confirms file-chooser interception is enabled.
    # ------------------------------------------------------------------
    def _upload_media(
        self,
        driver: Any,
        composer: WebElement,
        media: Iterable[Any],
    ) -> None:
        paths = [str(Path(item.path).resolve()) for item in media]
        missing = [path for path in paths if not Path(path).is_file()]
        if missing:
            raise PlatformPublishError(f"本地媒体文件不存在：{missing[0]}")
        if not paths:
            return

        before_media = self._media_signatures(composer)
        file_input = self._preferred_file_input(driver, composer)

        if file_input is None:
            media_button = self._find_media_button(driver, composer)
            if media_button is None:
                configured = " / ".join(self._MEDIA_TEXT[:6])
                raise PlatformPublishError(
                    "Facebook 发帖界面已打开，但没有找到媒体上传入口。"
                    f"当前配置关键词：{configured or '-'}。"
                )

            # Critical invariant: never activate Facebook's media entry unless
            # Chrome confirms the OS file chooser has been intercepted first.
            if not self._set_file_chooser_interception(driver, enabled=True):
                raise PlatformPublishError(
                    "当前 Chrome/iXBrowser 无法启用文件选择器拦截。为了避免再次弹出 Windows 文件夹，"
                    "系统没有点击 Facebook“照片/视频”入口。"
                )

            try:
                emit_platform_progress(
                    "facebook_state",
                    "Facebook UI 状态：media_entry_intercepted",
                    {"state": "media_entry_intercepted"},
                )
                self._safe_click(driver, media_button)
                file_input = self._wait_for_file_input(driver, composer)
            finally:
                # Best effort cleanup. Failure to disable does not invalidate an
                # already-attached media file, but should never mask the real error.
                self._set_file_chooser_interception(driver, enabled=False)

        self._send_media_paths(driver, composer, file_input, paths)
        self._wait_media_attached(driver, composer, file_input, before_media)
        self._wait_media_processing(driver, composer)

    def _preferred_file_input(
        self,
        driver: Any,
        composer: WebElement,
    ) -> WebElement | None:
        local = self._acceptable_file_inputs(composer)
        if local:
            return local[-1]
        global_inputs = self._acceptable_file_inputs(driver)
        return global_inputs[-1] if global_inputs else None

    def _wait_for_file_input(
        self,
        driver: Any,
        composer: WebElement,
    ) -> WebElement:
        deadline = time.monotonic() + self.FILE_INPUT_TIMEOUT
        while time.monotonic() < deadline:
            file_input = self._preferred_file_input(driver, composer)
            if file_input is not None:
                return file_input
            if self._has_security_challenge(driver):
                raise PlatformNeedsReviewError(
                    "Facebook 在准备媒体上传时打开了安全验证，请人工处理后再继续。"
                )
            time.sleep(0.1)
        raise PlatformPublishError(
            "Facebook 媒体入口已激活，但页面没有暴露可用的 input[type=file]。"
            "系统没有打开 Windows 文件选择器，请检查当前 Facebook 页面结构。"
        )

    @staticmethod
    def _set_file_chooser_interception(driver: Any, *, enabled: bool) -> bool:
        try:
            driver.execute_cdp_cmd(
                "Page.setInterceptFileChooserDialog",
                {"enabled": enabled},
            )
            return True
        except Exception:
            return False

    def _send_media_paths(
        self,
        driver: Any,
        composer: WebElement,
        file_input: WebElement,
        paths: list[str],
    ) -> None:
        try:
            if file_input.get_attribute("multiple") is not None:
                file_input.send_keys("\n".join(paths))
                return

            current = file_input
            for index, path in enumerate(paths):
                current.send_keys(path)
                if index < len(paths) - 1:
                    current = self._wait_for_file_input(driver, composer)
        except WebDriverException as exc:
            raise PlatformPublishError(
                f"Facebook 无法直接接收项目素材文件：{type(exc).__name__}"
            ) from exc

    # ------------------------------------------------------------------
    # Observable submit state machine.
    # ------------------------------------------------------------------
    def _observe_publish_state(
        self,
        driver: Any,
        composer: WebElement,
    ) -> tuple[str, WebElement | None]:
        if self._has_security_challenge(driver):
            return "checkpoint", None

        try:
            if not composer.is_displayed():
                return "composer_closed", None
        except StaleElementReferenceException:
            return "composer_closed", None

        if self._media_is_busy(driver, composer):
            return "media_processing", None

        post = self._find_post_button_anywhere(driver, composer)
        if post is not None and self._is_enabled(post):
            return "post_ready", post

        nxt = self._find_action_button(driver, composer, self._NEXT_TEXT)
        if nxt is not None and self._is_enabled(nxt):
            return "next_ready", nxt

        return "waiting_ui", None

    def _wait_post_ready(self, driver: Any, composer: WebElement) -> WebElement:
        timeout = self.MEDIA_TIMEOUT if self._composer_has_media(composer) else self.DEFAULT_TIMEOUT
        deadline = time.monotonic() + timeout
        next_steps = 0
        last_state: str | None = None

        while time.monotonic() < deadline:
            state, action = self._observe_publish_state(driver, composer)
            if state != last_state:
                emit_platform_progress(
                    "facebook_state",
                    f"Facebook UI 状态：{state}",
                    {"state": state, "next_steps": next_steps},
                )
                last_state = state

            if state == "checkpoint":
                raise PlatformNeedsReviewError(
                    "Facebook 在发布前打开了安全验证 / Checkpoint，请人工处理后再继续。"
                )

            if state == "composer_closed":
                raise PlatformPublishError(
                    "Facebook Composer 在最终发布前意外关闭，已停止任务。"
                )

            if state == "post_ready" and action is not None:
                content = _ACTIVE_SURFACE_CONTENT.get()
                if content is None:
                    raise PlatformPublishError("Facebook 发布上下文丢失，已停止发布。")
                self._assert_target_actor(driver, content, stage="点击最终发帖按钮前")
                return action

            if state == "next_ready" and action is not None:
                if next_steps >= 3:
                    raise PlatformPublishError(
                        "Facebook 连续出现超过 3 个流程推进步骤，已停止以避免误操作。"
                    )
                content = _ACTIVE_SURFACE_CONTENT.get()
                if content is not None:
                    self._assert_target_actor(driver, content, stage="进入下一步发布界面前")
                self._safe_click(driver, action)
                next_steps += 1
                time.sleep(0.35)
                continue

            time.sleep(0.18)

        visible = self._visible_primary_action_labels(driver)
        raise TimeoutException(
            "Facebook composer did not reach a usable observed state before timeout. "
            f"Last state={last_state or '-'}; visible actions={visible or '-'}"
        )

    # ------------------------------------------------------------------
    # Post-submit close observer. Unknown dialogs are not guessed or force-clicked.
    # They become needs_review after a short grace interval.
    # ------------------------------------------------------------------
    def _wait_composer_closed(self, driver: Any, composer: WebElement) -> None:
        deadline = time.monotonic() + self.POST_CLOSE_TIMEOUT
        unknown_dialog_since: float | None = None
        last_state: str | None = None

        while time.monotonic() < deadline:
            if self._has_security_challenge(driver):
                raise PlatformNeedsReviewError(
                    "Facebook 在最终发布后打开了安全验证，请人工确认帖子状态。",
                    submitted=True,
                )

            try:
                if not composer.is_displayed():
                    emit_platform_progress(
                        "facebook_state",
                        "Facebook UI 状态：composer_closed",
                        {"state": "composer_closed"},
                    )
                    return
            except StaleElementReferenceException:
                emit_platform_progress(
                    "facebook_state",
                    "Facebook UI 状态：composer_closed",
                    {"state": "composer_closed"},
                )
                return

            state = "post_submit_wait"
            try:
                composer_id = composer.id
                other_dialogs = [
                    item
                    for item in self._visible_dialogs(driver)
                    if item.id != composer_id
                ]
            except (StaleElementReferenceException, WebDriverException):
                other_dialogs = []

            if other_dialogs:
                state = "unknown_post_submit_dialog"
                if unknown_dialog_since is None:
                    unknown_dialog_since = time.monotonic()
                elif time.monotonic() - unknown_dialog_since >= self.UNKNOWN_DIALOG_GRACE:
                    raise PlatformNeedsReviewError(
                        "Facebook 最终发布后出现了未识别的新弹窗。系统没有自动点击任何未知操作，"
                        "请人工确认帖子状态后再决定是否重试。",
                        submitted=True,
                    )
            else:
                unknown_dialog_since = None

            if state != last_state:
                emit_platform_progress(
                    "facebook_state",
                    f"Facebook UI 状态：{state}",
                    {"state": state},
                )
                last_state = state
            time.sleep(0.2)

        raise PlatformNeedsReviewError(
            "Facebook 已执行最终发布点击，但 Composer 在等待窗口内仍未关闭。"
            "请人工确认 Facebook 页面，避免重复发布。",
            submitted=True,
        )
