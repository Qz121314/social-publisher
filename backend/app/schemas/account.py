from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

SUPPORTED_PLATFORMS = {
    "facebook",
    "instagram",
    "x",
    "tiktok",
    "threads",
    "linkedin",
    "youtube",
    "pinterest",
    "other",
}


class BrowserProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    profile_id: int
    name: str
    group_id: int | None = None
    group_name: str | None = None
    is_available: bool
    last_seen_at: datetime


class AccountGroupBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    sort_order: int = 0
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("group name cannot be empty")
        return value


class AccountGroupCreate(AccountGroupBase):
    pass


class AccountGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    sort_order: int | None = None
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("group name cannot be empty")
        return value


class AccountGroupRead(AccountGroupBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_count: int = 0
    created_at: datetime
    updated_at: datetime


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=50)
    ix_profile_id: int
    group_id: int | None = None
    enabled: bool = True
    notes: str | None = None

    @field_validator("platform")
    @classmethod
    def normalize_platform(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in SUPPORTED_PLATFORMS:
            raise ValueError(f"unsupported platform: {value}")
        return value

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    platform: str | None = Field(default=None, min_length=1, max_length=50)
    ix_profile_id: int | None = None
    group_id: int | None = None
    enabled: bool | None = None
    status: str | None = Field(default=None, max_length=50)
    notes: str | None = None

    @field_validator("platform")
    @classmethod
    def normalize_platform(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if value not in SUPPORTED_PLATFORMS:
            raise ValueError(f"unsupported platform: {value}")
        return value

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    platform: str
    ix_profile_id: int
    group_id: int | None
    enabled: bool
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
    browser_profile: BrowserProfileRead
    group: AccountGroupRead | None = None


class AccountBatchMove(BaseModel):
    account_ids: list[int] = Field(min_length=1, max_length=500)
    group_id: int | None = None
