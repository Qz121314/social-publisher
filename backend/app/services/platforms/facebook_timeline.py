from __future__ import annotations

import time
from typing import Any

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver import Chrome

from app.services.platforms.base import (
    PlatformContent,
    PlatformNeedsReviewError,
    PlatformPublishError,
    emit_platform_progress,
)
from app.services.platforms.facebook_unicode_flow import UnicodeFacebookFlowAdapter


class TimelineFacebookFlowAdapter(UnicodeFacebookFlowAdapter):
    """Existing verified Facebook flow with per-attempt progress instrumentation.

    This wrapper intentionally reuses the established Selenium primitives and
    identity gates. It only exposes their progress to Phase 6 Timeline records and
    captures coarse performance segments; it does not weaken or bypass any gate.
    """

    def publish(self, driver: Chrome, content: PlatformContent) -> dict[str, Any]:
        self.validate_content(content)
        if not content.target_url or not content.target_id:
            raise PlatformPublishError(
                "该 iX 环境尚未设置 Facebook 默认发布主页，已停止发布以避免发错位置。"
            )

        emit_platform_progress("checking_login", "检查 Facebook 登录状态")
        login = self.check_login(driver)
        if login["checkpoint"]:
            raise PlatformNeedsReviewError(
                "Facebook 出现安全验证 / Checkpoint，请人工处理后再继续。"
            )
        if not login["logged_in"]:
            raise PlatformNeedsReviewError(
                "当前 iX 环境尚未登录 Facebook，请先人工登录。"
            )
        emit_platform_progress("checking_login", "Facebook 登录状态正常")

        # The existing target preparation includes actor_id == target_id gates
        # before/after navigation. We expose the stage without changing that logic.
        emit_platform_progress(
            "checking_identity",
            "校验 Facebook 发布身份 actor_id == target_id",
            {"target_id": content.target_id},
        )
        emit_platform_progress("navigating", "打开配置的 Facebook 发布目标")
        self._navigate_to_target(driver, content)
        emit_platform_progress("checking_identity", "目标主页身份校验通过")

        media_ms = 0
        try:
            emit_platform_progress("opening_composer", "打开 Facebook 发帖 Composer")
            composer = self._open_composer(driver)
            emit_platform_progress("opening_composer", "Composer 已打开")

            if content.text:
                emit_platform_progress("writing_text", "写入帖子正文")
                self._fill_text(composer, content.text)
                emit_platform_progress("writing_text", "帖子正文已写入")

            if content.media:
                emit_platform_progress(
                    "uploading_media",
                    f"上传 {len(content.media)} 个媒体文件",
                )
                media_started = time.monotonic()
                self._upload_media(driver, composer, content.media)
                media_ms = int((time.monotonic() - media_started) * 1000)
                emit_platform_progress(
                    "waiting_media",
                    "媒体上传与平台处理已完成",
                    {"media_ms": media_ms, "media_count": len(content.media)},
                )

            emit_platform_progress("advancing", "检查 Next / Post 发布流程")
            post_button = self._wait_post_ready(driver, composer)
            emit_platform_progress(
                "checking_identity",
                "最终发布前身份检查通过",
                {"target_id": content.target_id},
            )
            emit_platform_progress("ready_to_submit", "最终发布按钮已就绪")
            emit_platform_progress("submitting", "点击最终发布按钮")
            self._safe_click(driver, post_button)
            emit_platform_progress("submitting", "已执行最终发布点击")
        except PlatformNeedsReviewError:
            raise
        except TimeoutException as exc:
            raise PlatformPublishError(
                "Facebook 发帖界面在超时时间内没有进入可发布状态。页面结构可能变化，或媒体仍在处理。"
            ) from exc
        except WebDriverException as exc:
            raise PlatformPublishError(f"Facebook 发布前浏览器自动化失败：{exc}") from exc

        # Any uncertainty after the final Post click must remain needs_review.
        verification_started = time.monotonic()
        emit_platform_progress("verifying", "验证 Facebook 发布结果")
        try:
            self._wait_composer_closed(driver, composer)
            verification = self._verify_submission(driver, content)
            current_url = driver.current_url
            title = driver.title
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
            "current_url": current_url,
            "title": title,
            "target_type": content.target_type,
            "target_id": content.target_id,
            "target_name": content.target_name,
            "target_url": content.target_url,
            "media_duration_ms": media_ms,
            "verification_duration_ms": verification_ms,
        }
