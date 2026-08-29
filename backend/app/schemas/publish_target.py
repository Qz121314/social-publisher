from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PublishTargetCaptureRequest(BaseModel):
    target_type: Literal["profile", "page"]


class PublishTargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    platform: str
    target_type: str
    target_id: str
    target_name: str
    target_url: str
    created_at: datetime
    updated_at: datetime


class PublishTargetCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    platform: str
    target_type: str
    target_id: str
    target_name: str
    target_url: str
    source: str
    is_available: bool
    created_at: datetime
    last_seen_at: datetime


class PublishTargetConfirmationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    platform: str
    target_id: str
    actor_id: str
    entry_signature_json: str
    confirmed_at: datetime
    updated_at: datetime


class FacebookPageScanRead(BaseModel):
    profile_id: int
    count: int
    items: list[PublishTargetCandidateRead]
