from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement

from app.services.login_engine import LoginResult


FACEBOOK_HOME = "https://www.facebook.com/"
FACEBOOK_LOGIN = "https://www.facebook.com/login/"


@dataclass(frozen=True)
class FacebookPageObservation:
    result: LoginResult | None
    identity_id: str | None
    current_url: str
    login_form_visible: bool
    reason: str

    @property
    def logged_in(self) -> bool:
        return self.result == LoginResult.SUCCESS and bool(self.identity_id)


def classify_facebook_login_page(
    *,
    current_url: str,
    page_text: str,
    identity_id: str | None,
    login_form_visible: bool,
    otp_input_visible: bool,
) -> tuple[LoginResult | None, str]:
    """Classify only observable login states; never bypass platform challenges."""

    url = (current_url or "").casefold()
    text = (page_text or "").casefold()

    authenticator_markers = (
        "authentication app",
        "authenticator app",
        "code generator",
        "authentication code",
        "身份验证器",
        "验证码生成器",
        "身份验证应用",
    )
    checkpoint_markers = (
        "security check",
        "confirm your identity",
        "verify your identity",
        "安全检查",
        "确认你的身份",
        "确认身份",
        "验证你的身份",
    )
    other_mfa_markers = (
        "text message",
        "sms",
        "send code",
        "email code",
        "approve from another device",
        "check your notifications",
        "短信",
        "发送验证码",
        "邮件验证码",
        "在另一台设备",
        "检查通知",
    )
    invalid_credential_markers = (
        "password that you've entered is incorrect",
        "incorrect password",
        "wrong password",
        "invalid username or password",
        "密码不正确",
        "密码错误",
        "账号或密码",
    )

    # A clearly labelled Authenticator challenge may be hosted under a generic
    # checkpoint URL, so classify it before the generic checkpoint branch.
    if otp_input_visible and any(marker in text for marker in authenticator_markers):
        return LoginResult.TOTP_REQUIRED, "检测到 Authenticator TOTP 验证。"

    if "checkpoint" in url or "challenge" in url or any(marker in text for marker in checkpoint_markers):
        return LoginResult.CHECKPOINT, "检测到 Facebook 安全检查，需要人工处理。"

    if otp_input_visible or any(marker in text for marker in other_mfa_markers):
        return LoginResult.OTHER_MFA_REQUIRED, "检测到需要人工完成的二次验证。"

    if any(marker in text for marker in invalid_credential_markers):
        return LoginResult.INVALID_CREDENTIALS, "Facebook 提示账号或密码不正确。"

    if identity_id and not login_form_visible and "/login" not in url:
        return LoginResult.SUCCESS, "已检测到有效 Facebook 登录状态。"

    if login_form_visible or "/login" in url:
        return None, "当前 Facebook 会话未登录。"

    return LoginResult.UNKNOWN, "无法确认当前 Facebook 登录状态。"


class FacebookLoginAdapter:
    """Browser-side Facebook login primitives for the fixed iX Profile.

    This adapter performs ordinary session inspection, Cookie restore, password
    entry and standard TOTP submission. CAPTCHA, Checkpoint, security keys,
    device approval and unknown security challenges are detected and returned to
    the caller for manual handling; they are never bypassed.
    """

    def open_home(self, driver: Chrome) -> FacebookPageObservation:
        driver.get(FACEBOOK_HOME)
        self._wait_document(driver)
        return self.observe(driver)

    def observe(self, driver: Chrome) -> FacebookPageObservation:
        identity_id = self.current_login_identity(driver)
        current_url = str(driver.current_url or "")
        login_form_visible = self._login_form_visible(driver)
        otp_input_visible = self._otp_input(driver) is not None
        page_text = self._body_text(driver)
        result, reason = classify_facebook_login_page(
            current_url=current_url,
            page_text=page_text,
            identity_id=identity_id,
            login_form_visible=login_form_visible,
            otp_input_visible=otp_input_visible,
        )
        return FacebookPageObservation(
            result=result,
            identity_id=identity_id,
            current_url=current_url,
            login_form_visible=login_form_visible,
            reason=reason,
        )

    def current_login_identity(self, driver: Chrome) -> str | None:
        try:
            cookie = driver.get_cookie("c_user")
        except WebDriverException:
            return None
        if not cookie:
            return None
        value = str(cookie.get("value") or "").strip()
        return value or None

    def restore_cookies(self, driver: Chrome, cookie_json: str) -> FacebookPageObservation:
        cookies = json.loads(cookie_json)
        if not isinstance(cookies, list) or not cookies:
            raise ValueError("已保存的 Facebook Cookie 数据为空。")

        driver.get(FACEBOOK_HOME)
        self._wait_document(driver)
        try:
            driver.execute_cdp_cmd("Network.enable", {})
        except WebDriverException as exc:
            raise RuntimeError("当前浏览器无法通过 CDP 恢复 Cookie。") from exc

        restored = 0
        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            name = str(cookie.get("name") or "").strip()
            value = str(cookie.get("value") or "")
            domain = str(cookie.get("domain") or "").strip()
            if not name or not domain:
                continue

            delete_params: dict[str, Any] = {"name": name, "domain": domain}
            path = str(cookie.get("path") or "/")
            if path:
                delete_params["path"] = path
            try:
                driver.execute_cdp_cmd("Network.deleteCookies", delete_params)
            except WebDriverException:
                pass

            params: dict[str, Any] = {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
            }
            if isinstance(cookie.get("secure"), bool):
                params["secure"] = cookie["secure"]
            if isinstance(cookie.get("httpOnly"), bool):
                params["httpOnly"] = cookie["httpOnly"]
            if isinstance(cookie.get("sameSite"), str):
                params["sameSite"] = cookie["sameSite"]
            if isinstance(cookie.get("expiry"), (int, float)):
                params["expires"] = float(cookie["expiry"])

            try:
                result = driver.execute_cdp_cmd("Network.setCookie", params)
            except WebDriverException:
                continue
            if result.get("success", True):
                restored += 1

        if restored == 0:
            raise RuntimeError("Cookie 恢复失败：浏览器没有接受任何 Facebook Cookie。")

        driver.get(FACEBOOK_HOME)
        self._wait_document(driver)
        return self._wait_for_observable_result(driver, timeout=12)

    def submit_password(
        self,
        driver: Chrome,
        *,
        login_identifier: str,
        password: str,
    ) -> FacebookPageObservation:
        if not login_identifier.strip():
            raise ValueError("尚未配置 Facebook 登录账号。")
        if not password:
            raise ValueError("尚未配置 Facebook 登录密码。")

        if not self._login_form_visible(driver):
            driver.get(FACEBOOK_LOGIN)
            self._wait_document(driver)

        identifier_input = self._first_visible(
            driver,
            (
                (By.CSS_SELECTOR, "input[name='email']"),
                (By.ID, "email"),
                (By.CSS_SELECTOR, "input[autocomplete='username']"),
                (By.CSS_SELECTOR, "input[type='email']"),
            ),
        )
        password_input = self._first_visible(
            driver,
            (
                (By.CSS_SELECTOR, "input[name='pass']"),
                (By.ID, "pass"),
                (By.CSS_SELECTOR, "input[type='password']"),
            ),
        )
        if identifier_input is None or password_input is None:
            return FacebookPageObservation(
                result=LoginResult.UNKNOWN,
                identity_id=self.current_login_identity(driver),
                current_url=str(driver.current_url or ""),
                login_form_visible=self._login_form_visible(driver),
                reason="没有找到可确认的 Facebook 账号密码登录表单。",
            )

        self._replace_text(driver, identifier_input, login_identifier)
        self._replace_text(driver, password_input, password)

        submit = self._first_visible(
            driver,
            (
                (By.CSS_SELECTOR, "button[name='login']"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[name='login']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
            ),
        )
        if submit is None:
            return FacebookPageObservation(
                result=LoginResult.UNKNOWN,
                identity_id=None,
                current_url=str(driver.current_url or ""),
                login_form_visible=True,
                reason="没有找到 Facebook 登录提交按钮。",
            )

        submit.click()
        return self._wait_for_observable_result(driver, timeout=22)

    def submit_totp(self, driver: Chrome, code: str) -> FacebookPageObservation:
        otp = self._otp_input(driver)
        if otp is None:
            return FacebookPageObservation(
                result=LoginResult.UNKNOWN,
                identity_id=self.current_login_identity(driver),
                current_url=str(driver.current_url or ""),
                login_form_visible=self._login_form_visible(driver),
                reason="页面没有找到可确认的 TOTP 输入框。",
            )

        # Only this method is called after the page has already been positively
        # classified as an Authenticator challenge.
        self._replace_text(driver, otp, code)
        submit = self._find_continue_button(driver)
        if submit is None:
            return FacebookPageObservation(
                result=LoginResult.UNKNOWN,
                identity_id=None,
                current_url=str(driver.current_url or ""),
                login_form_visible=False,
                reason="没有找到 TOTP 验证提交按钮。",
            )
        submit.click()
        return self._wait_for_observable_result(driver, timeout=22)

    def _wait_for_observable_result(self, driver: Chrome, *, timeout: float) -> FacebookPageObservation:
        deadline = time.monotonic() + timeout
        last: FacebookPageObservation | None = None
        while time.monotonic() < deadline:
            self._wait_document(driver, timeout=2)
            last = self.observe(driver)
            if last.result in {
                LoginResult.SUCCESS,
                LoginResult.TOTP_REQUIRED,
                LoginResult.OTHER_MFA_REQUIRED,
                LoginResult.CHECKPOINT,
                LoginResult.INVALID_CREDENTIALS,
            }:
                return last
            time.sleep(0.4)
        return last or self.observe(driver)

    def _login_form_visible(self, driver: Chrome) -> bool:
        password = self._first_visible(
            driver,
            (
                (By.CSS_SELECTOR, "input[name='pass']"),
                (By.ID, "pass"),
                (By.CSS_SELECTOR, "input[type='password']"),
            ),
        )
        return password is not None

    def _otp_input(self, driver: Chrome) -> WebElement | None:
        return self._first_visible(
            driver,
            (
                (By.CSS_SELECTOR, "input[name='approvals_code']"),
                (By.CSS_SELECTOR, "input[autocomplete='one-time-code']"),
                (By.CSS_SELECTOR, "input[inputmode='numeric']"),
            ),
        )

    def _find_continue_button(self, driver: Chrome) -> WebElement | None:
        direct = self._first_visible(
            driver,
            (
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
            ),
        )
        if direct is not None:
            return direct

        labels = ("Continue", "Submit", "Next", "Confirm", "继续", "提交", "下一步", "确认")
        try:
            buttons = driver.find_elements(By.XPATH, "//button|//*[@role='button']")
        except WebDriverException:
            return None
        for button in buttons:
            try:
                if button.is_displayed() and any(label.casefold() in (button.text or "").casefold() for label in labels):
                    return button
            except WebDriverException:
                continue
        return None

    @staticmethod
    def _replace_text(driver: Chrome, element: WebElement, value: str) -> None:
        element.click()
        try:
            element.send_keys(Keys.CONTROL, "a")
            element.send_keys(Keys.BACKSPACE)
            driver.execute_cdp_cmd("Input.insertText", {"text": value})
        except WebDriverException:
            element.clear()
            element.send_keys(value)

    @staticmethod
    def _first_visible(
        driver: Chrome,
        selectors: tuple[tuple[str, str], ...],
    ) -> WebElement | None:
        for by, value in selectors:
            try:
                elements = driver.find_elements(by, value)
            except (NoSuchElementException, WebDriverException):
                continue
            for element in elements:
                try:
                    if element.is_displayed() and element.is_enabled():
                        return element
                except WebDriverException:
                    continue
        return None

    @staticmethod
    def _body_text(driver: Chrome) -> str:
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            return (body.text or "")[:30000]
        except (NoSuchElementException, WebDriverException):
            return ""

    @staticmethod
    def _wait_document(driver: Chrome, timeout: float = 8) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                state = driver.execute_script("return document.readyState")
                if state in {"interactive", "complete"}:
                    return
            except WebDriverException:
                pass
            time.sleep(0.2)
