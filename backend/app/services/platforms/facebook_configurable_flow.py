from __future__ import annotations

from app.services.platforms.facebook_flow_config import load_facebook_flow
from app.services.platforms.facebook_unified_flow import UnifiedFacebookFlowAdapter


class ConfigurableFacebookFlowAdapter(UnifiedFacebookFlowAdapter):
    """Facebook publishing driven by runtime-editable text keyword groups.

    The automation actions remain constrained and safe: actor-ID validation,
    visible click, text entry, media upload, bounded Next/Continue advancement,
    final Post click, and result verification. Only the localized text used to
    locate Facebook UI states is configurable at runtime.
    """

    @staticmethod
    def _keywords(key: str) -> tuple[str, ...]:
        return tuple(load_facebook_flow()[key])

    @property
    def _PRIMARY_PROMPTS(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("entry_keywords")

    @property
    def _COMPOSER_TEXT(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("entry_keywords")

    @property
    def _SURFACE_TITLES(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("surface_titles")

    @property
    def _MEDIA_TEXT(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("media_keywords")

    @property
    def _NEXT_TEXT(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("next_keywords")

    @property
    def _POST_TEXT(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("post_keywords")

    @property
    def _UPLOAD_BUSY_TEXT(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("upload_busy_keywords")

    @property
    def _SUCCESS_TEXT(self) -> tuple[str, ...]:  # noqa: N802
        return self._keywords("success_keywords")
