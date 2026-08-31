from datetime import datetime

from pydantic import BaseModel, Field


class AccountAuthUpdate(BaseModel):
    login_identifier: str | None = Field(default=None, max_length=255)
    allow_cookie_restore: bool | None = None
    allow_password_login: bool | None = None
    allow_totp: bool | None = None

    password: str | None = Field(default=None, min_length=1, max_length=4096)
    totp_secret: str | None = Field(default=None, min_length=1, max_length=512)
    cookie_json: str | None = Field(default=None, min_length=2, max_length=524288)

    clear_password: bool = False
    clear_totp: bool = False
    clear_cookies: bool = False


class AccountAuthRead(BaseModel):
    account_id: int
    login_identifier: str | None
    allow_cookie_restore: bool
    allow_password_login: bool
    allow_totp: bool

    password_configured: bool
    totp_configured: bool
    cookie_configured: bool
    cookie_count: int

    password_updated_at: datetime | None
    totp_updated_at: datetime | None
    cookie_updated_at: datetime | None
    updated_at: datetime | None

    vault_supported: bool
    vault_backend: str
    login_plan: list[str]
