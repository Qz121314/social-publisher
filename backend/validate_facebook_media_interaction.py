from __future__ import annotations

from selenium.common.exceptions import ElementNotInteractableException

import app.services.platforms.facebook_unicode_flow as unicode_flow_module
from app.services.platforms.facebook_unicode_flow import UnicodeFacebookFlowAdapter


class FakeElement:
    def __init__(self) -> None:
        self.click_calls = 0
        self.rect = {"width": 120, "height": 40}

    def is_displayed(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return True

    def get_attribute(self, name: str):
        if name == "aria-disabled":
            return None
        return None

    def click(self) -> None:
        self.click_calls += 1


class NativeDialogGuardElement(FakeElement):
    def click(self) -> None:
        raise AssertionError("Media activation must not use a trusted element.click().")


class FakeDriver:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    def execute_script(self, script: str, *args):
        self.scripts.append(script)
        if "dispatchEvent" in script:
            return True
        if "elementFromPoint" in script:
            return True
        return None


class FailingActionChains:
    def __init__(self, driver) -> None:
        self.driver = driver

    def move_to_element(self, element):
        return self

    def pause(self, seconds: float):
        return self

    def click(self):
        return self

    def perform(self) -> None:
        raise ElementNotInteractableException("synthetic element not interactable")


adapter = UnicodeFacebookFlowAdapter()

# Ordinary controls: an ActionChains interactability failure must be contained and
# retried through the bounded native element click rather than escaping as a raw
# ChromeDriver stacktrace.
driver = FakeDriver()
element = FakeElement()
original_action_chains = unicode_flow_module.ActionChains
unicode_flow_module.ActionChains = FailingActionChains
try:
    adapter._safe_click(driver, element)  # type: ignore[arg-type]
finally:
    unicode_flow_module.ActionChains = original_action_chains
assert element.click_calls == 1

# Media activation: never use a trusted WebDriver/element click. That trusted click
# can open the Windows native file picker and steal focus from Selenium.
media_driver = FakeDriver()
media_button = NativeDialogGuardElement()
adapter._activate_media_button(media_driver, media_button)  # type: ignore[arg-type]
assert media_button.click_calls == 0
assert any("dispatchEvent" in script for script in media_driver.scripts)

print("facebook media interaction guard ok")
