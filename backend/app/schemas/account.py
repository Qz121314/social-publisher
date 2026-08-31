from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.resource_pool import ProxyEndpointRead

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
    proxy_type: str | None = None
    proxy_ip: str | None = None
    proxy_port: str | None = None
    real_ip: str | None = None
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
    ix_profile_id: int | None = None
    group_id: int | None = None
    proxy_id: int | None = None
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


class AccountProxyCreate(BaseModel):
    enabled: bool = False
    proxy_type: Literal["socks5"] = "socks5"
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def validate_enabled_proxy(self):
        if not self.enabled:
            return self
        if not (self.host or "").strip():
            raise ValueError("启用 SOCKS5 后必须填写 Host。")
        if self.port is None:
            raise ValueError("启用 SOCKS5 后必须填写 Port。")
        return self


class AccountOnboardCreate(BaseModel):
    """Compatibility path for manually creating one account + environment.

    The Phase 10 primary path is now bulk resource preparation; this endpoint is
    retained as an advanced/manual import path.
    """

    name: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=50)
    group_id: int | None = None
    environment_mode: Literal["new", "existing"] = "new"
    ix_profile_id: int | None = None
    profile_name: str | None = Field(default=None, max_length=255)
    proxy: AccountProxyCreate = Field(default_factory=AccountProxyCreate)
    open_after_create: bool = True

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

    @model_validator(mode="after")
    def validate_environment(self):
        if self.environment_mode == "existing":
            if self.ix_profile_id is None:
                raise ValueError("绑定已有环境时必须选择 iX Profile。")
            if self.proxy.enabled:
                raise ValueError("已有环境的 SOCKS5 请在浏览器环境中修改，不在绑定账号时覆盖。")
        else:
            if self.ix_profile_id is not None:
                raise ValueError("新建环境时不应提交已有 iX Profile ID。")
        return self


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    platform: str | None = Field(default=None, min_length=1, max_length=50)
    ix_profile_id: int | None = None
    group_id: int | None = None
    proxy_id: int | None = None
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
    ix_profile_id: int | None
    group_id: int | None
    proxy_id: int | None
    enabled: bool
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
    browser_profile: BrowserProfileRead | None = None
    group: AccountGroupRead | None = None
    proxy_endpoint: ProxyEndpointRead | None = None


class AccountOnboardRead(BaseModel):
    account: AccountRead
    profile_created: bool
    opened: bool
    open_error: str | None = None


class AccountBatchMove(BaseModel):
    account_ids: list[int] = Field(min_length=1, max_length=1000)
    group_id: int | None = None
