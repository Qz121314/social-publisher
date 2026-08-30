from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.channel import Channel
from app.models.content import ContentItem, MediaAsset, PublishJob
from app.models.flow import Flow, FlowRevision
from app.models.publishing import PublishPlan


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def content_snapshot(db: Session, content: ContentItem) -> dict[str, Any]:
    media = list(
        db.scalars(
            select(MediaAsset)
            .where(MediaAsset.content_id == content.id)
            .order_by(MediaAsset.sort_order.asc())
        ).all()
    )
    return {
        "content_id": content.id,
        "platform": content.platform,
        "text": content.text,
        "media": [
            {
                "id": item.id,
                "media_type": item.media_type,
                "original_name": item.original_name,
                "stored_name": item.stored_name,
                "mime_type": item.mime_type,
                "file_size": item.file_size,
                "sort_order": item.sort_order,
            }
            for item in media
        ],
        "captured_at": utcnow().isoformat(),
    }


def channel_snapshot(channel: Channel) -> dict[str, Any]:
    return {
        "channel_id": channel.id,
        "profile_id": channel.profile_id,
        "platform": channel.platform,
        "target_id": channel.target_id,
        "target_name": channel.target_name,
        "target_type": channel.target_type,
        "target_url": channel.target_url,
        "captured_at": utcnow().isoformat(),
    }


def resolve_flow_revision(
    db: Session,
    *,
    platform: str,
    flow_revision_id: str | None,
) -> FlowRevision:
    if flow_revision_id:
        revision = db.get(FlowRevision, flow_revision_id)
        if revision is None:
            raise ValueError("Flow revision not found.")
        if revision.flow.platform != platform:
            raise ValueError("Flow revision platform does not match selected channels.")
        if revision.status != "published":
            raise ValueError("Only a published flow revision can be bound to a publish plan.")
        return revision

    flow = db.scalar(
        select(Flow).where(
            Flow.platform == platform,
            Flow.enabled.is_(True),
            Flow.current_revision_id.is_not(None),
        ).order_by(Flow.created_at.asc())
    )
    if flow is None or flow.current_revision_id is None:
        raise ValueError(f"No current published flow revision is configured for {platform}.")
    revision = db.get(FlowRevision, flow.current_revision_id)
    if revision is None or revision.status != "published":
        raise ValueError(f"Current flow revision for {platform} is unavailable.")
    return revision


def create_publish_plan(
    db: Session,
    *,
    content_id: str,
    channel_ids: list[str],
    publish_mode: str,
    timezone_name: str,
    scheduled_at: datetime | None,
    interval_seconds: int,
    flow_revision_id: str | None,
) -> PublishPlan:
    content = db.get(ContentItem, content_id)
    if content is None:
        raise ValueError("Content not found.")

    unique_channel_ids = list(dict.fromkeys(channel_ids))
    if not unique_channel_ids:
        raise ValueError("Select at least one channel.")
    if len(unique_channel_ids) > 200:
        raise ValueError("A publish plan may target at most 200 channels.")

    channels = list(
        db.scalars(select(Channel).where(Channel.id.in_(unique_channel_ids))).all()
    )
    channel_by_id = {channel.id: channel for channel in channels}
    missing = [channel_id for channel_id in unique_channel_ids if channel_id not in channel_by_id]
    if missing:
        raise ValueError(f"Unknown channel id(s): {', '.join(missing)}.")

    disabled = [channel.target_name for channel in channels if not channel.enabled]
    if disabled:
        raise ValueError(f"Disabled channel(s) cannot be scheduled: {', '.join(disabled)}.")

    platforms = {channel.platform for channel in channels}
    if len(platforms) != 1:
        raise ValueError("A V1 publish plan may only contain channels from one platform.")
    platform = next(iter(platforms))
    if content.platform != platform:
        raise ValueError(
            f"Content platform '{content.platform}' does not match channel platform '{platform}'."
        )

    mode = publish_mode.strip().lower()
    timezone_value = timezone_name.strip() or "UTC"
    try:
        timezone_info = ZoneInfo(timezone_value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone_value}.") from exc

    if mode not in {"immediate", "scheduled", "draft"}:
        raise ValueError("publish_mode must be immediate, scheduled, or draft.")
    if interval_seconds < 0 or interval_seconds > 86400:
        raise ValueError("interval_seconds must be between 0 and 86400.")
    if mode == "scheduled" and scheduled_at is None:
        raise ValueError("scheduled_at is required for scheduled publishing.")

    revision = resolve_flow_revision(
        db,
        platform=platform,
        flow_revision_id=flow_revision_id,
    )
    snapshot = content_snapshot(db, content)
    snapshot_json = json.dumps(snapshot, ensure_ascii=False)

    base_time = scheduled_at
    if mode == "immediate":
        base_time = utcnow()
    elif mode == "scheduled" and base_time is not None:
        if base_time.tzinfo is None:
            base_time = base_time.replace(tzinfo=timezone_info)
        base_time = base_time.astimezone(timezone.utc)
    elif mode == "draft":
        base_time = None

    plan = PublishPlan(
        content_id=content.id,
        publish_mode=mode,
        status="draft" if mode == "draft" else "scheduled",
        timezone=timezone_value,
        scheduled_at=base_time,
        interval_seconds=interval_seconds,
        flow_revision_id=revision.id,
        content_snapshot_json=snapshot_json,
    )
    db.add(plan)
    db.flush()

    for index, channel_id in enumerate(unique_channel_ids):
        channel = channel_by_id[channel_id]
        job_time = (
            base_time + timedelta(seconds=index * interval_seconds)
            if base_time is not None
            else None
        )
        db.add(
            PublishJob(
                plan_id=plan.id,
                channel_id=channel.id,
                flow_revision_id=revision.id,
                content_id=None,
                profile_id=None,
                platform=channel.platform,
                status="draft" if mode == "draft" else "scheduled",
                stage=None,
                scheduled_at=job_time,
                content_snapshot_json=snapshot_json,
                channel_snapshot_json=json.dumps(channel_snapshot(channel), ensure_ascii=False),
            )
        )

    db.commit()
    return get_publish_plan(db, plan.id)


def get_publish_plan(db: Session, plan_id: str) -> PublishPlan:
    statement = (
        select(PublishPlan)
        .options(
            selectinload(PublishPlan.jobs).selectinload(PublishJob.attempts),
            selectinload(PublishPlan.flow_revision),
        )
        .where(PublishPlan.id == plan_id)
    )
    plan = db.scalar(statement)
    if plan is None:
        raise ValueError("Publish plan not found.")
    return plan
