from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
from types import SimpleNamespace

from selenium.common.exceptions import WebDriverException

from app.services.platforms.base import PlatformPublishError
from app.services.platforms.facebook_composite import FacebookCompositeAdapter
from app.services.platforms.facebook_executor_v2 import FacebookExecutorV2
from app.services.platforms.registry import get_platform_adapter


class FakeInput:
    def __init__(self) -> None:
        self.values: list[str] = []
        self.id = "file-input"

    def get_attribute(self, name: str):
        if name == "multiple":
            return "multiple"
        if name == "accept":
            return "image/*,video/*"
        return None

    def send_keys(self, value: str) -> None:
        self.values.append(value)


class FakeButton:
    id = "media-button"


class FakeDriver:
    def __init__(self, *, supports_intercept: bool = True) -> None:
        self.supports_intercept = supports_intercept
        self.events: list[tuple[str, object]] = []

    def execute_cdp_cmd(self, method: str, params: dict):
        self.events.append((method, params))
        if not self.supports_intercept:
            raise WebDriverException("unsupported")
        return {}


class Harness(FacebookExecutorV2):
    def __init__(self) -> None:
        super().__init__()
        self.activated = False
        self.clicked = False
        self.file_input = FakeInput()

    def _media_signatures(self, root):
        return set()

    def _acceptable_file_inputs(self, root):
        return [self.file_input] if self.activated else []

    def _find_media_button(self, driver, composer):
        return FakeButton()

    def _safe_click(self, driver, element):
        self.clicked = True
        self.activated = True

    def _wait_media_attached(self, driver, composer, file_input, before_media):
        assert file_input is self.file_input
        assert self.file_input.values

    def _wait_media_processing(self, driver, composer):
        return None

    def _has_security_challenge(self, driver):
        return False


production = get_platform_adapter("facebook")
assert isinstance(production, FacebookCompositeAdapter)
assert isinstance(production._primitives, FacebookExecutorV2)

with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
    media_path = Path(handle.name)

try:
    harness = Harness()
    driver = FakeDriver(supports_intercept=True)
    harness._upload_media(
        driver,
        object(),  # type: ignore[arg-type]
        [SimpleNamespace(path=media_path)],
    )
    assert harness.clicked is True
    assert harness.file_input.values == [str(media_path.resolve())]
    assert driver.events[0] == (
        "Page.setInterceptFileChooserDialog",
        {"enabled": True},
    )
    assert driver.events[-1] == (
        "Page.setInterceptFileChooserDialog",
        {"enabled": False},
    )

    # If Chrome/iX cannot intercept the chooser, the executor must fail closed and
    # must not click the Facebook media entry at all.
    blocked = Harness()
    blocked_driver = FakeDriver(supports_intercept=False)
    try:
        blocked._upload_media(
            blocked_driver,
            object(),  # type: ignore[arg-type]
            [SimpleNamespace(path=media_path)],
        )
    except PlatformPublishError as exc:
        assert "Windows 文件夹" in str(exc)
    else:
        raise AssertionError("Unsupported interception must fail closed")
    assert blocked.clicked is False
finally:
    media_path.unlink(missing_ok=True)

# Keep the production executor focused on stability/compliance rather than
# anti-detection or review bypass techniques.
source = inspect.getsource(FacebookExecutorV2).casefold()
for forbidden in (
    "navigator.webdriver",
    "automationcontrolled",
    "--disable-blink-features",
    "captcha bypass",
    "fingerprint spoof",
):
    assert forbidden not in source

for state in (
    "media_entry_intercepted",
    "media_processing",
    "next_ready",
    "post_ready",
    "composer_closed",
    "unknown_post_submit_dialog",
):
    assert state in source

print("facebook executor v2 safeguards ok")
