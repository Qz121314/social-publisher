"""Backward-compatible Phase 6 import for the composed Facebook adapter.

Phase 7 moved Timeline orchestration into :class:`FacebookCompositeAdapter`.
Keep this symbol as an alias so local integrations importing the Phase 6 class
name do not break while the production Registry no longer depends on the PoC
inheritance chain.
"""

from app.services.platforms.facebook_composite import FacebookCompositeAdapter

TimelineFacebookFlowAdapter = FacebookCompositeAdapter

__all__ = ["TimelineFacebookFlowAdapter"]
