from __future__ import annotations

import time
from typing import Any

from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from app.services.platforms.base import PlatformPublishError
from app.services.platforms.facebook_surface import FacebookSurfaceAdapter


class PreciseFacebookSurfaceAdapter(FacebookSurfaceAdapter):
    """Drive Facebook's composer through the same visible UI a user operates.

    The adapter does not rely on page-sized text ancestors or a synthetic hidden
    action. It resolves the compact visible composer prompt (for example
    ``分享新鲜事`` / ``What's on your mind``), scrolls it into view, performs a
    normal pointer click, then waits for Facebook's Create Post surface.

    Text entry and media upload continue through the visible composer/editor and
    Facebook file input. Actor-ID gates and final publish safety remain inherited.
    """

    _PRIMARY_PROMPTS = (
        "分享新鲜事",
        "分享你的新鲜事吧",
        "分享你的新鲜事",
        "在想些什么",
        "有什么新鲜事",
        "What's on your mind",
        "What’s on your mind",
        "Create post",
        "Create a post",
        "创建帖子",
        "Write something",
        "写点什么",
        "说点什么",
    )

    def _locate_confirmed_surface(
        self,
        driver: Chrome,
    ) -> tuple[WebElement, dict[str, Any]]:
        checked: list[str] = []

        for y in self._composer_scroll_positions(driver):
            try:
                driver.execute_script("window.scrollTo(0, arguments[0]);", y)
            except WebDriverException:
                pass
            time.sleep(0.25)

            entries = self._primary_entry_controls(driver)
            if not entries:
                # Tightly bounded fallback only. Never walk page-sized ancestors.
                entries = self._facebook_entry_controls(driver)[:2]

            for entry in entries[:3]:
                try:
                    fingerprint = self._fingerprint(entry)
                    label = self._fingerprint_text(fingerprint)
                    if label and label not in checked:
                        checked.append(label)

                    self._scroll_entry_into_view(driver, entry)
                    state_before = self._surface_state(driver)

                    # Use a normal pointer interaction first. This is deliberately
                    # different from firing a page-wide JavaScript action: it
                    # follows the visible Facebook UI in the same order a user does.
                    self._pointer_click(driver, entry)
                    located = self._wait_for_surface(driver, state_before, timeout=4.0)

                    # A small number of Facebook builds attach the handler to the
                    # same control but WebDriver's pointer action can be intercepted
                    # by a transient overlay. Retry the same confirmed control once
                    # with WebElement.click(); do not search/click unrelated nodes.
                    if located is None and self._surface_state(driver) == state_before:
                        try:
                            entry.click()
                        except WebDriverException:
                            pass
                        located = self._wait_for_surface(driver, state_before, timeout=3.0)

                    if located is not None:
                        surface, title, editor, post_button = located
                        return surface, {
                            **fingerprint,
                            "surface_title": self._element_label(title) if title else "",
                            "editor": self._element_signature(editor),
                            "post_button": self._element_signature(post_button),
                            "surface": self._element_signature(surface),
                            "strategy": "visible_ui_pointer_click",
                        }

                    self._dismiss_transient_ui(driver)
                except (StaleElementReferenceException, WebDriverException):
                    continue

        sample = " | ".join(checked[-6:])
        suffix = f" 已检查主发帖控件：{sample}" if sample else ""
        raise PlatformPublishError(
            "Facebook 目标页面已打开，但点击可见的“分享新鲜事”输入区后，没有进入“创建帖子”界面。"
            " 系统只操作高置信度的可见发帖输入区，不会遍历或盲点整页控件。"
            f" 页面={driver.current_url or '-'}。{suffix}"
        )

    def _primary_entry_controls(self, driver: Chrome) -> list[WebElement]:
        candidates: dict[str, WebElement] = {}

        def add(element: WebElement | None) -> None:
            if element is None:
                return
            try:
                if not element.is_displayed():
                    return
                if element.find_elements(By.XPATH, "ancestor::*[@role='dialog' or @aria-modal='true']"):
                    return
                rect = element.rect
                width = float(rect.get("width") or 0)
                height = float(rect.get("height") or 0)
                # The main Facebook composer input is a compact horizontal control,
                # not a page-sized ancestor container.
                if width < 120 or height < 20 or height > 180:
                    return
                candidates[element.id] = element
            except (StaleElementReferenceException, WebDriverException):
                return

        for prompt in self._PRIMARY_PROMPTS:
            literal = self._xpath_literal(prompt)

            # Strongest form: the interactive element itself carries the prompt.
            direct_xpath = (
                "//*[(self::button or @role='button' or @role='textbox' or @tabindex='0') and ("
                f"normalize-space(@aria-label)={literal} or "
                f"normalize-space(@aria-placeholder)={literal} or "
                f"normalize-space(@data-placeholder)={literal} or "
                f"normalize-space(.)={literal} or "
                f"contains(normalize-space(@aria-label), {literal}) or "
                f"contains(normalize-space(@aria-placeholder), {literal})"
                ")]"
            )
            try:
                for element in driver.find_elements(By.XPATH, direct_xpath):
                    add(element)
            except WebDriverException:
                pass

            # Chinese Facebook commonly renders ``分享新鲜事`` on a nested div/span.
            # Climb only to the nearest interactive ancestor.
            nested_xpath = (
                "//*[self::span or self::div][normalize-space(.)="
                f"{literal}]/ancestor-or-self::*["
                "self::button or @role='button' or @role='textbox' or @tabindex='0'][1]"
            )
            try:
                for element in driver.find_elements(By.XPATH, nested_xpath):
                    add(element)
            except WebDriverException:
                pass

            # Exact visible prompt node as the final precise fallback. Clicking the
            # node itself is valid because Facebook's React click handler bubbles to
            # the owning composer control, just as a user's pointer click does.
            exact_xpath = f"//*[self::span or self::div][normalize-space(.)={literal}]"
            try:
                for text_node in driver.find_elements(By.XPATH, exact_xpath):
                    add(text_node)
                    add(self._clickable_ancestor(driver, text_node))
            except WebDriverException:
                pass

        return sorted(candidates.values(), key=self._entry_score, reverse=True)

    def _entry_score(self, element: WebElement) -> tuple[int, int, float]:
        try:
            role = (element.get_attribute("role") or "").lower()
            aria = " ".join(
                filter(
                    None,
                    [
                        element.get_attribute("aria-label") or "",
                        element.get_attribute("aria-placeholder") or "",
                        element.get_attribute("data-placeholder") or "",
                    ],
                )
            ).casefold()
            text = " ".join((element.text or "").split()).casefold()
            role_score = 3 if role in {"button", "textbox"} else 1
            prompt_score = 2 if any(p.casefold() in aria for p in self._PRIMARY_PROMPTS) else 1
            exact_score = 3 if any(text == p.casefold() for p in self._PRIMARY_PROMPTS) else 1
            area = float(element.rect.get("width") or 0) * float(element.rect.get("height") or 0)
            return role_score + prompt_score + exact_score, -len(text), -area
        except Exception:
            return (0, 0, 0.0)

    @staticmethod
    def _pointer_click(driver: Chrome, entry: WebElement) -> None:
        try:
            ActionChains(driver).move_to_element(entry).pause(0.1).click().perform()
            return
        except WebDriverException:
            pass
        entry.click()

    @staticmethod
    def _scroll_entry_into_view(driver: Chrome, entry: WebElement) -> None:
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center', inline:'nearest'});",
                entry,
            )
            time.sleep(0.15)
        except Exception:
            pass
