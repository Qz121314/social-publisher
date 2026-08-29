from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any

from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from app.services.platforms.base import PlatformContent, PlatformPublishError
from app.services.platforms.facebook_adaptive import AdaptiveFacebookAdapter


_ACTIVE_PUBLISH_CONTENT: ContextVar[PlatformContent | None] = ContextVar(
    "facebook_active_publish_content",
    default=None,
)


class IdentityAwareFacebookAdapter(AdaptiveFacebookAdapter):
    """Facebook adapter with a strict target-ID publishing gate.

    The active Facebook publishing actor is determined from stable account IDs:
    `i_user` when acting as a Page, otherwise `c_user` for the personal profile.
    Display names, titles and URLs are navigation aids only; they never authorize
    a publish. The actor ID must match the configured target ID after switching,
    after target navigation, and immediately before the final Post click.
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
        "See all Pages",
        "See all profiles and Pages",
        "Switch profile",
        "Switch profiles",
        "All profiles",
        "查看所有主页",
        "查看全部主页",
        "查看所有个人主页",
        "查看所有个人资料",
        "查看全部个人主页",
        "查看所有个人主页和公共主页",
        "切换个人主页",
        "切换个人资料",
        "所有个人主页",
    )
    _SWITCH_TO_PERSONAL_PREFIXES = (
        "Switch to ",
        "Switch into ",
        "切换到",
        "切换至",
    )

    def publish(self, driver: Chrome, content: PlatformContent) -> dict[str, Any]:
        token = _ACTIVE_PUBLISH_CONTENT.set(content)
        try:
            return super().publish(driver, content)
        finally:
            _ACTIVE_PUBLISH_CONTENT.reset(token)

    def _navigate_to_target(self, driver: Chrome, content: PlatformContent) -> None:
        # Gate 1: regardless of what the iX window opened as, the Facebook actor
        # must first become the configured target ID.
        self._ensure_target_identity(driver, content)
        self._assert_target_actor(driver, content, stage="身份切换后")

        # URL navigation is secondary. It never substitutes for the actor-ID gate.
        super()._navigate_to_target(driver, content)

        # Gate 2: navigation itself must not have changed the active actor.
        self._assert_target_actor(driver, content, stage="进入目标主页后")

    def _wait_post_ready(self, driver: Chrome, composer: WebElement) -> WebElement:
        button = super()._wait_post_ready(driver, composer)
        content = _ACTIVE_PUBLISH_CONTENT.get()
        if content is None:
            raise PlatformPublishError("Facebook 发布上下文丢失，已停止发布。")

        # Gate 3: this is the final guard immediately before the base adapter
        # clicks Post. A mismatch here is always a safe pre-submission failure.
        self._assert_target_actor(driver, content, stage="点击发布前")
        return button

    def _assert_target_actor(
        self,
        driver: Chrome,
        content: PlatformContent,
        *,
        stage: str,
    ) -> None:
        expected_actor = (content.target_id or "").strip()
        current_actor = self._current_actor_id(driver)
        c_user = self._cookie_value(driver, "c_user")
        i_user = self._cookie_value(driver, "i_user")

        if not expected_actor:
            raise PlatformPublishError("Facebook 发布目标缺少 target_id，已停止发布。")
        if not current_actor:
            raise PlatformPublishError(
                f"{stage}无法读取 Facebook 当前发布身份 ID，已停止发布。"
            )
        if current_actor != expected_actor:
            raise PlatformPublishError(
                f"{stage} Facebook 身份 ID 校验失败，已停止发布以避免发错主页。"
                f" 当前身份={current_actor}，目标身份={expected_actor}，"
                f"c_user={c_user or '-'}，i_user={i_user or '-'}。"
            )

    def _ensure_target_identity(self, driver: Chrome, content: PlatformContent) -> None:
        expected_actor = (content.target_id or "").strip()
        if not expected_actor:
            raise PlatformPublishError("Facebook 发布目标缺少身份 ID，已停止发布。")

        c_user = self._cookie_value(driver, "c_user")
        current_actor = self._current_actor_id(driver)

        # A personal-profile target must always be the actual logged-in account.
        # Do not trust the display name here: Facebook titles/names can vary by
        # experiment and notification state, while c_user is the stable account id.
        if content.target_type == "profile":
            if not c_user:
                raise PlatformPublishError(
                    "无法读取 Facebook 登录账号 ID（c_user），不能安全切换到个人主页。"
                )
            if expected_actor != c_user:
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
                f" 当前身份={current_actor or '-'}，目标={expected_actor}。"
                + self._switcher_diagnostics(driver)
            )

        self._safe_click(driver, opener)
        time.sleep(0.8)

        if content.target_type == "profile":
            # On the first-level menu Facebook commonly renders exactly one
            # direct action such as "切换到 Tanin Nan". That action is the correct
            # way to leave a Page actor and return to c_user. Do not try to match
            # the personal target by its stored display name.
            target_control = self._find_personal_switch_control(driver)
            if target_control is None:
                expand = self._find_switcher_expand_control(driver)
                if expand is not None:
                    self._safe_click(driver, expand)
                    time.sleep(0.8)
                    target_control = self._find_identity_control(driver, content)
        else:
            # Managed Pages may be visible on the first menu, but usually live
            # behind "查看所有主页 / See all profiles". Try direct match first,
            # then expand to the complete identity list.
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
                f" 目标ID={expected_actor}。"
                + self._switcher_diagnostics(driver)
            )

        self._safe_click(driver, target_control)
        self._wait_for_actor(driver, expected_actor)

    def _wait_for_actor(self, driver: Chrome, expected_actor: str) -> None:
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
            "已点击 Facebook 身份切换项，但身份 ID 校验没有通过，已停止发布以避免发错主页。"
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

        def x_position(element: WebElement) -> float:
            try:
                return float(element.rect.get("x") or 0)
            except Exception:
                return 0

        return max(candidates, key=x_position)

    def _find_personal_switch_control(self, driver: Chrome) -> WebElement | None:
        """Find the direct first-level action that returns Page actor -> c_user."""
        width = self._viewport_width(driver)
        prefixes = tuple(value.casefold() for value in self._SWITCH_TO_PERSONAL_PREFIXES)
        try:
            elements = driver.find_elements(
                By.CSS_SELECTOR,
                "[role='menuitem'], [role='button'], a, [tabindex='0']",
            )
        except WebDriverException:
            return None

        matches: list[WebElement] = []
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
                folded = value.casefold()
                if not value:
                    continue
                if any(folded.startswith(prefix) for prefix in prefixes):
                    if folded in {"switch profile", "switch profiles", "切换个人主页", "切换个人资料"}:
                        continue
                    matches.append(element)
            except StaleElementReferenceException:
                continue

        if not matches:
            return None
        return max(matches, key=lambda item: float(item.rect.get("x") or 0))

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

        # Page names are navigation hints only. The selected result is never
        # trusted until i_user/current actor equals expected_actor after the click.
        if content.target_type != "profile" and name:
            control = self._find_clickable_by_text(driver, name, right_half_only=True)
            if control is not None:
                return control

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
                if len(labels) >= 12:
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
