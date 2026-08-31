from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BatchLoginCreate(BaseModel):
    group_id: int | None = Field(default=None, ge=1)
    account_ids: list[int] | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_target(self):
        if (self.group_id is None) == (self.account_ids is None):
            raise ValueError("必须选择一个账号分组，或提交明确的账号列表。")
        return self


class TaskJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    batch_id: str
    account_id: int | None
    job_type: str
    status: str
    stage: str
    account_snapshot_json: str
    profile_id: int | None
    result_json: str | None
    error_message: str | None
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class BatchTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_type: str
    source_type: Literal["group", "selection"] | str
    source_selection_json: str
    target_snapshot_json: str
    status: str
    total_jobs: int
    succeeded_jobs: int
    attention_jobs: int
    failed_jobs: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    jobs: list[TaskJobRead] = []
