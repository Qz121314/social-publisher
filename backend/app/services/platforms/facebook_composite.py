from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver import Chrome

from app.services.platforms.base import (
    PlatformAdapter,
    PlatformCapabilities,
    PlatformContent,
    PlatformNeedsReviewError,
    PlatformPublishError,
    emit_platform_progress,
)
from app.services.platforms.facebook_components import FacebookComponentSet
from app.services.platforms.facebook_surface import _ACTIVE_SURFACE_CONTENT
from app.services.platforms.facebook_target import _ACTIVE_PUBLISH_CONTENT
from app.services.platforms.facebook_unicode_flow import UnicodeFacebookFlowAdapter


@contextmanager
def _facebook_execution_scope(content: PlatformContent) -> Iterator[None]:
    """Bind legacy Selenium primitives to one immutable execution snapshot.

    The verified target/surface primitives historically received their content
    through two ContextVars installed by inheritance wrappers. The composite
    adapter owns orchestration now, so it binds both contexts explicitly. This
    keeps actor-ID gates active without depending on MRO side effects and remains
    safe for the existing multi-threaded Worker Pool.
    """

    publish_token = _ACTIVE_PUBLISH_CONTENT.set(content)
    surface_token = _ACTIVE_SURFACE_CONTENT.set(content)
    try:
        yield
    finally:
        _ACTIVE_SURFACE_CONTENT.reset(surface_token)
        _ACTIVE_PUBLISH_CONTENT.reset(publish_token)


class FacebookCompositeAdapter(PlatformAdapter):
    """Production Facebook adapter orchestrated through explicit components.

    The Selenium primitives below are intentionally the same ones that were
    verified during the Facebook PoC. Phase 7 changes ownership and structure,
    not browser behavior: the Registry now exposes a direct PlatformAdapter whose
    Identity/Navigation/Composer/Text/Media/Submit/Verifier concerns are composed
    instead of inherited through the PoC class chain.
    """

    capabilities = PlatformCapabilities(
        name="facebook",
        display_name="Facebook",
        supports_text=True,
        media_types=("image", "video"),
    )

    def __init__(
        self,
        primitives: UnicodeFacebookFlowAdapter | None = None,
    ) -> None:
        self._primitives = primitives or UnicodeFacebookFlowAdapter()
        self.components = FacebookComponentSet.build(self._primitives)

    def check_login(self, driver: Chrome) -> dict[str, Any]:
        return self.components.identity.check_login(driver)

    def confirm_composer_entry(
        self,
        driver: Chrome,
        content: PlatformContent,
    ) -> dict[str, Any]:
        """Behavior-confirm the configured target without typing or publishing."""

        with _facebook_execution_scope(content):
            return self.components.composer.confirm_entry(driver, content)

    def publish(self, driver: Chrome, content: PlatformContent) -> dict[str, Any]:
        self.validate_content(content)
        if not content.target_url or not content.target_id:
            raise PlatformPublishError(
                "该 iX 环境尚未设置 Facebook 默认发布主页，已停止发布以避免发错位置。"
            )

        with _facebook_execution_scope(content):
            return self._publish_scoped(driver, content)

    def _publish_scoped(
        self,
        driver: Chrome,
        content: PlatformContent,
    ) -> dict[str, Any]:
        emit_platform_progress("checking_login", "检查 Facebook 登录状态")
        login = self.components.identity.check_login(driver)
        if login["checkpoint"]:
            raise PlatformNeedsReviewError(
                "Facebook 出现安全验证 / Checkpoint，请人工处理后再继续。"
            )
        if not login["logged_in"]:
            raise PlatformNeedsReviewError(
                "当前 iX 环境尚未登录 Facebook，请先人工登录。"
            )
        emit_platform_progress("checking_login", "Facebook 登录状态正常")

        emit_platform_progress(
            "checking_identity",
            "校验 Facebook 发布身份 actor_id == target_id",
            {"target_id": content.target_id},
        )
        emit_platform_progress("navigating", "打开配置的 Facebook 发布目标")
        self.components.navigation.open_target(driver, content)
        emit_platform_progress("checking_identity", "目标主页身份校验通过")

        media_ms = 0
        try:
            emit_platform_progress("opening_composer", "打开 Facebook 发帖 Composer")
            composer = self.components.composer.open(driver)
            emit_platform_progress("opening_composer", "Composer 已打开")

            if content.text:
                emit_platform_progress("writing_text", "写入帖子正文")
                self.components.text.write(composer, content.text)
                emit_platform_progress("writing_text", "帖子正文已写入")

            if content.media:
                emit_platform_progress(
                    "uploading_media",
                    f"上传 {len(content.media)} 个媒体文件",
                )
                media_started = time.monotonic()
                self.components.media.upload(driver, composer, content.media)
                media_ms = int((time.monotonic() - media_started) * 1000)
                emit_platform_progress(
                    "waiting_media",
                    "媒体上传与平台处理已完成",
                    {"media_ms": media_ms, "media_count": len(content.media)},
                )

            emit_platform_progress("advancing", "检查 Next / Post 发布流程")
            post_button = self.components.submit.wait_ready(driver, composer)
            # The delegated wait_ready primitive performs the original final
            # actor-ID gate. Record the evidence only after it returns safely.
            emit_platform_progress(
                "checking_identity",
                "最终发布前身份检查通过",
                {"target_id": content.target_id},
            )
            emit_platform_progress("ready_to_submit", "最终发布按钮已就绪")
            emit_platform_progress("submitting", "点击最终发布按钮")
            self.components.submit.click(driver, post_button)
            emit_platform_progress("submitting", "已执行最终发布点击")
        except PlatformNeedsReviewError:
            raise
        except TimeoutException as exc:
            raise PlatformPublishError(
                "Facebook 发帖界面在超时时间内没有进入可发布状态。页面结构可能变化，或媒体仍在处理。"
            ) from exc
        except WebDriverException as exc:
            raise PlatformPublishError(f"Facebook 发布前浏览器自动化失败：{exc}") from exc

        # Any uncertainty after the final Post click remains needs_review. No
        # composition component is allowed to turn this into an automatic retry.
        verification_started = time.monotonic()
        emit_platform_progress("verifying", "验证 Facebook 发布结果")
        try:
            self.components.verifier.wait_composer_closed(driver, composer)
            verification = self.components.verifier.verify(driver, content)
            diagnostics = self.components.diagnostics.snapshot(driver, content)
        except PlatformNeedsReviewError:
            raise
        except Exception as exc:
            raise PlatformNeedsReviewError(
                "系统已经执行最终发布点击，但验证结果前浏览器状态变得不确定。为了避免重复发帖，请人工确认 Facebook。",
                submitted=True,
            ) from exc

        verification_ms = int((time.monotonic() - verification_started) * 1000)
        if verification["verified"]:
            emit_platform_progress(
                "verifying",
                "Facebook 发布结果验证成功",
                {"verification_ms": verification_ms},
            )
        else:
            emit_platform_progress(
                "verifying",
                "已点击发布，但未能独立确认帖子结果",
                {"verification_ms": verification_ms},
            )

        return {
            "platform": "facebook",
            "submitted": True,
            "verified": verification["verified"],
            "published_url": verification.get("published_url"),
            "verification": verification["message"],
            "current_url": diagnostics["current_url"],
            "title": diagnostics["title"],
            "target_type": content.target_type,
            "target_id": content.target_id,
            "target_name": content.target_name,
            "target_url": content.target_url,
            "media_duration_ms": media_ms,
            "verification_duration_ms": verification_ms,
        }
