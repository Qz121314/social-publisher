from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any

from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement

from app.services.platforms.base import PlatformContent, PlatformPublishError
from app.services.platforms.facebook_target import TargetActorFacebookAdapter


_ACTIVE_SURFACE_CONTENT: ContextVar[PlatformContent | None] = ContextVar(
    "facebook_active_surface_content",
    default=None,
)


class FacebookSurfaceAdapter(TargetActorFacebookAdapter):
    """Facebook adapter that models the real create-post surface.

    Facebook desktop does not guarantee that the editor and final Post button are
    descendants of one fixed ``role=dialog`` node. The visible UI is nevertheless
    stable at the interaction level: a feed/profile composer card opens a
    create-post surface, that surface exposes one editor, and it exposes a Post
    action (disabled while empty is normal).

    This adapter confirms those states across the visible Facebook layer instead
    of relying on one brittle container hierarchy. Target authorization remains
    exclusively actor-ID based in ``TargetActorFacebookAdapter``.
    """

    _SURFACE_TITLES = (
        "Create post",
        "Create Post",
        "创建帖子",
        "建立帖子",
        "建立貼文",
    )
    _ENTRY_PROMPTS = (
        "What's on your mind",
        "What’s on your mind",
        "Share something",
        "Create post",
        "Create a post",
        "Write something",
        "Share an update",
        "分享新鲜事",
        "分享你的新鲜事吧",
        "分享你的新鲜事",
        "在想些什么",
        "有什么新鲜事",
        "写点什么",
        "说点什么",
        "发布动态",
    )

    def publish(self, driver: Chrome, content: PlatformContent) -> dict[str, Any]:
        token = _ACTIVE_SURFACE_CONTENT.set(content)
        try:
            return super().publish(driver, content)
        finally:
            _ACTIVE_SURFACE_CONTENT.reset(token)

    def _open_composer(self, driver: Chrome) -> WebElement:
        surface, _ = self._locate_confirmed_surface(driver)
        content = _ACTIVE_SURFACE_CONTENT.get()
        if content is not None:
            self._assert_target_actor(driver, content, stage="创建帖子界面打开后")
        return surface

    def confirm_composer_entry(
        self,
        driver: Chrome,
        content: PlatformContent,
    ) -> dict[str, Any]:
        """Confirm Facebook's real create-post UI without typing or submitting."""
        token = _ACTIVE_SURFACE_CONTENT.set(content)
        try:
            self.prepare_target(driver, content)
            surface, evidence = self._locate_confirmed_surface(driver)
            self._assert_target_actor(driver, content, stage="确认创建帖子界面后")

            editor = self._find_surface_editor(driver, surface)
            post_button = self._find_surface_post_button(driver, surface)
            if editor is None or post_button is None:
                raise PlatformPublishError(
                    "Facebook 创建帖子界面曾打开，但最终确认时编辑器或发帖按钮已消失。"
                )

            result = {
                "confirmed": True,
                "target_id": content.target_id,
                "target_name": content.target_name,
                "current_actor_id": self.current_actor_id(driver),
                "current_url": driver.current_url,
                "title": driver.title,
                "entry": evidence,
                "editor_confirmed": True,
                "post_button_confirmed": True,
                "post_button_enabled": self._is_enabled(post_button),
            }
            self._close_surface_without_submitting(driver, surface)
            return result
        finally:
            _ACTIVE_SURFACE_CONTENT.reset(token)

    def _locate_confirmed_surface(
        self,
        driver: Chrome,
    ) -> tuple[WebElement, dict[str, Any]]:
        checked: list[str] = []

        # Profile and Page layouts can place the composer card lower on the page.
        for y in self._composer_scroll_positions(driver):
            try:
                driver.execute_script("window.scrollTo(0, arguments[0]);", y)
            except WebDriverException:
                pass
            time.sleep(0.45)

            for entry in self._facebook_entry_controls(driver):
                try:
                    fingerprint = self._fingerprint(entry)
                    label = self._fingerprint_text(fingerprint)
                    if label:
                        checked.append(label)

                    state_before = self._surface_state(driver)
                    self._safe_click(driver, entry)
                    located = self._wait_for_surface(driver, state_before, timeout=8.0)
                    if located is not None:
                        surface, title, editor, post_button = located
                        evidence = {
                            **fingerprint,
                            "surface_title": self._element_label(title) if title else "",
                            "editor": self._element_signature(editor),
                            "post_button": self._element_signature(post_button),
                            "surface": self._element_signature(surface),
                        }
                        return surface, evidence

                    # The clicked control was not the composer. Reset transient UI
                    # before trying another Facebook control.
                    self._dismiss_transient_ui(driver)
                except (StaleElementReferenceException, WebDriverException):
                    continue

        sample = " | ".join(checked[-8:])
        suffix = f" 已点击检查：{sample}" if sample else ""
        raise PlatformPublishError(
            "Facebook 发帖卡片已搜索，但没有确认到完整的“创建帖子”界面。"
            " 确认条件为：创建帖子界面 + 可编辑正文区域 + 发帖按钮（灰色也算）。"
            f" 页面={driver.current_url or '-'}。{suffix}"
        )

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
            post_buttons = self._visible_post_buttons(driver)

            if editors and post_buttons:
                for editor in editors:
                    for post_button in post_buttons:
                        surface = self._resolve_surface_root(driver, editor, post_button, title)
                        if surface is None:
                            continue

                        # Strong Facebook evidence: explicit Create Post title, or
                        # a newly-created modal/dialog layer containing both controls.
                        if title is not None or self._surface_is_modal(surface):
                            return surface, title, editor, post_button

            # Avoid accepting the profile/page background composer itself when no
            # new create-post UI appeared after the click.
            current = self._surface_state(driver)
            if current == state_before:
                time.sleep(0.2)
                continue
            time.sleep(0.2)
        return None

    def _facebook_entry_controls(self, driver: Chrome) -> list[WebElement]:
        result: list[WebElement] = []
        seen: set[str] = set()

        def add(element: WebElement | None) -> None:
            if element is None:
                return
            try:
                if not element.is_displayed():
                    return
                if element.find_elements(By.XPATH, "ancestor::*[@role='dialog']"):
                    return
                key = element.id
                if key in seen:
                    return
                seen.add(key)
                result.append(element)
            except (StaleElementReferenceException, WebDriverException):
                return

        # Facebook composer cards expose localized prompt text. Match the nested
        # text first, then climb only to the nearest clickable control.
        for text in self._ENTRY_PROMPTS:
            literal = self._xpath_literal(text)
            xpath = (
                "//*[contains(normalize-space(@aria-label), "
                f"{literal}) or contains(normalize-space(@aria-placeholder), {literal}) or "
                f"contains(normalize-space(@data-placeholder), {literal}) or "
                f"contains(normalize-space(.), {literal})]"
            )
            try:
                elements = driver.find_elements(By.XPATH, xpath)
            except WebDriverException:
                elements = []
            for element in elements:
                add(self._clickable_ancestor(driver, element) or element)

        # Current Facebook profile layout often renders the prompt in a visually
        # button-like element without a useful accessible name. Keep a structural
        # fallback, but only when its visible text still looks like a composer.
        try:
            structural = driver.find_elements(
                By.CSS_SELECTOR,
                "[role='button'], [role='textbox'], [tabindex='0'], [contenteditable='true']",
            )
        except WebDriverException:
            structural = []
        folded_prompts = tuple(value.casefold() for value in self._ENTRY_PROMPTS)
        for element in structural:
            try:
                if not element.is_displayed():
                    continue
                label = self._element_label(element).casefold()
                if label and any(prompt in label for prompt in folded_prompts):
                    add(self._clickable_ancestor(driver, element) or element)
            except StaleElementReferenceException:
                continue

        return result

    def _find_surface_title(self, driver: Chrome) -> WebElement | None:
        for text in self._SURFACE_TITLES:
            literal = self._xpath_literal(text)
            xpath = (
                "//*[self::h1 or self::h2 or self::h3 or @role='heading' or self::span or self::div]"
                f"[normalize-space(.)={literal} or normalize-space(@aria-label)={literal}]"
            )
            try:
                elements = driver.find_elements(By.XPATH, xpath)
            except WebDriverException:
                continue
            for element in elements:
                try:
                    if element.is_displayed():
                        return element
                except StaleElementReferenceException:
                    continue
        return None

    def _visible_surface_editors(self, driver: Chrome) -> list[WebElement]:
        selectors = (
            "[role='textbox'][contenteditable='true']",
            "[contenteditable='true'][data-lexical-editor='true']",
            "[contenteditable='true'][aria-label]",
            "[contenteditable='true'][aria-placeholder]",
            "[contenteditable='true'][data-placeholder]",
            "[contenteditable='true']",
            "textarea",
        )
        found: list[WebElement] = []
        seen: set[str] = set()
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
            except WebDriverException:
                continue
            for element in elements:
                try:
                    if not element.is_displayed() or element.id in seen:
                        continue
                    rect = element.rect
                    if float(rect.get("width") or 0) < 80 or float(rect.get("height") or 0) < 20:
                        continue
                    seen.add(element.id)
                    found.append(element)
                except (StaleElementReferenceException, WebDriverException):
                    continue

        # Prefer editors inside a modal/dialog and then larger editors. This puts
        # the real Create Post editor ahead of the background profile prompt.
        def score(element: WebElement) -> tuple[int, float]:
            try:
                modal = bool(
                    element.find_elements(
                        By.XPATH,
                        "ancestor::*[@role='dialog' or @aria-modal='true'][1]",
                    )
                )
                area = float(element.rect.get("width") or 0) * float(element.rect.get("height") or 0)
                return (1 if modal else 0, area)
            except Exception:
                return (0, 0.0)

        return sorted(found, key=score, reverse=True)

    def _visible_post_buttons(self, driver: Chrome) -> list[WebElement]:
        result: list[WebElement] = []
        seen: set[str] = set()
        for text in self._POST_TEXT:
            literal = self._xpath_literal(text)
            xpaths = (
                "//*[(self::button or @role='button') and "
                f"(normalize-space(.)={literal} or normalize-space(@aria-label)={literal})]",
                "//*[self::span or self::div][normalize-space(.)="
                f"{literal}]/ancestor::*[self::button or @role='button'][1]",
            )
            for xpath in xpaths:
                try:
                    elements = driver.find_elements(By.XPATH, xpath)
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

        def score(element: WebElement) -> tuple[int, float]:
            try:
                modal = bool(
                    element.find_elements(
                        By.XPATH,
                        "ancestor::*[@role='dialog' or @aria-modal='true'][1]",
                    )
                )
                return (1 if modal else 0, float(element.rect.get("y") or 0))
            except Exception:
                return (0, 0.0)

        return sorted(result, key=score, reverse=True)

    def _resolve_surface_root(
        self,
        driver: Chrome,
        editor: WebElement,
        post_button: WebElement,
        title: WebElement | None,
    ) -> WebElement | None:
        try:
            root = driver.execute_script(
                """
                const editor = arguments[0];
                const button = arguments[1];
                const title = arguments[2];
                let cur = editor;
                while (cur && cur !== document.body) {
                  if (cur.contains(button) && (!title || cur.contains(title))) return cur;
                  cur = cur.parentElement;
                }
                const modal = editor.closest('[role="dialog"], [aria-modal="true"]');
                if (modal && modal.contains(button)) return modal;
                return null;
                """,
                editor,
                post_button,
                title,
            )
            if root is not None and root.is_displayed():
                return root
        except Exception:
            pass

        # Last fallback: a real role=dialog containing the editor; the Post button
        # may be rendered through a sibling portal, so global lookup remains valid.
        try:
            dialogs = editor.find_elements(By.XPATH, "ancestor::*[@role='dialog' or @aria-modal='true']")
            for dialog in dialogs:
                if dialog.is_displayed():
                    return dialog
        except Exception:
            pass
        return None

    def _find_surface_editor(self, driver: Chrome, surface: WebElement) -> WebElement | None:
        try:
            for editor in self._visible_surface_editors(driver):
                if self._element_inside(driver, surface, editor):
                    return editor
        except Exception:
            pass
        return None

    def _find_surface_post_button(self, driver: Chrome, surface: WebElement) -> WebElement | None:
        # Prefer descendants, but allow Facebook portal siblings when the surface
        # itself is a modal/dialog. Confirmation is based on the whole visible UI.
        button = self._find_post_button(surface)
        if button is not None:
            return button
        if self._surface_is_modal(surface):
            buttons = self._visible_post_buttons(driver)
            return buttons[0] if buttons else None
        return None

    @staticmethod
    def _surface_is_modal(surface: WebElement) -> bool:
        try:
            role = (surface.get_attribute("role") or "").lower()
            aria_modal = (surface.get_attribute("aria-modal") or "").lower()
            if role == "dialog" or aria_modal == "true":
                return True
            return bool(
                surface.find_elements(
                    By.XPATH,
                    "ancestor-or-self::*[@role='dialog' or @aria-modal='true'][1]",
                )
            )
        except Exception:
            return False

    @staticmethod
    def _surface_state(driver: Chrome) -> tuple[int, int, int]:
        try:
            dialogs = sum(1 for item in driver.find_elements(By.CSS_SELECTOR, "[role='dialog'], [aria-modal='true']") if item.is_displayed())
            editables = sum(1 for item in driver.find_elements(By.CSS_SELECTOR, "[contenteditable='true'], [role='textbox'], textarea") if item.is_displayed())
            buttons = sum(1 for item in driver.find_elements(By.CSS_SELECTOR, "button, [role='button']") if item.is_displayed())
            return dialogs, editables, buttons
        except Exception:
            return (0, 0, 0)

    @staticmethod
    def _element_inside(driver: Chrome, root: WebElement, child: WebElement) -> bool:
        try:
            return bool(driver.execute_script("return arguments[0] === arguments[1] || arguments[0].contains(arguments[1]);", root, child))
        except Exception:
            return False

    @staticmethod
    def _element_label(element: WebElement | None) -> str:
        if element is None:
            return ""
        try:
            return " ".join(
                filter(
                    None,
                    [
                        element.get_attribute("aria-label") or "",
                        element.get_attribute("aria-placeholder") or "",
                        element.get_attribute("data-placeholder") or "",
                        element.text or "",
                    ],
                )
            ).strip()[:180]
        except Exception:
            return ""

    def _element_signature(self, element: WebElement) -> dict[str, Any]:
        try:
            return {
                "tag": (element.tag_name or "").lower(),
                "role": element.get_attribute("role") or "",
                "aria_label": element.get_attribute("aria-label") or "",
                "aria_placeholder": element.get_attribute("aria-placeholder") or "",
                "contenteditable": element.get_attribute("contenteditable") or "",
                "disabled": element.get_attribute("aria-disabled") or "",
                "text": " ".join((element.text or "").split())[:180],
            }
        except Exception:
            return {}

    def _close_surface_without_submitting(self, driver: Chrome, surface: WebElement) -> None:
        # Confirmation must leave no draft and must never click the final Post action.
        try:
            surface.send_keys(Keys.ESCAPE)
            time.sleep(0.35)
            if not surface.is_displayed():
                return
        except Exception:
            pass

        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.35)
        except Exception:
            pass
