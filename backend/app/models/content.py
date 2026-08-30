from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContentItem(Base):
    __tablename__ = "contents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="draft", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    media: Mapped[list["MediaAsset"]] = relationship(
        back_populates="content",
        cascade="all, delete-orphan",
        order_by="MediaAsset.sort_order",
    )
    # Compatibility relation for the existing PoC path. Formal V1 PublishPlan jobs
    # use plan_id/channel_id snapshots and intentionally leave content_id NULL.
    jobs: Mapped[list["PublishJob"]] = relationship(
        back_populates="content",
        cascade="all, delete-orphan",
        order_by="PublishJob.created_at",
    )
    plans: Mapped[list["PublishPlan"]] = relationship(back_populates="content")


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    content_id: Mapped[str] = mapped_column(
        ForeignKey("contents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    content: Mapped[ContentItem] = relationship(back_populates="media")


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    # Formal V1 ownership. A job belongs to one immutable plan/channel snapshot.
    plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("publish_plans.id", ondelete="CASCADE"), nullable=True, index=True
    )
    channel_id: Mapped[str | None] = mapped_column(
        ForeignKey("channels.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    flow_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("flow_revisions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    content_snapshot_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    channel_snapshot_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    # Legacy compatibility fields retained until the PoC worker is migrated in
    # Phase 3. Formal plan jobs intentionally leave content_id/profile_id NULL.
    content_id: Mapped[str | None] = mapped_column(
        ForeignKey("contents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("browser_profiles.profile_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), default="draft", nullable=False, index=True
    )
    stage: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    worker_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    published_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    content: Mapped[ContentItem | None] = relationship(back_populates="jobs")
    plan: Mapped["PublishPlan | None"] = relationship(back_populates="jobs")
    channel: Mapped["Channel | None"] = relationship(back_populates="jobs")
    flow_revision: Mapped["FlowRevision | None"] = relationship(back_populates="jobs")
    attempts: Mapped[list["PublishAttempt"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="PublishAttempt.attempt_no",
    )
