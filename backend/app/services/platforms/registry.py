from __future__ import annotations

from app.services.platforms.base import PlatformAdapter, PlatformValidationError
from app.services.platforms.facebook_unified_flow import UnifiedFacebookFlowAdapter

_ADAPTERS: dict[str, PlatformAdapter] = {
    "facebook": UnifiedFacebookFlowAdapter(),
}


def get_platform_adapter(platform: str) -> PlatformAdapter:
    key = platform.strip().lower()
    adapter = _ADAPTERS.get(key)
    if adapter is None:
        raise PlatformValidationError(f"Platform '{platform}' is not available yet.")
    return adapter


def list_platforms() -> list[dict[str, object]]:
    return [adapter.capabilities.to_dict() for adapter in _ADAPTERS.values()]
