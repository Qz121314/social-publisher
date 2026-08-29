from __future__ import annotations

import time
from typing import Any

from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from app.services.platforms.base import PlatformContent, PlatformPublishError
from app.services.platforms.facebook_adaptive import AdaptiveFacebookAdapter


class IdentityAwareFacebookAdapter(AdaptiveFacebookAdapter):
    """Facebook adapter that switches the active publishing identity first.

    Navigating to a personal profile or Page URL does not necessarily change
    Facebook's active actor. New Pages Experience keeps the current actor in the
    session. We therefore verify `c_user` / `i_user`, use Facebook's visible
    account/profile switcher when needed, verify the actor changed, and only then
    navigate to the configured publish target.
    """

    _ACCOUNT_MENU_LABELS = (
        "Account",
        "Your profile",
        "Profile",
        "账户",
        "帐户",
        "账号",
        "你的个人主页",
        "个人主页",
        "个人资料",
    )
    _SEE_ALL_PROFILES_TEXT = (
        "See all profiles",
        "Switch profile",
        "Switch profiles",
        "All profiles",
        "查看所有个人主页",
        "查看所有个人资料",
        "查看全部个人主页",
        "切换个人主页",
        "切换个人资料",
        "所有个人主页",
    )

    def _navigate_to_target(self, driver: Chrome, content: PlatformContent) -> None:
        self._ensure_target_identity(driver, content)
        super()._navigate_to_target(driver, content)

    def _ensure_target_identity(self, driver: Chrome, content: PlatformContent) -> None:
        expected_actor = (content.target_id or "").strip()
        if not expected_actor:
            raise PlatformPublishError("Facebook 发布目标缺少身份 ID，已停止发布。")

        c_user = self._cookie_value(driver, "c_user")
        current_actor = self._current_actor_id(driver)

        # The personal profile discovered by the scanner is the c_user account.
        # A Page actor is normally represented by i_user.
        if content.target_type == "profile" and c_user and expected_actor != c_user:
            raise PlatformPublishError(
                "Facebook 个人主页目标与当前登录账号不一致，已停止发布。"
                f" 登录账号={c_user}，目标={expected_actor}。"
            )

        if current_actor == expected_actor:
            return

        self._open_facebook_home(driver)
        current_actor = self._current_actor_id(driver)
        if current_actor == expected_actor:
            return

        opener = self._find_account_menu_opener(driver)
        if opener is None:
            raise PlatformPublishError(
                "需要切换 Facebook 发布身份，但没有找到右上角账号菜单。"
                f" 当前身份={current_actor or '-'}，目标={content.target_name or expected_actor}。"
                + self._switcher_diagnostics(driver)
            )

        self._safe_click(driver, opener)
        time.sleep(0.8)

        # Some layouts show all identities immediately; others require one more
        # click on See all profiles / Switch profile.
        target_control = self._find_identity_control(driver, content)
        if target_control is None:
            expand = self._find_switcher_expand_control(driver)
            if expand is not None:
                self._safe_click(driver, expand)
                time.sleep(0.8)
                target_control = self._find_identity_control(driver, content)

        if target_control is None:
            raise PlatformPublishError(
                "Facebook 账号菜单已打开，但没有找到设定的发布身份。"
                f" 目标={content.target_name or expected_actor} ({expected_actor})。"
                + self._switcher_diagnostics(driver)
            )

        self._safe_click(driver, target_control)

        end = time.monotonic() + 25
        last_actor: str | None = None
        while time.monotonic() < end:
            try:
                WebDriverWait(driver, 3).until(
                    lambda browser: browser.execute_script("return document.readyState")
                    in ("interactive", "complete")
                )
            except Exception:
                pass

            last_actor = self._current_actor_id(driver)
            if last_actor == expected_actor:
                return
            time.sleep(0.5)

        raise PlatformPublishError(
            "已点击 Facebook 身份切换项，但身份校验没有通过，已停止发布以避免发错主页。"
            f" 当前身份={last_actor or '-'}，目标身份={expected_actor}。"
        )

    def _open_facebook_home(self, driver: Chrome) -> None:
        try:
            driver.get(self.HOME_URL)
            WebDriverWait(driver, self.DEFAULT_TIMEOUT).until(
                lambda browser: browser.execute_script("return document.readyState")
                in ("interactive", "complete")
            )
        except WebDriverException as exc:
            raise PlatformPublishError(f"打开 Facebook 首页准备切换身份时失败：{exc}") from exc

    def _find_account_menu_opener(self, driver: Chrome) -> WebElement | None:
        candidates: list[WebElement] = []
        try:
            elements = driver.find_elements(
                By.CSS_SELECTOR,
                "[role='button'][aria-label], a[role='button'][aria-label]",
            )
        except WebDriverException:
            return None

        labels = tuple(value.casefold() for value in self._ACCOUNT_MENU_LABELS)
        for element in elements:
            try:
                if not element.is_displayed():
                    continue
                label = " ".join(
                    filter(
                        None,
                        [
                            element.get_attribute("aria-label") or "",
                            element.get_attribute("title") or "",
                            element.text or "",
                        ],
                    )
                ).casefold()
                if any(token in label for token in labels):
                    candidates.append(element)
            except StaleElementReferenceException:
                continue

        if not candidates:
            return None

        # Facebook's account/avatar control is normally the right-most matching
        # control in the top navigation. Prefer it over profile-related buttons in
        # the page body.
        def x_position(element: WebElement) -> float:
            try:
                return float(element.rect.get("x") or 0)
            except Exception:
                return 0

        return max(candidates, key=x_position)

    def _find_switcher_expand_control(self, driver: Chrome) -> WebElement | None:
        for text in self._SEE_ALL_PROFILES_TEXT:
            control = self._find_clickable_by_text(driver, text, right_half_only=True)
            if control is not None:
                return control
        return None

    def _find_identity_control(
        self,
        driver: Chrome,
        content: PlatformContent,
    ) -> WebElement | None:
        name = " ".join((content.target_name or "").split()).strip()
        expected_actor = (content.target_id or "").strip()

        # Prefer the visible identity name in the opened account switcher.
        if name and name.casefold() not in {"个人主页", "profile"}:
            control = self._find_clickable_by_text(driver, name, right_half_only=True)
            if control is not None:
                return control

        # Fallback for switcher controls that expose the target id in href/data.
        # Restrict this to the right half of the viewport where Facebook renders
        # the account switcher so normal profile links in the feed are ignored.
        if expected_actor:
            try:
                elements = driver.find_elements(
                    By.CSS_SELECTOR,
                    "[role='menuitem'], [role='button'], a[href], [tabindex='0']",
                )
            except WebDriverException:
                elements = []
            width = self._viewport_width(driver)
            for element in elements:
                try:
                    if not element.is_displayed() or element.rect.get("x", 0) < width * 0.45:
                        continue
                    haystack = " ".join(
                        filter(
                            None,
                            [
                                element.get_attribute("href") or "",
                                element.get_attribute("data-profileid") or "",
                                element.get_attribute("data-userid") or "",
                                element.get_attribute("aria-label") or "",
                            ],
                        )
                    )
                    if expected_actor in haystack:
                        return element
                except StaleElementReferenceException:
                    continue
        return None

    def _find_clickable_by_text(
        self,
        driver: Chrome,
        text: str,
        *,
        right_half_only: bool,
    ) -> WebElement | None:
        literal = self._xpath_literal(text)
        xpath = (
            "//*[normalize-space(.)="
            f"{literal} or contains(normalize-space(@aria-label), {literal})]"
            "/ancestor-or-self::*["
            "@role='menuitem' or @role='button' or self::button or self::a or @tabindex='0'][1]"
        )
        try:
            elements = driver.find_elements(By.XPATH, xpath)
        except WebDriverException:
            return None

        width = self._viewport_width(driver)
        visible: list[WebElement] = []
        for element in elements:
            try:
                if not element.is_displayed():
                    continue
                if right_half_only and element.rect.get("x", 0) < width * 0.45:
                    continue
                visible.append(element)
            except StaleElementReferenceException:
                continue

        if not visible:
            return None
        return max(visible, key=lambda item: float(item.rect.get("x") or 0))

    def _switcher_diagnostics(self, driver: Chrome) -> str:
        width = self._viewport_width(driver)
        labels: list[str] = []
        try:
            elements = driver.find_elements(
                By.CSS_SELECTOR,
                "[role='button'], [role='menuitem'], [tabindex='0']",
            )
        except WebDriverException:
            return ""

        for element in elements:
            try:
                if not element.is_displayed() or element.rect.get("x", 0) < width * 0.45:
                    continue
                value = " ".join(
                    filter(
                        None,
                        [
                            element.get_attribute("aria-label") or "",
                            element.text or "",
                        ],
                    )
                ).strip()
                if value and value not in labels:
                    labels.append(value[:100])
                if len(labels) >= 10:
                    break
            except StaleElementReferenceException:
                continue

        return " 可见账号菜单控件：" + " | ".join(labels) if labels else ""

    @staticmethod
    def _viewport_width(driver: Chrome) -> float:
        try:
            return float(driver.execute_script("return window.innerWidth") or 0)
        except Exception:
            return 0

    @staticmethod
    def _cookie_value(driver: Chrome, name: str) -> str | None:
        try:
            cookie: dict[str, Any] | None = driver.get_cookie(name)
        except WebDriverException:
            return None
        if not cookie:
            return None
        value = str(cookie.get("value") or "").strip()
        return value or None

    def _current_actor_id(self, driver: Chrome) -> str | None:
        return self._cookie_value(driver, "i_user") or self._cookie_value(driver, "c_user")
