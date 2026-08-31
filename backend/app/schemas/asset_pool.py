from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    asset_type: str
    platform: str
    text_content: str | None
    original_name: str | None
    mime_type: str | None
    file_size: int | None
    status: str
    created_at: datetime
    updated_at: datetime


class TextAssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=200_000)
    platform: str = Field(default="generic", max_length=50)

    @field_validator("name", "text")
    @classmethod
    def strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("内容不能为空。")
        return normalized

    @field_validator("platform")
    @classmethod
    def normalize_platform(cls, value: str) -> str:
        normalized = value.strip().lower() or "generic"
        if normalized not in {"generic", "facebook", "instagram"}:
            raise ValueError("素材平台只能是通用、Facebook 或 Instagram。")
        return normalized


class TextAssetImport(BaseModel):
    text: str = Field(min_length=1, max_length=20_000_000)


class AssetBatchDelete(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=1000)
