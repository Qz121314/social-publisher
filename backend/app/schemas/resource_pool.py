from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProxyEndpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    protocol: str
    host: str
    port: int
    label: str | None = None
    username_configured: bool
    password_configured: bool
    enabled: bool
    status: str
    exit_ip: str | None = None
    country: str | None = None
    region: str | None = None
    latency_ms: int | None = None
    last_checked_at: datetime | None = None
    assigned_count: int = 0
    created_at: datetime
    updated_at: datetime


class ProxyImportText(BaseModel):
    text: str = Field(min_length=1, max_length=2_000_000)


class ProxyBatchDelete(BaseModel):
    proxy_ids: list[int] = Field(min_length=1, max_length=1000)


class ProxyHealthCheckRequest(BaseModel):
    proxy_ids: list[int] = Field(min_length=1, max_length=200)

    @field_validator("proxy_ids")
    @classmethod
    def unique_proxy_ids(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(value))


class AccountPoolImportText(BaseModel):
    """CSV import payload for account-pool preparation.

    The CSV itself is parsed server-side so Cookie JSON remains correctly quoted
    and the browser UI does not duplicate secret validation rules.
    """

    text: str = Field(min_length=1, max_length=20_000_000)


class AccountBatchProxyAssign(BaseModel):
    account_ids: list[int] = Field(min_length=1, max_length=1000)
    replace_existing: bool = False

    @field_validator("account_ids")
    @classmethod
    def unique_ids(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(value))
