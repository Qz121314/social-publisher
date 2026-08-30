from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: int
    platform: str
    target_id: str
    target_name: str
    target_type: str
    target_url: str
    enabled: bool
    health_status: str
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FlowStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sort_order: int
    action_type: str
    name: str
    config_json: str
    enabled: bool


class FlowRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: int
    label: str
    status: str
    notes: str | None
    published_at: datetime | None
    steps: list[FlowStepRead]


class FlowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform: str
    key: str
    name: str
    enabled: bool
    current_revision_id: str | None
    revisions: list[FlowRevisionRead]


class AssetCreate(BaseModel):
    platform: str = "facebook"
    text: str = ""


class PublishPlanCreate(BaseModel):
    content_id: str
    channel_ids: list[str] = Field(min_length=1, max_length=200)
    publish_mode: str = "draft"
    timezone: str = "UTC"
    scheduled_at: datetime | None = None
    interval_seconds: int = Field(default=0, ge=0, le=86400)
    flow_revision_id: str | None = None


class PublishAttemptEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    attempt_id: str
    sequence: int
    stage: str
    message: str
    details_json: str | None
    created_at: datetime


class PublishAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    worker_task_id: str | None
    attempt_no: int
    status: str
    stage: str | None
    started_at: datetime | None
    submitted_at: datetime | None
    finished_at: datetime | None
    browser_open_ms: int | None
    platform_ms: int | None
    media_ms: int | None
    verification_ms: int | None
    total_ms: int | None
    result_json: str | None
    error_message: str | None
    created_at: datetime
    events: list[PublishAttemptEventRead]


class DomainPublishJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    plan_id: str | None
    channel_id: str | None
    flow_revision_id: str | None
    platform: str
    status: str
    stage: str | None
    scheduled_at: datetime | None
    content_snapshot_json: str
    channel_snapshot_json: str
    worker_task_id: str | None
    published_url: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    attempts: list[PublishAttemptRead]


class PublishPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    content_id: str
    publish_mode: str
    status: str
    timezone: str
    scheduled_at: datetime | None
    interval_seconds: int
    flow_revision_id: str
    content_snapshot_json: str
    created_at: datetime
    updated_at: datetime
    jobs: list[DomainPublishJobRead]
