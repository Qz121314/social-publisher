from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PublishPlan(Base):
    __tablename__ = "publish_plans"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    content_id: Mapped[str] = mapped_column(
        ForeignKey("contents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    publish_mode: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), default="draft", nullable=False, index=True
    )
    timezone: Mapped[str] = mapped_column(String(80), default="UTC", nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    interval_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flow_revision_id: Mapped[str] = mapped_column(
        ForeignKey("flow_revisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    content_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    content: Mapped["ContentItem"] = relationship(back_populates="plans")
    flow_revision: Mapped["FlowRevision"] = relationship()
    jobs: Mapped[list["PublishJob"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="PublishJob.scheduled_at",
    )


class PublishAttempt(Base):
    __tablename__ = "publish_attempts"
    __table_args__ = (
        UniqueConstraint("job_id", "attempt_no", name="uq_publish_attempt_job_number"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("publish_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    worker_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    stage: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    browser_open_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    platform_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    job: Mapped["PublishJob"] = relationship(back_populates="attempts")
    events: Mapped[list["PublishAttemptEvent"]] = relationship(
        back_populates="attempt",
        cascade="all, delete-orphan",
        order_by="PublishAttemptEvent.sequence",
    )


class PublishAttemptEvent(Base):
    """Immutable execution event used to build the user-facing task Timeline."""

    __tablename__ = "publish_attempt_events"
    __table_args__ = (
        UniqueConstraint("attempt_id", "sequence", name="uq_attempt_event_sequence"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("publish_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    attempt: Mapped[PublishAttempt] = relationship(back_populates="events")
