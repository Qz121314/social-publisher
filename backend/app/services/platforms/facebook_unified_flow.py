from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterable

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from app.services.platforms.base import PlatformContent, PlatformNeedsReviewError, PlatformPublishError
from app.services.platforms.facebook_surface import _ACTIVE_SURFACE_CONTENT
from app.services.platforms.facebook_surface_precise import PreciseFacebookSurfaceAdapter


class UnifiedFacebookFlowAdapter(PreciseFacebookSurfaceAdapter):
    """One Facebook publishing flow for every configured target actor.

    The main pipeline is target-type agnostic. Facebook may expose a one-step
    composer (editor -> Post) or a staged composer (editor -> Next -> Post).
    The adapter advances by the controls actually visible in the current composer
    instead of branching on personal-profile versus Page metadata.
    """

    _POST_TEXT = ("Post", "发布", "发帖", "发布帖子")
    _NEXT_TEXT = ("Next", "下一页", "下一步", "继续")
    _SURFACE_TITLES = PreciseFacebookSurfaceAdapter._SURFACE_TITLES + (
        "发帖",
        "Post",
    )

    # ------------------------------------------------------------------
    # Unified surface detection: editor + current primary action.
    # A Page composer can legitimately expose Next instead of final Post.
    # ------------------------------------------------------------------
    def _wait_for_surface(
        self,
        driver: Chrome,
        state_before: tuple[int, int, int],
        *,
        timeout: float,
    ) -> tuple[WebElement, WebElement | None, WebElement, WebElement] | None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            title = self._find_surface_title(driver)
            editors = self._visible_surface_editors(driver)
            actions = self._visible_post_buttons(driver) + self._visible_action_buttons(
                driver,
                self._NEXT_TEXT,
            )

            if editors and actions:
                for editor in editors:
                    for action in actions:
                        surface = self._resolve_surface_root(driver, editor, action, title)
                        if surface is None:
                            continue
                        if title is not None or self._surface_is_modal(surface):
                            return surface, title, editor, action

            if self._surface_state(driver) == state_before:
                time.sleep(0.15)
                continue
            time.sleep(0.15)
        return None

    # ------------------------------------------------------------------
    # Text entry: resolve the real visible editor from the Facebook surface.
    # Do not require a fixed descendant hierarchy.
    # ------------------------------------------------------------------
    def _fill_text(self, composer: WebElement, text: str) -> None:
        if not text:
            return

        driver = composer.parent
        editor = self._find_surface_editor(driver, composer)
        if editor is None:
            editors = self._visible_surface_editors(driver)
            editor = editors[0] if editors else None
        if editor is None:
            raise PlatformPublishError("Facebook 发帖界面已打开，但没有找到可输入正文的编辑区。")

        try:
            editor.click()
            editor.send_keys(text)
        except WebDriverException as exc:
            raise PlatformPublishError(f"Facebook 正文输入失败：{exc}") from exc

        probe = " ".join(text.split())[:24]
        if not probe:
            return

        def text_entered(_: Any) -> bool:
            try:
                current = " ".join(
                    (
                        editor.get_attribute("innerText")
                        or editor.text
                        or editor.get_attribute("textContent")
                        or ""
                    ).split()
                )
                return probe in current or bool(current)
            except StaleElementReferenceException:
                return False

        try:
            WebDriverWait(driver, 8).until(text_entered)
        except TimeoutException as exc:
            raise PlatformPublishError("Facebook 编辑器已点击，但正文没有成功写入。") from exc

    # ------------------------------------------------------------------
    # Media upload: same operation for every actor. Prefer the file input owned by
    # the current composer. If Facebook creates it after clicking Photo/Video,
    # wait for that new input and submit local paths normally.
    # ------------------------------------------------------------------
    def _upload_media(
        self,
        driver: Chrome,
        composer: WebElement,
        media: Iterable[Any],
    ) -> None:
        paths = [str(Path(item.path).resolve()) for item in media]
        missing = [path for path in paths if not Path(path).is_file()]
        if missing:
            raise PlatformPublishError(f"本地媒体文件不存在：{missing[0]}")
        if not paths:
            return

        file_input = self._find_file_input(composer)
        if file_input is None:
            before_ids = {
                item.id
                for item in self._acceptable_file_inputs(driver)
            }
            media_button = self._find_media_button(driver, composer)
            if media_button is None:
                raise PlatformPublishError("Facebook 发帖界面已打开，但没有找到“照片/视频”上传入口。")
            self._safe_click(driver, media_button)
            file_input = self._wait_new_file_input(driver, composer, before_ids)

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

        self._wait_media_processing(driver, composer)

    def _wait_media_processing(self, driver: Chrome, composer: WebElement) -> None:
        start = time.monotonic()
        quiet_since: float | None = None

        while time.monotonic() - start < self.MEDIA_TIMEOUT:
            if self._has_security_challenge(driver):
                raise PlatformNeedsReviewError(
                    "Facebook 在媒体上传期间打开了安全验证，请人工处理后再继续。"
                )

            busy = self._media_is_busy(driver, composer)
            if busy:
                quiet_since = None
            else:
                action = self._find_enabled_post_or_next(driver, composer)
                if action is not None:
                    if quiet_since is None:
                        quiet_since = time.monotonic()
                    elif time.monotonic() - quiet_since >= 1.0:
                        return
            time.sleep(0.4)

        raise TimeoutException("Facebook media processing timed out.")

    # ------------------------------------------------------------------
    # Unified action state machine:
    #   editor -> Post
    #   editor -> Next -> Post
    # Additional Next steps are bounded and remain actor-ID gated.
    # ------------------------------------------------------------------
    def _wait_post_ready(self, driver: Chrome, composer: WebElement) -> WebElement:
        timeout = self.MEDIA_TIMEOUT if self._composer_has_media(composer) else self.DEFAULT_TIMEOUT
        end = time.monotonic() + timeout
        next_steps = 0

        while time.monotonic() < end:
            if self._has_security_challenge(driver):
                raise PlatformNeedsReviewError(
                    "Facebook 在发布前打开了安全验证，请人工处理后再继续。"
                )

            post_button = self._find_post_button_anywhere(driver, composer)
            if post_button is not None and self._is_enabled(post_button):
                content = _ACTIVE_SURFACE_CONTENT.get()
                if content is None:
                    raise PlatformPublishError("Facebook 发布上下文丢失，已停止发布。")
                self._assert_target_actor(driver, content, stage="点击最终发帖按钮前")
                return post_button

            next_button = self._find_action_button(driver, composer, self._NEXT_TEXT)
            if next_button is not None and self._is_enabled(next_button):
                if next_steps >= 3:
                    raise PlatformPublishError("Facebook 发帖流程连续出现过多“下一页”，已停止以避免误操作。")
                content = _ACTIVE_SURFACE_CONTENT.get()
                if content is not None:
                    self._assert_target_actor(driver, content, stage="进入下一步发布界面前")
                self._safe_click(driver, next_button)
                next_steps += 1
                time.sleep(0.6)
                continue

            time.sleep(0.3)

        visible = self._visible_primary_action_labels(driver)
        raise TimeoutException(
            "Facebook composer did not reach a usable Post/Next action before timeout. "
            f"Visible primary actions: {visible or '-'}"
        )

    # ------------------------------------------------------------------
    # Confirmation stays diagnostic only. A Page is considered confirmed when the
    # real editor and its current primary action (Next or Post) are both present.
    # ------------------------------------------------------------------
    def confirm_composer_entry(
        self,
        driver: Chrome,
        content: PlatformContent,
    ) -> dict[str, Any]:
        token = _ACTIVE_SURFACE_CONTENT.set(content)
        try:
            self.prepare_target(driver, content)
            surface, evidence = self._locate_confirmed_surface(driver)
            self._assert_target_actor(driver, content, stage="确认 Facebook 发帖界面后")

            editor = self._find_surface_editor(driver, surface)
            action = self._find_post_button_anywhere(driver, surface)
            action_kind = "post"
            if action is None:
                action = self._find_action_button(driver, surface, self._NEXT_TEXT)
                action_kind = "next"
            if editor is None or action is None:
                raise PlatformPublishError(
                    "Facebook 发帖界面已打开，但没有同时确认到正文编辑器和当前主操作按钮。"
                )

            result = {
                "confirmed": True,
                "target_id": content.target_id,
                "target_name": content.target_name,
                "current_actor_id": self.current_actor_id(driver),
                "current_url": driver.current_url,
                "title": driver.title,
                "entry": {
                    **evidence,
                    "primary_action": action_kind,
                    "primary_action_element": self._element_signature(action),
                },
                "editor_confirmed": True,
                "post_button_confirmed": action_kind == "post",
                "next_button_confirmed": action_kind == "next",
                "primary_action": action_kind,
            }
            self._close_surface_without_submitting(driver, surface)
            return result
        finally:
            _ACTIVE_SURFACE_CONTENT.reset(token)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _find_post_button_anywhere(
        self,
        driver: Chrome,
        composer: WebElement,
    ) -> WebElement | None:
        button = self._find_post_button(composer)
        if button is not None:
            return button
        buttons = self._visible_post_buttons(driver)
        return buttons[0] if buttons else None

    def _find_enabled_post_or_next(
        self,
        driver: Chrome,
        composer: WebElement,
    ) -> WebElement | None:
        post = self._find_post_button_anywhere(driver, composer)
        if post is not None and self._is_enabled(post):
            return post
        nxt = self._find_action_button(driver, composer, self._NEXT_TEXT)
        if nxt is not None and self._is_enabled(nxt):
            return nxt
        return None

    def _find_action_button(
        self,
        driver: Chrome,
        composer: WebElement,
        texts: tuple[str, ...],
    ) -> WebElement | None:
        for root in (composer, driver):
            result = self._visible_action_buttons(root, texts)
            if result:
                return result[0]
        return None

    def _visible_action_buttons(
        self,
        root: Chrome | WebElement,
        texts: tuple[str, ...],
    ) -> list[WebElement]:
        result: list[WebElement] = []
        seen: set[str] = set()
        for text in texts:
            literal = self._xpath_literal(text)
            xpaths = (
                ".//*[(self::button or @role='button') and "
                f"(normalize-space(.)={literal} or normalize-space(@aria-label)={literal})]",
                ".//*[self::span or self::div][normalize-space(.)="
                f"{literal}]/ancestor::*[self::button or @role='button'][1]",
            )
            for xpath in xpaths:
                try:
                    elements = root.find_elements(By.XPATH, xpath)
                except WebDriverException:
                    continue
                for element in elements:
                    try:
                        if not element.is_displayed() or element.id in seen:
                            continue
                        seen.add(element.id)
                        result.append(element)
                    except StaleElementReferenceException:
                        continue
        return result

    def _find_media_button(
        self,
        driver: Chrome,
        composer: WebElement,
    ) -> WebElement | None:
        for root in (composer, driver):
            for text in self._MEDIA_TEXT:
                literal = self._xpath_literal(text)
                xpath = (
                    ".//*[(self::button or @role='button' or @tabindex='0') and ("
                    f"contains(normalize-space(@aria-label), {literal}) or "
                    f"contains(normalize-space(.), {literal})"
                    ")]"
                )
                try:
                    elements = root.find_elements(By.XPATH, xpath)
                except WebDriverException:
                    continue
                for element in elements:
                    try:
                        if element.is_displayed():
                            return element
                    except StaleElementReferenceException:
                        continue
        return None

    def _acceptable_file_inputs(self, root: Chrome | WebElement) -> list[WebElement]:
        result: list[WebElement] = []
        try:
            elements = root.find_elements(By.CSS_SELECTOR, "input[type='file']")
        except WebDriverException:
            return result
        for element in elements:
            try:
                accept = (element.get_attribute("accept") or "").lower()
                if not accept or "image" in accept or "video" in accept:
                    result.append(element)
            except StaleElementReferenceException:
                continue
        return result

    def _wait_new_file_input(
        self,
        driver: Chrome,
        composer: WebElement,
        before_ids: set[str],
    ) -> WebElement:
        def locate(_: Any) -> WebElement | bool:
            local = self._acceptable_file_inputs(composer)
            if local:
                return local[-1]
            global_inputs = self._acceptable_file_inputs(driver)
            for item in reversed(global_inputs):
                if item.id not in before_ids:
                    return item
            return False

        try:
            return WebDriverWait(driver, 12).until(locate)
        except TimeoutException as exc:
            raise PlatformPublishError("已点击 Facebook“照片/视频”，但没有出现可用的文件上传控件。") from exc

    def _wait_any_composer_file_input(
        self,
        driver: Chrome,
        composer: WebElement,
    ) -> WebElement:
        return WebDriverWait(driver, 12).until(
            lambda _: (
                (self._acceptable_file_inputs(composer) or self._acceptable_file_inputs(driver))[-1]
                if (self._acceptable_file_inputs(composer) or self._acceptable_file_inputs(driver))
                else False
            )
        )

    def _media_is_busy(self, driver: Chrome, composer: WebElement) -> bool:
        for root in (composer, driver):
            try:
                if any(
                    item.is_displayed()
                    for item in root.find_elements(By.CSS_SELECTOR, "[role='progressbar']")
                ):
                    return True
                text = (root.text or "").casefold()
                if any(marker.casefold() in text for marker in self._UPLOAD_BUSY_TEXT):
                    return True
            except (StaleElementReferenceException, WebDriverException):
                continue
        return False

    def _visible_primary_action_labels(self, driver: Chrome) -> str:
        labels: list[str] = []
        for element in self._visible_post_buttons(driver) + self._visible_action_buttons(
            driver,
            self._NEXT_TEXT,
        ):
            label = self._element_label(element)
            if label and label not in labels:
                labels.append(label)
        return " | ".join(labels[:8])
