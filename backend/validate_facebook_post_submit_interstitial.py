from __future__ import annotations

import inspect

from app.services.platforms.facebook_components import FacebookSubmitComponent
from app.services.platforms.facebook_flow_config import default_config, validate_facebook_flow
from app.services.platforms.facebook_unicode_flow import UnicodeFacebookFlowAdapter


def main() -> None:
    config = default_config()
    publish_original = config.get("publish_original_keywords")
    assert publish_original
    assert "发布原帖" in publish_original
    assert any(value.casefold() == "publish original post" for value in publish_original)

    # Existing runtime payloads that predate this keyword group must remain valid
    # and receive the new safe default automatically.
    legacy_payload = {key: value for key, value in config.items() if key != "publish_original_keywords"}
    normalized = validate_facebook_flow(legacy_payload)
    assert normalized["publish_original_keywords"] == publish_original

    resolver_source = inspect.getsource(UnicodeFacebookFlowAdapter._resolve_post_submit_interstitial)
    finder_source = inspect.getsource(UnicodeFacebookFlowAdapter._find_publish_original_button)
    component_source = inspect.getsource(FacebookSubmitComponent.resolve_interstitial)

    assert "publish_original_keywords" in resolver_source
    assert "点击发布原帖前" in resolver_source
    assert "submitted=True" in resolver_source
    assert "role='dialog'" in finder_source or "aria-modal='true'" in finder_source
    assert "_resolve_post_submit_interstitial" in component_source

    # The promotion CTA must not be part of this dedicated bypass group.
    assert "继续" not in publish_original
    assert "Continue" not in publish_original

    print("facebook post-submit interstitial guard ok")


if __name__ == "__main__":
    main()
