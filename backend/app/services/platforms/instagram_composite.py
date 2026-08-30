from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from selenium.common.exceptions import (
    ElementNotInteractableException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from app.services.platforms.base import (
    PlatformAdapter,
    PlatformCapabilities,
    PlatformContent,
    PlatformMedia,
    PlatformNeedsReviewError,
    PlatformPublishError,
    PlatformValidationError,
    emit_platform_progress,
)


_CREATE_NAMES = (
    "Create",
    "New post",
    "Create post",
    "创建",
    "新帖子",
    "创建帖子",
    "建立",
    "建立貼文",
)
_POST_NAMES = ("Post", "帖子", "貼文", "发布帖子")
_NEXT_NAMES = ("Next", "Continue", "下一步", "继续", "繼續")
_SHARE_NAMES = ("Share", "分享", "共享")
_PROFILE_LABELS = (
    "profile",
    "your profile",
    "个人主页",
    "個人檔案",
    "个人资料",
    "主页",
    "profil",
)
_SUCCESS_MARKERS = (
    "your post has been shared",
    "post shared",
    "post has been shared",
    "你的帖子已分享",
    "帖子已分享",
    "貼文已分享",
    "已分享帖子",
)
_RESERVED_PROFILE_PATHS = {
    "",
    "accounts",
    "about",
    "api",
    "challenge",
    "create",
    "direct",
    "emails",
    "explore",
    "legal",
    "p",
    "privacy",
    "reel",
    "reels",
    "stories",
    "terms",
    "web",
}


class InstagramIdentityComponent:
    """Login state and stable ds_user_id authorization gate."""

    @staticmethod
    def _cookie(driver: Chrome, name: str) -> str | None:
        try:
            value = driver.get_cookie(name)
        except WebDriverException:
            return None
        if not value:
            return None
        raw = str(value.get("value") or "").strip()
        return raw or None

    def current_actor_id(self, driver: Chrome) -> str | None:
        return self._cookie(driver, "ds_user_id")

    def check_login(self, driver: Chrome) -> dict[str, Any]:
        current_url = (driver.current_url or "").lower()
        checkpoint = any(
            marker in current_url
            for marker in ("/challenge/", "/checkpoint/", "/two_factor/", "/accounts/confirm_email/")
        )
        logged_out = "/accounts/login" in current_url
        actor_id = self.current_actor_id(driver)
        session_id = self._cookie(driver, "sessionid")
        return {
            "logged_in": bool(actor_id and session_id and not logged_out and not checkpoint),
            "checkpoint": checkpoint,
            "actor_id": actor_id,
            "current_url": driver.current_url,
        }

    def verify_actor(self, driver: Chrome, content: PlatformContent, *, stage: str) -> None:
        expected = (content.target_id or "").strip()
        current = self.current_actor_id(driver)
        if not expected:
            raise PlatformPublishError("Instagram Channel 缺少稳定用户 ID，已停止发布。")
        if not current:
            raise PlatformPublishError(f"{stage}无法读取 Instagram 当前 ds_user_id，已停止发布。")
        if current != expected:
            raise PlatformPublishError(
                f"{stage} Instagram 身份校验失败，已停止发布以避免发到错误账号。"
                f" 当前 ds_user_id={current}，目标={expected}。"
            )

    def discover_identity(self, driver: Chrome) -> dict[str, str]:
        login = self.check_login(driver)
        if login["checkpoint"]:
            raise PlatformNeedsReviewError("Instagram 出现安全验证，请先在 iXBrowser 中人工处理。")
        if not login["logged_in"]:
            raise PlatformNeedsReviewError("当前 iX 环境尚未登录 Instagram，请先人工登录。")

        profile_url = self._find_own_profile_url(driver)
        if not profile_url:
            raise PlatformPublishError(
                "已检测到 Instagram 登录，但没有可靠识别当前账号的个人主页入口。"
                " 请打开 Instagram 首页，确认左侧/底部 Profile 入口可见后重试。"
            )
        username = self._username_from_profile_url(profile_url)
        if not username:
            raise PlatformPublishError("Instagram 当前账号主页 URL 无法解析用户名。")
        return {
            "target_id": str(login["actor_id"]),
            "target_name": username,
            "target_type": "profile",
            "target_url": f"https://www.instagram.com/{username}/",
        }

    def _find_own_profile_url(self, driver: Chrome) -> str | None:
        try:
            anchors = driver.find_elements(By.CSS_SELECTOR, "a[href]")
        except WebDriverException:
            return None
        for anchor in anchors:
            try:
                if not anchor.is_displayed():
                    continue
                labels = [
                    anchor.get_attribute("aria-label") or "",
                    anchor.get_attribute("title") or "",
                ]
                for child in anchor.find_elements(By.CSS_SELECTOR, "svg[aria-label], img[alt]"):
                    labels.append(child.get_attribute("aria-label") or child.get_attribute("alt") or "")
                folded = " ".join(labels).casefold()
                if not any(label in folded for label in _PROFILE_LABELS):
                    continue
                href = str(anchor.get_attribute("href") or "").strip()
                if self._username_from_profile_url(href):
                    return href
            except (StaleElementReferenceException, WebDriverException):
                continue
        return None

    @staticmethod
    def _username_from_profile_url(raw_url: str) -> str | None:
        if not raw_url:
            return None
        parsed = urlparse(raw_url)
        host = parsed.netloc.lower().split(":", 1)[0]
        if host not in {"instagram.com", "www.instagram.com"}:
            return None
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 1:
            return None
        username = parts[0].strip()
        if not username or username.casefold() in _RESERVED_PROFILE_PATHS:
            return None
        return username


class InstagramNavigationComponent:
    """Navigate to the native Instagram web composer starting point."""

    def open_home(self, driver: Chrome) -> None:
        driver.get("https://www.instagram.com/")
        try:
            WebDriverWait(driver, 20).until(
                lambda browser: browser.execute_script("return document.readyState")
                in ("interactive", "complete")
            )
        except TimeoutException:
            pass


class InstagramComposerComponent:
    """Open the native Create/Post surface and upload feed media."""

    def open(self, driver: Chrome) -> WebElement | Chrome:
        self._dismiss_optional_prompts(driver)
        create = self._find_clickable(driver, _CREATE_NAMES)
        if create is None:
            raise PlatformPublishError(
                "Instagram 已登录，但没有找到 Create / New post 入口。页面结构可能已变化。"
            )
        self._safe_click(driver, create)
        time.sleep(0.5)

        if self._find_file_input(driver) is None:
            post = self._find_clickable(driver, _POST_NAMES)
            if post is not None:
                self._safe_click(driver, post)

        try:
            WebDriverWait(driver, 12).until(lambda _: self._find_file_input(driver) is not None)
        except TimeoutException as exc:
            raise PlatformPublishError(
                "Instagram Create 已打开，但没有出现 Feed Post 文件上传控件。"
            ) from exc
        return self._active_dialog(driver) or driver

    def upload(self, driver: Chrome, media: Iterable[PlatformMedia]) -> None:
        items = tuple(media)
        if not items:
            raise PlatformValidationError("Instagram Feed Post 至少需要 1 个图片或视频。")
        file_input = self._find_file_input(driver)
        if file_input is None:
            raise PlatformPublishError("Instagram 发帖界面没有可用的文件上传控件。")
        paths = "\n".join(str(Path(item.path).resolve()) for item in items)
        try:
            file_input.send_keys(paths)
        except ElementNotInteractableException:
            try:
                driver.execute_script(
                    "arguments[0].style.display='block'; arguments[0].style.visibility='visible';",
                    file_input,
                )
                file_input.send_keys(paths)
            except WebDriverException as exc:
                raise PlatformPublishError(f"Instagram 媒体文件无法写入上传控件：{exc}") from exc
        except WebDriverException as exc:
            raise PlatformPublishError(f"Instagram 媒体上传失败：{exc}") from exc

    def wait_caption_step(self, driver: Chrome) -> WebElement | Chrome:
        end = time.monotonic() + 45
        clicks = 0
        while time.monotonic() < end:
            dialog = self._active_dialog(driver) or driver
            editor = self.find_caption_editor(dialog)
            if editor is not None:
                return dialog
            if clicks < 4:
                next_button = self._find_clickable(dialog, _NEXT_NAMES)
                if next_button is not None and self._is_enabled(next_button):
                    self._safe_click(driver, next_button)
                    clicks += 1
                    time.sleep(0.7)
                    continue
            if self._has_security_challenge(driver):
                raise PlatformNeedsReviewError(
                    "Instagram 在媒体处理期间出现安全验证，请人工处理后再继续。"
                )
            time.sleep(0.25)
        raise PlatformPublishError(
            "Instagram 媒体已上传，但没有在限定时间内进入 Caption / Share 步骤。"
        )

    @staticmethod
    def find_caption_editor(root: WebElement | Chrome) -> WebElement | None:
        selectors = (
            "[aria-label='Write a caption...']",
            "[aria-label='Write a caption…']",
            "[aria-label*='caption'][contenteditable='true']",
            "div[role='textbox'][contenteditable='true']",
            "textarea[aria-label*='caption']",
        )
        for selector in selectors:
            try:
                for item in root.find_elements(By.CSS_SELECTOR, selector):
                    if item.is_displayed():
                        return item
            except (StaleElementReferenceException, WebDriverException):
                continue
        return None

    def write_caption(self, driver: Chrome, root: WebElement | Chrome, text: str) -> None:
        if not text:
            return
        editor = self.find_caption_editor(root)
        if editor is None:
            raise PlatformPublishError("Instagram Caption 步骤已打开，但没有找到正文输入区域。")
        try:
            editor.click()
        except WebDriverException as exc:
            raise PlatformPublishError(f"Instagram Caption 输入区域无法聚焦：{exc}") from exc
        try:
            driver.execute_cdp_cmd("Input.insertText", {"text": text})
        except WebDriverException:
            if any(ord(char) > 0xFFFF for char in text):
                raise PlatformPublishError(
                    "Instagram 正文包含 Emoji / 非 BMP Unicode，但当前 Chrome 无法使用 CDP 输入。"
                )
            try:
                editor.send_keys(text)
            except WebDriverException as exc:
                raise PlatformPublishError(f"Instagram Caption 输入失败：{exc}") from exc

    def wait_share_button(self, driver: Chrome) -> WebElement:
        try:
            return WebDriverWait(driver, 20).until(
                lambda _: self._enabled_share_button(driver) or False
            )
        except TimeoutException as exc:
            raise PlatformPublishError("Instagram 最终 Share 按钮没有进入可点击状态。") from exc

    def _enabled_share_button(self, driver: Chrome) -> WebElement | None:
        root = self._active_dialog(driver) or driver
        button = self._find_clickable(root, _SHARE_NAMES)
        if button is not None and self._is_enabled(button):
            return button
        return None

    @staticmethod
    def _active_dialog(driver: Chrome) -> WebElement | None:
        try:
            dialogs = [item for item in driver.find_elements(By.CSS_SELECTOR, "[role='dialog']") if item.is_displayed()]
        except (StaleElementReferenceException, WebDriverException):
            return None
        return dialogs[-1] if dialogs else None

    @staticmethod
    def _find_file_input(driver: Chrome) -> WebElement | None:
        try:
            inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        except WebDriverException:
            return None
        for item in reversed(inputs):
            try:
                accept = (item.get_attribute("accept") or "").casefold()
                if not accept or "image" in accept or "video" in accept:
                    return item
            except StaleElementReferenceException:
                continue
        return None

    @staticmethod
    def _find_clickable(root: WebElement | Chrome, names: tuple[str, ...]) -> WebElement | None:
        for name in names:
            literal = InstagramComposerComponent._xpath_literal(name)
            xpath = (
                ".//*[self::button or self::a or @role='button' or @role='menuitem']"
                f"[normalize-space(.)={literal} or normalize-space(@aria-label)={literal}]"
            )
            try:
                items = root.find_elements(By.XPATH, xpath)
            except WebDriverException:
                continue
            for item in reversed(items):
                try:
                    if item.is_displayed():
                        return item
                except StaleElementReferenceException:
                    continue
        return None

    @staticmethod
    def _safe_click(driver: Chrome, element: WebElement) -> None:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", element)
        except WebDriverException:
            pass
        try:
            element.click()
            return
        except WebDriverException:
            pass
        try:
            clicked = driver.execute_script("arguments[0].click(); return true;", element)
        except WebDriverException as exc:
            raise PlatformPublishError(f"Instagram 控件无法点击：{exc}") from exc
        if not clicked:
            raise PlatformPublishError("Instagram 控件当前不可点击。")

    @staticmethod
    def _is_enabled(element: WebElement) -> bool:
        try:
            return element.is_enabled() and element.get_attribute("aria-disabled") != "true"
        except (StaleElementReferenceException, WebDriverException):
            return False

    @staticmethod
    def _dismiss_optional_prompts(driver: Chrome) -> None:
        for name in ("Not Now", "以后再说", "稍后", "取消"):
            button = InstagramComposerComponent._find_clickable(driver, (name,))
            if button is not None:
                try:
                    button.click()
                    time.sleep(0.2)
                except WebDriverException:
                    pass

    @staticmethod
    def _has_security_challenge(driver: Chrome) -> bool:
        current_url = (driver.current_url or "").casefold()
        return any(marker in current_url for marker in ("/challenge/", "/checkpoint/", "/two_factor/"))

    @staticmethod
    def _xpath_literal(value: str) -> str:
        if "'" not in value:
            return f"'{value}'"
        if '"' not in value:
            return f'"{value}"'
        parts = value.split("'")
        return "concat(" + ", \"'\", ".join(f"'{part}'" for part in parts) + ")"


class InstagramVerifierComponent:
    """High-confidence post-click verification. Uncertainty is never retried."""

    def verify(self, driver: Chrome) -> dict[str, Any]:
        end = time.monotonic() + 45
        while time.monotonic() < end:
            if InstagramComposerComponent._has_security_challenge(driver):
                return {
                    "verified": False,
                    "published_url": None,
                    "message": "Instagram opened a security challenge after Share.",
                }
            current_url = driver.current_url or ""
            parsed = urlparse(current_url)
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2 and parts[0] in {"p", "reel"}:
                return {
                    "verified": True,
                    "published_url": current_url,
                    "message": "Instagram navigated to the published post.",
                }

            try:
                status_items = driver.find_elements(By.CSS_SELECTOR, "[role='alert'], [role='status']")
            except WebDriverException:
                status_items = []
            for item in status_items:
                try:
                    if not item.is_displayed():
                        continue
                    text = " ".join((item.text or "").split()).casefold()
                    if text and any(marker in text for marker in _SUCCESS_MARKERS):
                        return {
                            "verified": True,
                            "published_url": None,
                            "message": "Instagram displayed an explicit post-shared confirmation.",
                        }
                except StaleElementReferenceException:
                    continue
            time.sleep(0.25)
        return {
            "verified": False,
            "published_url": None,
            "message": "Share was clicked but Instagram did not expose a high-confidence success signal.",
        }


class InstagramCompositeAdapter(PlatformAdapter):
    """Instagram Feed Post adapter using the Phase 7 composition boundary."""

    capabilities = PlatformCapabilities(
        name="instagram",
        display_name="Instagram",
        supports_text=True,
        media_types=("image", "video"),
    )

    def __init__(self) -> None:
        self.identity = InstagramIdentityComponent()
        self.navigation = InstagramNavigationComponent()
        self.composer = InstagramComposerComponent()
        self.verifier = InstagramVerifierComponent()

    def validate_content(self, content: PlatformContent) -> None:
        super().validate_content(content)
        if not content.media:
            raise PlatformValidationError("Instagram Feed Post 至少需要 1 个图片或视频。")
        if len(content.media) > 20:
            raise PlatformValidationError("Instagram Feed Post 当前最多允许 20 个媒体文件。")

    def check_login(self, driver: Chrome) -> dict[str, Any]:
        return self.identity.check_login(driver)

    def discover_identity(self, driver: Chrome) -> dict[str, str]:
        return self.identity.discover_identity(driver)

    def publish(self, driver: Chrome, content: PlatformContent) -> dict[str, Any]:
        self.validate_content(content)
        if not content.target_id:
            raise PlatformPublishError("Instagram Channel 缺少 target_id，已停止发布。")

        emit_platform_progress("checking_login", "检查 Instagram 登录状态")
        login = self.identity.check_login(driver)
        if login["checkpoint"]:
            raise PlatformNeedsReviewError("Instagram 出现安全验证，请人工处理后再继续。")
        if not login["logged_in"]:
            raise PlatformNeedsReviewError("当前 iX 环境尚未登录 Instagram，请先人工登录。")
        emit_platform_progress("checking_login", "Instagram 登录状态正常")

        emit_platform_progress(
            "checking_identity",
            "校验 Instagram 发布身份 ds_user_id == target_id",
            {"target_id": content.target_id},
        )
        self.identity.verify_actor(driver, content, stage="发布开始前")

        emit_platform_progress("navigating", "打开 Instagram 首页")
        self.navigation.open_home(driver)
        self.identity.verify_actor(driver, content, stage="进入 Instagram 后")

        media_started = time.monotonic()
        emit_platform_progress("opening_composer", "打开 Instagram Create / Post")
        composer = self.composer.open(driver)
        emit_platform_progress("opening_composer", "Instagram Feed Post 界面已打开")
        emit_platform_progress("uploading_media", f"上传 {len(content.media)} 个媒体文件")
        self.composer.upload(driver, content.media)
        emit_platform_progress("waiting_media", "等待 Instagram 媒体处理")
        caption_root = self.composer.wait_caption_step(driver)
        media_ms = int((time.monotonic() - media_started) * 1000)
        emit_platform_progress(
            "waiting_media",
            "Instagram 媒体处理完成",
            {"media_ms": media_ms, "media_count": len(content.media)},
        )

        if content.text:
            emit_platform_progress("writing_text", "写入 Instagram Caption")
            self.composer.write_caption(driver, caption_root, content.text)
            emit_platform_progress("writing_text", "Instagram Caption 已写入")

        emit_platform_progress("advancing", "等待 Instagram Share 步骤")
        share_button = self.composer.wait_share_button(driver)
        self.identity.verify_actor(driver, content, stage="点击 Share 前")
        emit_platform_progress(
            "checking_identity",
            "Instagram 最终发布前身份检查通过",
            {"target_id": content.target_id},
        )
        emit_platform_progress("ready_to_submit", "Instagram Share 按钮已就绪")
        emit_platform_progress("submitting", "点击 Instagram Share")
        try:
            self.composer._safe_click(driver, share_button)
        except Exception as exc:
            raise PlatformNeedsReviewError(
                "Instagram Share 点击阶段出现不确定异常。请先人工确认账号中是否已发布，避免重复帖子。",
                submitted=True,
            ) from exc
        emit_platform_progress("submitting", "已执行 Instagram Share 点击")

        verification_started = time.monotonic()
        emit_platform_progress("verifying", "验证 Instagram 发布结果")
        try:
            verification = self.verifier.verify(driver)
        except Exception as exc:
            raise PlatformNeedsReviewError(
                "Instagram 已执行 Share，但验证阶段出现异常。请人工确认后再决定是否重试。",
                submitted=True,
            ) from exc
        verification_ms = int((time.monotonic() - verification_started) * 1000)
        emit_platform_progress(
            "verifying",
            "Instagram 发布验证成功" if verification["verified"] else "Instagram 发布结果需要人工确认",
            {"verification_ms": verification_ms},
        )

        return {
            "platform": "instagram",
            "submitted": True,
            "verified": bool(verification["verified"]),
            "published_url": verification.get("published_url"),
            "verification": verification["message"],
            "current_url": driver.current_url,
            "title": driver.title,
            "target_type": content.target_type,
            "target_id": content.target_id,
            "target_name": content.target_name,
            "target_url": content.target_url,
            "media_duration_ms": media_ms,
            "verification_duration_ms": verification_ms,
        }
