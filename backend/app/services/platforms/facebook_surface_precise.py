from __future__ import annotations

import time
from typing import Any

from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from app.services.platforms.base import PlatformPublishError
from app.services.platforms.facebook_surface import FacebookSurfaceAdapter


class PreciseFacebookSurfaceAdapter(FacebookSurfaceAdapter):
    """Prefer Facebook's real composer-card input over broad page text matches.

    Facebook profile/Page documents contain large ancestor nodes whose text also
    includes the composer prompt. Treating every such ancestor as a candidate can
    make automation appear stuck because each false candidate waits for a modal.

    This adapter first resolves the compact, interactive prompt control visible in
    the actual composer card (for example ``分享新鲜事`` / ``What's on your mind``),
    tries only a few high-confidence controls, and verifies the resulting Create
    Post surface. The actor-ID gates and final publish safety remain inherited.
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
            time.sleep(0.3)

            entries = self._primary_entry_controls(driver)
            if not entries:
                # Keep a tightly bounded fallback for layouts whose prompt lacks
                # normal button/textbox semantics. Never iterate the whole page.
                entries = self._facebook_entry_controls(driver)[:3]

            for entry in entries[:4]:
                try:
                    fingerprint = self._fingerprint(entry)
                    label = self._fingerprint_text(fingerprint)
                    if label and label not in checked:
                        checked.append(label)

                    self._scroll_entry_into_view(driver, entry)
                    state_before = self._surface_state(driver)

                    # Native click first: this is closest to a real user click and
                    # works for the current Facebook composer card.
                    self._safe_click(driver, entry)
                    located = self._wait_for_surface(driver, state_before, timeout=4.0)

                    # Some FB builds attach the click handler to a nested/parent
                    # React node while Selenium's native click lands on a child.
                    # If nothing opened, invoke that same confirmed control once
                    # through DOM click; this is not a blind page-wide JS action.
                    if located is None and self._surface_state(driver) == state_before:
                        try:
                            driver.execute_script("arguments[0].click();", entry)
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
                            "strategy": "precise_composer_card",
                        }

                    self._dismiss_transient_ui(driver)
                except (StaleElementReferenceException, WebDriverException):
                    continue

        sample = " | ".join(checked[-6:])
        suffix = f" 已检查主发帖控件：{sample}" if sample else ""
        raise PlatformPublishError(
            "Facebook 目标页面已打开，但主发帖卡片没有成功进入“创建帖子”界面。"
            " 系统只检查了高置信度的发帖输入区域，不再遍历整页候选控件。"
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
                # The main FB composer input is a compact horizontal control, not
                # a page-sized ancestor container.
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

            # Current Chinese Facebook commonly renders ``分享新鲜事`` on a nested
            # div/span. Climb only to the nearest interactive ancestor.
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

            # Last precise form: exact prompt node, then the inherited clickable
            # ancestor resolver. Exact text prevents page-sized ancestor matches.
            exact_xpath = f"//*[self::span or self::div][normalize-space(.)={literal}]"
            try:
                for text_node in driver.find_elements(By.XPATH, exact_xpath):
                    add(self._clickable_ancestor(driver, text_node) or text_node)
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
            exact_score = 2 if any(text == p.casefold() for p in self._PRIMARY_PROMPTS) else 1
            area = float(element.rect.get("width") or 0) * float(element.rect.get("height") or 0)
            # Smaller compact controls beat broad card/page ancestors.
            return role_score + prompt_score + exact_score, -len(text), -area
        except Exception:
            return (0, 0, 0.0)

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
