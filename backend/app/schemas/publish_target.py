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
