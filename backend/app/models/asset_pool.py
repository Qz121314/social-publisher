from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Asset(Base):
    """Editable source resource in the product-level asset pool.

    Assets are preparation resources only. Creating an Asset never creates a
    PublishJob. Future ContentPackage records may compose these assets and a
    publish task will freeze immutable snapshots at task creation time.
    """

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), default="generic", nullable=False, index=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    original_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    stored_name: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    mime_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="ready", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
