from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from selenium.webdriver import Chrome


class PlatformValidationError(ValueError):
    """Raised when content is incompatible with a platform adapter."""


class PlatformPublishError(RuntimeError):
    """Raised when a publish attempt failed before a confirmed submission."""


class PlatformNeedsReviewError(RuntimeError):
    """Raised when human review is required before retrying a job.

    `submitted=True` means the adapter may already have submitted the post. The
    worker must not retry such a job automatically because that could create a
    duplicate post.
    """

    def __init__(self, message: str, *, submitted: bool = False) -> None:
        super().__init__(message)
        self.submitted = submitted


@dataclass(frozen=True)
class PlatformCapabilities:
    name: str
    display_name: str
    supports_text: bool
    media_types: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["media_types"] = list(self.media_types)
        return result


@dataclass(frozen=True)
class PlatformMedia:
    media_type: str
    path: Path
    mime_type: str
    original_name: str


@dataclass(frozen=True)
class PlatformContent:
    text: str
    media: tuple[PlatformMedia, ...]
    target_type: str | None = None
    target_id: str | None = None
    target_name: str | None = None
    target_url: str | None = None


class PlatformAdapter(ABC):
    capabilities: PlatformCapabilities

    def validate_content(self, content: PlatformContent) -> None:
        text = content.text.strip()
        if not text and not content.media:
            raise PlatformValidationError("A post needs text, media, or both.")
        if text and not self.capabilities.supports_text:
            raise PlatformValidationError(
                f"{self.capabilities.display_name} does not support text in this adapter."
            )

        allowed = set(self.capabilities.media_types)
        unsupported = sorted({item.media_type for item in content.media} - allowed)
        if unsupported:
            raise PlatformValidationError(
                f"Unsupported media type(s): {', '.join(unsupported)}."
            )

    @abstractmethod
    def check_login(self, driver: Chrome) -> dict[str, Any]:
        """Inspect the attached browser and report platform login state."""

    @abstractmethod
    def publish(self, driver: Chrome, content: PlatformContent) -> dict[str, Any]:
        """Publish validated content and return a platform-specific result."""
