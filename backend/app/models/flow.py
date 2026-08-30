from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


FLOW_ACTION_TYPES = (
    "CHECK_LOGIN",
    "VERIFY_ACTOR",
    "NAVIGATE",
    "CLICK_TEXT",
    "CLICK_IF_EXISTS",
    "INPUT_TEXT",
    "UPLOAD_MEDIA",
    "WAIT_ELEMENT",
    "WAIT_TEXT",
    "WAIT_MEDIA_READY",
    "NEXT",
    "PUBLISH",
    "VERIFY_RESULT",
)


class Flow(Base):
    __tablename__ = "flows"
    __table_args__ = (
        UniqueConstraint("platform", "key", name="uq_flow_platform_key"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    current_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("flow_revisions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    revisions: Mapped[list["FlowRevision"]] = relationship(
        back_populates="flow",
        foreign_keys="FlowRevision.flow_id",
        cascade="all, delete-orphan",
        order_by="FlowRevision.version.desc()",
    )
    current_revision: Mapped["FlowRevision | None"] = relationship(
        foreign_keys=[current_revision_id],
        post_update=True,
    )


class FlowRevision(Base):
    __tablename__ = "flow_revisions"
    __table_args__ = (
        UniqueConstraint("flow_id", "version", name="uq_flow_revision_version"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    flow_id: Mapped[str] = mapped_column(
        ForeignKey("flows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="draft", nullable=False, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    flow: Mapped[Flow] = relationship(
        back_populates="revisions",
        foreign_keys=[flow_id],
    )
    steps: Mapped[list["FlowStep"]] = relationship(
        back_populates="revision",
        cascade="all, delete-orphan",
        order_by="FlowStep.sort_order",
    )
    jobs: Mapped[list["PublishJob"]] = relationship(back_populates="flow_revision")


class FlowStep(Base):
    __tablename__ = "flow_steps"
    __table_args__ = (
        UniqueConstraint("revision_id", "sort_order", name="uq_flow_step_order"),
        CheckConstraint(
            "action_type IN (" + ", ".join(repr(value) for value in FLOW_ACTION_TYPES) + ")",
            name="ck_flow_step_action_type",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    revision_id: Mapped[str] = mapped_column(
        ForeignKey("flow_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    revision: Mapped[FlowRevision] = relationship(back_populates="steps")
