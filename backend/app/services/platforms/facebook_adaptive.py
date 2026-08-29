from __future__ import annotations

import time
from typing import Any

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from app.services.platforms.base import PlatformPublishError
from app.services.platforms.facebook import FacebookAdapter


class AdaptiveFacebookAdapter(FacebookAdapter):
    """Facebook adapter with broader desktop composer selectors.

    Facebook renders the "create post" entry differently across personal
    profiles, Pages, languages and account experiments. The base adapter keeps
    the publishing safety model; this subclass only broadens UI discovery.
    """

    _COMPOSER_EXTRA_TEXT = (
        "Create post",
        "Create Post",
        "Write something",
        "Write something...",
        "Share an update",
        "发帖",
        "发布动态",
        "说点什么",
        "写点什么",
    )

    def _open_composer(self, driver: Chrome) -> WebElement:
        dialogs_before = self._visible_dialogs(driver)
        opener = self._wait_composer_opener(driver)
        self._safe_click(driver, opener)

        def locate_composer(_: Chrome) -> WebElement | bool:
            dialogs = self._visible_dialogs(driver)
            for dialog in dialogs:
                if dialog not in dialogs_before and self._has_editable(dialog):
                    return dialog
            for dialog in reversed(dialogs):
                if self._has_editable(dialog):
                    return dialog

            # Some Facebook variants expose the editor before the dialog gets
            # a role=dialog attribute. Resolve the nearest sensible container.
            for editable in self._visible_editables(driver):
                container = self._nearest_composer_container(driver, editable)
                if container is not None:
                    return container
            return False

        try:
            return WebDriverWait(driver, self.DEFAULT_TIMEOUT).until(locate_composer)
        except TimeoutException as exc:
            raise PlatformPublishError(
                "已点击 Facebook 发帖入口，但没有检测到可编辑的发帖窗口。"
                f" 当前页面：{driver.current_url or '-'}；标题：{driver.title or '-'}。"
            ) from exc

    def _wait_composer_opener(self, driver: Chrome) -> WebElement:
        texts = self._COMPOSER_TEXT + self._COMPOSER_EXTRA_TEXT

        def locate(_: Chrome) -> WebElement | bool:
            # 1) Stable accessibility attributes first.
            for text in texts:
                literal = self._xpath_literal(text)
                xpath = (
                    "//*[(@role='button' or @role='textbox' or @tabindex='0') and ("
                    f"contains(normalize-space(@aria-label), {literal}) or "
                    f"contains(normalize-space(@aria-placeholder), {literal}) or "
                    f"contains(normalize-space(@data-placeholder), {literal}) or "
                    f"contains(normalize-space(.), {literal})"
                    ")]"
                )
                element = self._first_visible(driver.find_elements(By.XPATH, xpath))
                if element is not None:
                    return element

            # 2) Text is sometimes rendered on a nested span while the clickable
            # ancestor carries role/button semantics.
            for text in texts:
                literal = self._xpath_literal(text)
                xpath = (
                    "//*[self::span or self::div][contains(normalize-space(.), "
                    f"{literal})]/ancestor-or-self::*["
                    "@role='button' or @role='textbox' or @tabindex='0'][1]"
                )
                element = self._first_visible(driver.find_elements(By.XPATH, xpath))
                if element is not None:
                    return element

            # 3) A profile/page may expose a readonly-looking contenteditable as
            # the composer trigger. Only accept visible elements outside dialogs.
            for element in driver.find_elements(
                By.CSS_SELECTOR,
                "div[contenteditable='true'][role='textbox'], [contenteditable='true'][aria-label]",
            ):
                try:
                    if not element.is_displayed():
                        continue
                    if element.find_elements(By.XPATH, "ancestor::*[@role='dialog']"):
                        continue
                    label = " ".join(
                        filter(
                            None,
                            [
                                element.get_attribute("aria-label") or "",
                                element.get_attribute("aria-placeholder") or "",
                                element.text or "",
                            ],
                        )
                    ).casefold()
                    if any(text.casefold() in label for text in texts):
                        return element
                except StaleElementReferenceException:
                    continue
            return False

        try:
            return WebDriverWait(driver, self.DEFAULT_TIMEOUT).until(locate)
        except TimeoutException as exc:
            hints = self._composer_diagnostics(driver)
            raise PlatformPublishError(
                "未找到 Facebook 的发帖入口。已尝试 button、textbox、aria-label、"
                "aria-placeholder 和可点击文本等多种桌面布局。"
                f" 页面：{driver.current_url or '-'}；标题：{driver.title or '-'}。{hints}"
            ) from exc

    def _find_post_button(self, composer: WebElement) -> WebElement | None:
        for text in self._POST_TEXT:
            literal = self._xpath_literal(text)
            selectors = (
                (
                    By.XPATH,
                    ".//*[(@role='button' or self::button) and ("
                    f"normalize-space(@aria-label)={literal} or "
                    f"normalize-space(.)={literal})]",
                ),
                (
                    By.XPATH,
                    ".//*[self::span or self::div][normalize-space(.)="
                    f"{literal}]/ancestor::*[@role='button' or self::button][1]",
                ),
            )
            for by, selector in selectors:
                element = self._first_visible(composer.find_elements(by, selector))
                if element is not None:
                    return element
        return None

    @staticmethod
    def _first_visible(elements: list[WebElement]) -> WebElement | None:
        for element in elements:
            try:
                if element.is_displayed():
                    return element
            except StaleElementReferenceException:
                continue
        return None

    @staticmethod
    def _visible_editables(driver: Chrome) -> list[WebElement]:
        result: list[WebElement] = []
        selectors = (
            "div[role='textbox'][contenteditable='true']",
            "[contenteditable='true'][data-lexical-editor='true']",
            "[contenteditable='true'][aria-label]",
        )
        for selector in selectors:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                try:
                    if element.is_displayed():
                        result.append(element)
                except StaleElementReferenceException:
                    continue
        return result

    def _has_editable(self, root: WebElement) -> bool:
        try:
            return bool(
                root.find_elements(
                    By.CSS_SELECTOR,
                    "div[role='textbox'][contenteditable='true'], "
                    "[contenteditable='true'][data-lexical-editor='true'], "
                    "[contenteditable='true'][aria-label]",
                )
            )
        except StaleElementReferenceException:
            return False

    def _nearest_composer_container(
        self,
        driver: Chrome,
        editable: WebElement,
    ) -> WebElement | None:
        try:
            container = driver.execute_script(
                "return arguments[0].closest('[role=dialog]') || "
                "arguments[0].closest('form') || "
                "arguments[0].parentElement?.parentElement?.parentElement || null;",
                editable,
            )
            if container is not None and container.is_displayed():
                return container
        except Exception:
            return None
        return None

    def _composer_diagnostics(self, driver: Chrome) -> str:
        snippets: list[str] = []
        try:
            elements = driver.find_elements(
                By.CSS_SELECTOR,
                "[role='button'][aria-label], [role='textbox'][aria-label], [aria-placeholder]",
            )[:80]
            for element in elements:
                try:
                    if not element.is_displayed():
                        continue
                    value = (
                        element.get_attribute("aria-label")
                        or element.get_attribute("aria-placeholder")
                        or element.text
                        or ""
                    ).strip()
                    if value and value not in snippets:
                        snippets.append(value[:80])
                    if len(snippets) >= 8:
                        break
                except StaleElementReferenceException:
                    continue
        except Exception:
            return ""

        if not snippets:
            return ""
        return " 页面可见控件示例：" + " | ".join(snippets)
