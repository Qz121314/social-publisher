from __future__ import annotations

import time
from typing import Any

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    MoveTargetOutOfBoundsException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from app.services.platforms.base import PlatformPublishError
from app.services.platforms.facebook_configurable_flow import ConfigurableFacebookFlowAdapter


class UnicodeFacebookFlowAdapter(ConfigurableFacebookFlowAdapter):
    """Facebook flow with Unicode-safe input and guarded browser interaction.

    ChromeDriver ``send_keys`` still rejects non-BMP code points in some Chrome /
    driver combinations. Facebook posts commonly contain emoji, so composer input
    is sent through Chrome DevTools ``Input.insertText`` after the real editor has
    been focused.

    Media selection deliberately never uses a trusted WebDriver click on
    Facebook's Photo/Video control. A trusted click can open the Windows native
    file picker, which steals focus from the browser and leaves the subsequent DOM
    automation in an ``element not interactable`` state. Instead, the Facebook UI
    is activated with an untrusted DOM event and the selected project asset is
    assigned directly to ``input[type=file]`` by Selenium ``send_keys``.
    """

    def _safe_click(self, driver: Any, element: WebElement) -> None:
        """Click a visible DOM control without leaking raw interactability errors.

        This helper is used for ordinary Facebook controls, including Composer,
        Next and final Post. It scrolls first, retries bounded native interaction,
        and only uses a DOM click when the element still passes a center-point
        hit-test. The Photo/Video control is intentionally handled separately by
        ``_activate_media_button`` so this method can never open a native picker in
        the media workflow.
        """

        last_error: Exception | None = None
        deadline = time.monotonic() + 3.0

        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                element,
            )
        except WebDriverException:
            pass

        while time.monotonic() < deadline:
            try:
                if not element.is_displayed():
                    raise ElementNotInteractableException("element is not displayed")
                if not self._is_enabled(element):
                    raise ElementNotInteractableException("element is disabled")
                rect = element.rect
                if float(rect.get("width") or 0) < 1 or float(rect.get("height") or 0) < 1:
                    raise ElementNotInteractableException("element has no clickable area")
            except StaleElementReferenceException as exc:
                raise PlatformPublishError(
                    "Facebook 页面在点击控件前已刷新，原控件失效。请重新执行当前任务。"
                ) from exc
            except WebDriverException as exc:
                last_error = exc
                time.sleep(0.12)
                continue

            try:
                ActionChains(driver).move_to_element(element).pause(0.05).click().perform()
                return
            except (
                ElementClickInterceptedException,
                ElementNotInteractableException,
                MoveTargetOutOfBoundsException,
                WebDriverException,
            ) as exc:
                last_error = exc

            try:
                element.click()
                return
            except (
                ElementClickInterceptedException,
                ElementNotInteractableException,
                WebDriverException,
            ) as exc:
                last_error = exc

            # Last bounded fallback. Never force-click an occluded/disabled node:
            # the center point must still resolve to the element or its descendant.
            try:
                clicked = driver.execute_script(
                    """
                    const el = arguments[0];
                    if (!el || !el.isConnected) return false;
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' ||
                        style.pointerEvents === 'none') return false;
                    if (el.getAttribute('aria-disabled') === 'true' || el.disabled) return false;
                    const r = el.getBoundingClientRect();
                    if (r.width < 1 || r.height < 1) return false;
                    const x = Math.min(window.innerWidth - 1, Math.max(0, r.left + r.width / 2));
                    const y = Math.min(window.innerHeight - 1, Math.max(0, r.top + r.height / 2));
                    const hit = document.elementFromPoint(x, y);
                    if (!hit || !(hit === el || el.contains(hit))) return false;
                    el.click();
                    return true;
                    """,
                    element,
                )
                if clicked:
                    return
            except WebDriverException as exc:
                last_error = exc

            time.sleep(0.15)

        label = ""
        try:
            label = self._element_label(element)
        except Exception:
            pass
        detail = f" 控件={label!r}。" if label else ""
        error_name = type(last_error).__name__ if last_error is not None else "unknown"
        raise PlatformPublishError(
            "Facebook 已找到页面控件，但该控件当前不可交互。"
            f"{detail}交互错误={error_name}。页面可能仍在切换、存在遮罩层或焦点被其他窗口占用。"
        ) from last_error

    def _activate_media_button(self, driver: Any, button: WebElement) -> None:
        """Activate Facebook media mode without opening the Windows file picker.

        WebDriver/ActionChains clicks are trusted user gestures. Facebook may use
        them to call a native file chooser, which is outside Selenium's DOM and can
        block the rest of the publish flow. Dispatching an untrusted bubbling mouse
        sequence still reaches Facebook's React handler but does not grant a native
        file-picker user activation. The actual project file is attached later via
        ``input[type=file].send_keys(<absolute project asset path>)``.
        """

        try:
            activated = driver.execute_script(
                """
                const el = arguments[0];
                if (!el || !el.isConnected) return false;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') return false;
                el.scrollIntoView({block: 'center', inline: 'center'});
                const init = {bubbles: true, cancelable: true, composed: true, view: window};
                el.dispatchEvent(new MouseEvent('mousedown', init));
                el.dispatchEvent(new MouseEvent('mouseup', init));
                el.dispatchEvent(new MouseEvent('click', init));
                return true;
                """,
                button,
            )
        except WebDriverException as exc:
            raise PlatformPublishError(
                "Facebook 已找到“照片/视频”入口，但无法在浏览器页面内激活媒体模式。"
            ) from exc

        if not activated:
            raise PlatformPublishError(
                "Facebook 已找到“照片/视频”入口，但该入口当前不可用。"
            )

        # Give Facebook a short render turn before the existing bounded input
        # resolver looks for the composer-owned file input.
        time.sleep(0.2)

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

        self._safe_click(driver, editor)

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
                raise PlatformPublishError(f"Facebook 正文输入失败：{type(exc).__name__}") from exc

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
