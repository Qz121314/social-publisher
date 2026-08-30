from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.flow import Flow, FlowRevision, FlowStep, utcnow


def bootstrap_phase8_records(db: Session) -> dict[str, int]:
    seeded = _ensure_instagram_feed_flow(db)
    db.commit()
    return {"instagram_flows_seeded": seeded}


def _ensure_instagram_feed_flow(db: Session) -> int:
    flow = db.scalar(
        select(Flow).where(Flow.platform == "instagram", Flow.key == "feed_post")
    )
    if flow is not None:
        if flow.current_revision_id is None and flow.revisions:
            flow.current_revision_id = flow.revisions[0].id
        return 0

    flow = Flow(
        platform="instagram",
        key="feed_post",
        name="Instagram Feed Post",
        enabled=True,
    )
    db.add(flow)
    db.flush()

    revision = FlowRevision(
        flow_id=flow.id,
        version=1,
        label="v1.0 web baseline",
        status="published",
        notes=(
            "Phase 8A Instagram desktop Feed Post baseline. Stable ds_user_id "
            "identity gates are required before opening and before final Share."
        ),
        published_at=utcnow(),
    )
    db.add(revision)
    db.flush()

    steps = (
        (10, "CHECK_LOGIN", "检查 Instagram 登录", {}),
        (20, "VERIFY_ACTOR", "校验发布身份", {"gate": "ds_user_id == target_id"}),
        (30, "NAVIGATE", "打开 Instagram", {"url": "https://www.instagram.com/"}),
        (40, "CLICK_TEXT", "打开 Create / Post", {}),
        (50, "UPLOAD_MEDIA", "上传 Feed 媒体", {"required": True, "max_items": 20}),
        (60, "WAIT_MEDIA_READY", "等待媒体处理", {}),
        (70, "NEXT", "推进 Crop / Edit", {"repeat_until": "caption", "max": 4}),
        (80, "INPUT_TEXT", "输入 Caption", {"optional": True, "unicode": "cdp_insert_text"}),
        (90, "VERIFY_ACTOR", "Share 前再次校验身份", {"gate": "ds_user_id == target_id"}),
        (100, "PUBLISH", "最终 Share", {}),
        (110, "VERIFY_RESULT", "验证发布结果", {"uncertain": "needs_review"}),
    )
    for sort_order, action_type, name, config in steps:
        db.add(
            FlowStep(
                revision_id=revision.id,
                sort_order=sort_order,
                action_type=action_type,
                name=name,
                config_json=json.dumps(config, ensure_ascii=False),
                enabled=True,
            )
        )

    flow.current_revision_id = revision.id
    return 1
