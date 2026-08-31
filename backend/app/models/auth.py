from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AccountAuthConfig(Base):
    """Non-secret login configuration for a social account.

    Passwords, TOTP secrets and cookie payloads are never stored in SQLite.
    SQLite stores only safe metadata and presence flags; the encrypted values
    live in the local CredentialVault.
    """

    __tablename__ = "account_auth_configs"

    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    login_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    allow_cookie_restore: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_password_login: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_totp: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    cookie_configured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    password_configured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_configured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    cookie_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cookie_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    totp_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )
