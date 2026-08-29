from __future__ import annotations

from typing import Any

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from app.services.platforms.base import PlatformPublishError
from app.services.platforms.facebook_configurable_flow import ConfigurableFacebookFlowAdapter


class UnicodeFacebookFlowAdapter(ConfigurableFacebookFlowAdapter):
    """Facebook flow with Unicode-safe composer text entry.

    ChromeDriver ``send_keys`` still rejects non-BMP code points in some Chrome /
    driver combinations. Facebook posts commonly contain emoji, so composer input
    is sent through Chrome DevTools ``Input.insertText`` after the real editor has
    been focused. That path accepts full Unicode and behaves like text insertion in
    the focused editable surface. ``send_keys`` is retained only as a BMP-safe
    fallback when CDP insertion is unavailable.
    """

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
        except WebDriverException as exc:
            raise PlatformPublishError(f"Facebook 正文编辑器无法聚焦：{exc}") from exc

        inserted = False
        cdp_error: Exception | None = None
        try:
            driver.execute_cdp_cmd("Input.insertText", {"text": text})
            inserted = True
        except Exception as exc:  # Selenium may wrap CDP transport failures differently.
            cdp_error = exc

        if not inserted:
            if any(ord(char) > 0xFFFF for char in text):
                raise PlatformPublishError(
                    "Facebook 文案包含 emoji/非 BMP 字符，但当前 Chrome 无法使用 Unicode 输入通道。"
                    f" CDP 错误：{cdp_error}"
                ) from cdp_error
            try:
                editor.send_keys(text)
                inserted = True
            except WebDriverException as exc:
                raise PlatformPublishError(f"Facebook 正文输入失败：{exc}") from exc

        if not inserted:
            raise PlatformPublishError("Facebook 正文没有成功写入。")

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
            WebDriverWait(driver, 6).until(text_entered)
        except TimeoutException as exc:
            raise PlatformPublishError("Facebook 编辑器已输入正文，但页面没有确认文本已写入。") from exc
