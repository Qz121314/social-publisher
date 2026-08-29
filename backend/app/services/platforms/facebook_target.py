from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any

from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from app.services.platforms.base import PlatformContent, PlatformPublishError
from app.services.platforms.facebook_adaptive import AdaptiveFacebookAdapter


_ACTIVE_PUBLISH_CONTENT: ContextVar[PlatformContent | None] = ContextVar(
    "facebook_active_publish_content",
    default=None,
)


class TargetActorFacebookAdapter(AdaptiveFacebookAdapter):
    """Facebook adapter centered on one concept: the configured target actor ID.

    Personal profiles and Pages use the same publishing pipeline. ``target_type``
    remains metadata for display only. Authorization to publish is based solely on
    the active Facebook actor ID: ``i_user`` when acting as a Page, otherwise
    ``c_user``. Names and URLs are navigation hints and never authorize a post.
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
    _EXPAND_SWITCHER_TEXT = (
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
    _DIRECT_SWITCH_PREFIXES = (
        "Switch to ",
        "Switch into ",
        "切换到",
        "切换至",
    )
    _COMPOSER_ENTRY_TEXT = (
        "What's on your mind",
        "What’s on your mind",
        "Create post",
        "Create a post",
        "Write something",
        "Share an update",
        "在想些什么",
        "有什么新鲜事",
        "创建帖子",
        "发帖",
        "写点什么",
        "说点什么",
        "发布动态",
    )

    def publish(self, driver: Chrome, content: PlatformContent) -> dict[str, Any]:
        token = _ACTIVE_PUBLISH_CONTENT.set(content)
        try:
            return super().publish(driver, content)
        finally:
            _ACTIVE_PUBLISH_CONTENT.reset(token)

    # ------------------------------------------------------------------
    # Unified target preparation / actor-ID gates
    # ------------------------------------------------------------------
    def prepare_target(self, driver: Chrome, content: PlatformContent) -> None:
        self._ensure_target_actor(driver, content)
        self._assert_target_actor(driver, content, stage="身份切换后")

        # URL is only a navigation destination. It is not an authorization signal.
        super()._navigate_to_target(driver, content)
        self._assert_target_actor(driver, content, stage="进入目标页面后")

    def _navigate_to_target(self, driver: Chrome, content: PlatformContent) -> None:
        self.prepare_target(driver, content)

    def _wait_post_ready(self, driver: Chrome, composer: WebElement) -> WebElement:
        button = super()._wait_post_ready(driver, composer)
        content = _ACTIVE_PUBLISH_CONTENT.get()
        if content is None:
            raise PlatformPublishError("Facebook 发布上下文丢失，已停止发布。")
        self._assert_target_actor(driver, content, stage="点击发布前")
        return button

    def _assert_target_actor(
        self,
        driver: Chrome,
        content: PlatformContent,
        *,
        stage: str,
    ) -> None:
        expected = (content.target_id or "").strip()
        current = self.current_actor_id(driver)
        c_user = self._cookie_value(driver, "c_user")
        i_user = self._cookie_value(driver, "i_user")

        if not expected:
            raise PlatformPublishError("Facebook 发布目标缺少 target_id，已停止发布。")
        if not current:
            raise PlatformPublishError(f"{stage}无法读取 Facebook 当前发布身份 ID，已停止发布。")
        if current != expected:
            raise PlatformPublishError(
                f"{stage} Facebook 身份 ID 校验失败，已停止发布以避免发错目标。"
                f" 当前身份={current}，目标身份={expected}，"
                f"c_user={c_user or '-'}，i_user={i_user or '-'}。"
            )

    def _ensure_target_actor(self, driver: Chrome, content: PlatformContent) -> None:
        expected = (content.target_id or "").strip()
        if not expected:
            raise PlatformPublishError("Facebook 发布目标缺少身份 ID，已停止发布。")

        if self.current_actor_id(driver) == expected:
            return

        self._open_facebook_home(driver)
        if self.current_actor_id(driver) == expected:
            return

        opener = self._find_account_menu_opener(driver)
        if opener is None:
            raise PlatformPublishError(
                "需要切换 Facebook 发布身份，但没有找到右上角账号菜单。"
                f" 当前身份={self.current_actor_id(driver) or '-'}，目标={expected}。"
                + self._switcher_diagnostics(driver)
            )
        self._safe_click(driver, opener)
        time.sleep(0.8)

        # One unified selection pipeline. Stable ID is always preferred.
        target_control = self._find_identity_control_by_id(driver, expected)

        # Facebook's direct "切换到 <name>" action commonly omits the ID. It is
        # acceptable only when expected == c_user, and is still verified by ID
        # after the click. No target_type branch is needed.
        if target_control is None and expected == self._cookie_value(driver, "c_user"):
            target_control = self._find_direct_switch_control(driver)

        # Name is a navigation hint only. A click is never trusted until actor ID
        # equals the configured target ID afterward.
        if target_control is None and content.target_name:
            target_control = self._find_clickable_by_text(
                driver,
                content.target_name,
                right_half_only=True,
            )

        if target_control is None:
            expand = self._find_switcher_expand_control(driver)
            if expand is not None:
                self._safe_click(driver, expand)
                time.sleep(0.8)
                target_control = self._find_identity_control_by_id(driver, expected)
                if target_control is None and content.target_name:
                    target_control = self._find_clickable_by_text(
                        driver,
                        content.target_name,
                        right_half_only=False,
                    )

        if target_control is None:
            raise PlatformPublishError(
                "Facebook 身份选择器已打开，但没有找到设定的目标身份。"
                f" 目标ID={expected}。"
                + self._switcher_diagnostics(driver)
            )

        self._safe_click(driver, target_control)
        self._wait_for_actor(driver, expected)

    def _wait_for_actor(self, driver: Chrome, expected: str) -> None:
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
            last_actor = self.current_actor_id(driver)
            if last_actor == expected:
                return
            time.sleep(0.5)

        raise PlatformPublishError(
            "已点击 Facebook 身份切换项，但身份 ID 校验没有通过，已停止发布。"
            f" 当前身份={last_actor or '-'}，目标身份={expected}。"
        )

    # ------------------------------------------------------------------
    # Behavior-confirmed composer entry
    # ------------------------------------------------------------------
    def _open_composer(self, driver: Chrome) -> WebElement:
        composer, _fingerprint = self._locate_confirmed_composer(driver)
        content = _ACTIVE_PUBLISH_CONTENT.get()
        if content is not None:
            self._assert_target_actor(driver, content, stage="打开发帖编辑器后")
        return composer

    def confirm_composer_entry(
        self,
        driver: Chrome,
        content: PlatformContent,
    ) -> dict[str, Any]:
        """Confirm a real composer entry without typing or submitting anything."""
        token = _ACTIVE_PUBLISH_CONTENT.set(content)
        try:
            self.prepare_target(driver, content)
            composer, fingerprint = self._locate_confirmed_composer(driver)
            self._assert_target_actor(driver, content, stage="确认发帖入口后")
            result = {
                "confirmed": True,
                "target_id": content.target_id,
                "target_name": content.target_name,
                "current_actor_id": self.current_actor_id(driver),
                "current_url": driver.current_url,
                "title": driver.title,
                "entry": fingerprint,
                "editor_confirmed": self._has_editable(composer),
                "post_button_confirmed": self._find_post_button(composer) is not None,
            }
            self._close_composer_without_submitting(driver, composer)
            return result
        finally:
            _ACTIVE_PUBLISH_CONTENT.reset(token)

    def _locate_confirmed_composer(self, driver: Chrome) -> tuple[WebElement, dict[str, Any]]:
        last_controls: list[str] = []
        for y in self._composer_scroll_positions(driver):
            try:
                driver.execute_script("window.scrollTo(0, arguments[0]);", y)
            except WebDriverException:
                pass
            time.sleep(0.6)

            candidates = self._composer_entry_candidates(driver)
            for candidate in candidates:
                try:
                    fingerprint = self._fingerprint(candidate)
                    last_controls.append(self._fingerprint_text(fingerprint))
                    dialogs_before = self._visible_dialogs(driver)
                    self._safe_click(driver, candidate)
                    composer = self._wait_confirmed_composer(driver, dialogs_before, timeout=5)
                    if composer is not None:
                        return composer, fingerprint
                    self._dismiss_transient_ui(driver)
                except (StaleElementReferenceException, WebDriverException):
                    continue

        sample = " | ".join(value for value in last_controls[-8:] if value)
        suffix = f" 已检查控件：{sample}" if sample else ""
        raise PlatformPublishError(
            "没有确认到 Facebook 发帖入口：未能通过“点击入口后同时出现编辑器和发布按钮”的行为验证。"
            f" 页面={driver.current_url or '-'}。{suffix}"
        )

    def _wait_confirmed_composer(
        self,
        driver: Chrome,
        dialogs_before: list[WebElement],
        *,
        timeout: int,
    ) -> WebElement | None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            dialogs = self._visible_dialogs(driver)
            ordered = [d for d in dialogs if d not in dialogs_before] + list(reversed(dialogs))
            for dialog in ordered:
                if self._has_editable(dialog) and self._find_post_button(dialog) is not None:
                    return dialog

            # Some variants use an inline composer rather than role=dialog.
            for editable in self._visible_editables(driver):
                container = self._nearest_composer_container(driver, editable)
                if container is None:
                    continue
                if self._find_post_button(container) is not None:
                    return container
            time.sleep(0.25)
        return None

    def _composer_entry_candidates(self, driver: Chrome) -> list[WebElement]:
        candidates: list[WebElement] = []
        seen: set[str] = set()

        def add(element: WebElement) -> None:
            try:
                if not element.is_displayed():
                    return
                key = element.id
                if key in seen:
                    return
                if element.find_elements(By.XPATH, "ancestor::*[@role='dialog']"):
                    return
                seen.add(key)
                candidates.append(element)
            except (StaleElementReferenceException, WebDriverException):
                return

        # Semantic text / accessibility labels.
        for text in self._COMPOSER_ENTRY_TEXT:
            literal = self._xpath_literal(text)
            xpath = (
                "//*[contains(normalize-space(@aria-label), "
                f"{literal}) or contains(normalize-space(@aria-placeholder), {literal}) or "
                f"contains(normalize-space(@data-placeholder), {literal}) or "
                f"contains(normalize-space(.), {literal})]"
            )
            try:
                matches = driver.find_elements(By.XPATH, xpath)
            except WebDriverException:
                matches = []
            for element in matches:
                clickable = self._clickable_ancestor(driver, element)
                add(clickable or element)

        # Structural composer triggers/editables. These are still behavior-verified
        # before being accepted as the real entry.
        selectors = (
            "[role='textbox'][contenteditable='true']",
            "[contenteditable='true'][aria-label]",
            "[contenteditable='true'][aria-placeholder]",
            "[role='button'][aria-label]",
        )
        for selector in selectors:
            try:
                matches = driver.find_elements(By.CSS_SELECTOR, selector)
            except WebDriverException:
                matches = []
            for element in matches:
                try:
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
                except StaleElementReferenceException:
                    continue
                if any(text.casefold() in label for text in self._COMPOSER_ENTRY_TEXT):
                    add(self._clickable_ancestor(driver, element) or element)

        return candidates

    def _clickable_ancestor(self, driver: Chrome, element: WebElement) -> WebElement | None:
        try:
            value = driver.execute_script(
                """
                let cur = arguments[0];
                for (let i = 0; cur && i < 7; i++, cur = cur.parentElement) {
                  const role = cur.getAttribute ? (cur.getAttribute('role') || '') : '';
                  const tabindex = cur.getAttribute ? (cur.getAttribute('tabindex') || '') : '';
                  const href = cur.getAttribute ? (cur.getAttribute('href') || '') : '';
                  const cursor = getComputedStyle(cur).cursor;
                  if (role === 'button' || role === 'textbox' || tabindex === '0' || href || cursor === 'pointer') return cur;
                }
                return null;
                """,
                element,
            )
            return value if isinstance(value, WebElement) else None
        except Exception:
            return None

    def _composer_scroll_positions(self, driver: Chrome) -> list[int]:
        try:
            height = int(
                driver.execute_script(
                    "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
                )
                or 0
            )
            viewport = int(driver.execute_script("return window.innerHeight") or 800)
        except WebDriverException:
            return [0, 350, 700, 1050]
        max_scroll = max(0, height - viewport)
        raw = [0, 250, 500, 800, 1100, int(height * 0.25), int(height * 0.5)]
        return sorted({min(max(0, value), max_scroll) for value in raw})

    def _fingerprint(self, element: WebElement) -> dict[str, Any]:
        try:
            return {
                "tag": (element.tag_name or "").lower(),
                "role": element.get_attribute("role") or "",
                "aria_label": element.get_attribute("aria-label") or "",
                "aria_placeholder": element.get_attribute("aria-placeholder") or "",
                "data_placeholder": element.get_attribute("data-placeholder") or "",
                "contenteditable": element.get_attribute("contenteditable") or "",
                "tabindex": element.get_attribute("tabindex") or "",
                "text": " ".join((element.text or "").split())[:220],
            }
        except StaleElementReferenceException:
            return {}

    @staticmethod
    def _fingerprint_text(value: dict[str, Any]) -> str:
        parts = [
            str(value.get("aria_label") or ""),
            str(value.get("aria_placeholder") or ""),
            str(value.get("text") or ""),
        ]
        return next((part[:100] for part in parts if part), "")

    def _close_composer_without_submitting(self, driver: Chrome, composer: WebElement) -> None:
        try:
            composer.send_keys(Keys.ESCAPE)
            time.sleep(0.4)
            if not composer.is_displayed():
                return
        except Exception:
            pass
        self._dismiss_transient_ui(driver)

    @staticmethod
    def _dismiss_transient_ui(driver: Chrome) -> None:
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.25)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Account switcher helpers
    # ------------------------------------------------------------------
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
                value = " ".join(
                    filter(
                        None,
                        [
                            element.get_attribute("aria-label") or "",
                            element.get_attribute("title") or "",
                            element.text or "",
                        ],
                    )
                ).casefold()
                if any(token in value for token in labels):
                    candidates.append(element)
            except StaleElementReferenceException:
                continue
        if not candidates:
            return None
        return max(candidates, key=lambda item: float(item.rect.get("x") or 0))

    def _find_identity_control_by_id(self, driver: Chrome, expected: str) -> WebElement | None:
        try:
            elements = driver.find_elements(
                By.CSS_SELECTOR,
                "[role='menuitem'], [role='button'], a[href], [tabindex='0']",
            )
        except WebDriverException:
            return None
        for element in elements:
            try:
                if not element.is_displayed():
                    continue
                haystack = " ".join(
                    filter(
                        None,
                        [
                            element.get_attribute("href") or "",
                            element.get_attribute("data-profileid") or "",
                            element.get_attribute("data-userid") or "",
                            element.get_attribute("data-pageid") or "",
                            element.get_attribute("aria-label") or "",
                        ],
                    )
                )
                if expected in haystack:
                    return element
            except StaleElementReferenceException:
                continue
        return None

    def _find_direct_switch_control(self, driver: Chrome) -> WebElement | None:
        prefixes = tuple(value.casefold() for value in self._DIRECT_SWITCH_PREFIXES)
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
                if not element.is_displayed():
                    continue
                value = " ".join(
                    filter(
                        None,
                        [element.get_attribute("aria-label") or "", element.text or ""],
                    )
                ).strip()
                folded = value.casefold()
                if value and any(folded.startswith(prefix) for prefix in prefixes):
                    matches.append(element)
            except StaleElementReferenceException:
                continue
        return matches[0] if matches else None

    def _find_switcher_expand_control(self, driver: Chrome) -> WebElement | None:
        for text in self._EXPAND_SWITCHER_TEXT:
            control = self._find_clickable_by_text(driver, text, right_half_only=False)
            if control is not None:
                return control
        return None

    def _find_clickable_by_text(
        self,
        driver: Chrome,
        text: str,
        *,
        right_half_only: bool,
    ) -> WebElement | None:
        literal = self._xpath_literal(" ".join(text.split()).strip())
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
        for element in elements:
            try:
                if not element.is_displayed():
                    continue
                if right_half_only and element.rect.get("x", 0) < width * 0.4:
                    continue
                return element
            except StaleElementReferenceException:
                continue
        return None

    def _switcher_diagnostics(self, driver: Chrome) -> str:
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
                if not element.is_displayed():
                    continue
                value = " ".join(
                    filter(
                        None,
                        [element.get_attribute("aria-label") or "", element.text or ""],
                    )
                ).strip()
                if value and value not in labels:
                    labels.append(value[:100])
                if len(labels) >= 12:
                    break
            except StaleElementReferenceException:
                continue
        return " 可见身份切换控件：" + " | ".join(labels) if labels else ""

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

    def current_actor_id(self, driver: Chrome) -> str | None:
        return self._cookie_value(driver, "i_user") or self._cookie_value(driver, "c_user")
