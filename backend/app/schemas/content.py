from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MediaAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    media_type: str
    original_name: str
    mime_type: str
    file_size: int
    sort_order: int
    created_at: datetime


class PublishJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: int | None
    plan_id: str | None
    channel_id: str | None
    flow_revision_id: str | None
    platform: str
    status: str
    stage: str | None
    scheduled_at: datetime | None
    worker_task_id: str | None
    published_url: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ContentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform: str
    text: str
    status: str
    media: list[MediaAssetRead]
    jobs: list[PublishJobRead]
    created_at: datetime
    updated_at: datetime
