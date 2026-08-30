from __future__ import annotations

import json

from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.channel import Channel
from app.models.flow import Flow, FlowRevision, FlowStep, utcnow
from app.models.publish_target import PublishTarget


_PUBLISH_JOB_COLUMNS: tuple[tuple[str, str], ...] = (
    ("plan_id", "VARCHAR(36)"),
    ("channel_id", "VARCHAR(36)"),
    ("flow_revision_id", "VARCHAR(36)"),
    ("content_snapshot_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("channel_snapshot_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("stage", "VARCHAR(50)"),
)


def ensure_phase2_schema(engine: Engine) -> bool:
    """Upgrade the Phase 1 publish_jobs table without losing local task history."""
    inspector = inspect(engine)
    if "publish_jobs" not in inspector.get_table_names():
        return False

    columns = {column["name"]: column for column in inspector.get_columns("publish_jobs")}
    table_sql = _table_sql(engine, "publish_jobs").lower()
    needs_rebuild = (
        not columns.get("content_id", {}).get("nullable", True)
        or not columns.get("profile_id", {}).get("nullable", True)
        or "uq_publish_job_content_profile" in table_sql
        or "unique (content_id, profile_id)" in table_sql
    )

    if needs_rebuild:
        _rebuild_publish_jobs(engine, set(columns))
        return True

    with engine.begin() as connection:
        for name, definition in _PUBLISH_JOB_COLUMNS:
            if name not in columns:
                connection.exec_driver_sql(
                    f'ALTER TABLE publish_jobs ADD COLUMN "{name}" {definition}'
                )
        _create_publish_job_indexes(connection)
    return False


def _table_sql(engine: Engine, table_name: str) -> str:
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).first()
    return str(row[0] or "") if row else ""


def _rebuild_publish_jobs(engine: Engine, existing_columns: set[str]) -> None:
    raw = engine.raw_connection()
    cursor = raw.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("DROP TABLE IF EXISTS publish_attempts")
        cursor.execute("ALTER TABLE publish_jobs RENAME TO publish_jobs_phase1_legacy")
        cursor.execute(
            """
            CREATE TABLE publish_jobs (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                plan_id VARCHAR(36) REFERENCES publish_plans(id) ON DELETE CASCADE,
                channel_id VARCHAR(36) REFERENCES channels(id) ON DELETE RESTRICT,
                flow_revision_id VARCHAR(36) REFERENCES flow_revisions(id) ON DELETE RESTRICT,
                content_snapshot_json TEXT NOT NULL DEFAULT '{}',
                channel_snapshot_json TEXT NOT NULL DEFAULT '{}',
                content_id VARCHAR(36) REFERENCES contents(id) ON DELETE CASCADE,
                profile_id INTEGER REFERENCES browser_profiles(profile_id) ON DELETE RESTRICT,
                platform VARCHAR(50) NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'draft',
                stage VARCHAR(50),
                scheduled_at DATETIME,
                worker_task_id VARCHAR(36),
                published_url TEXT,
                error_message TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )

        target_columns = [
            "id",
            "plan_id",
            "channel_id",
            "flow_revision_id",
            "content_snapshot_json",
            "channel_snapshot_json",
            "content_id",
            "profile_id",
            "platform",
            "status",
            "stage",
            "scheduled_at",
            "worker_task_id",
            "published_url",
            "error_message",
            "created_at",
            "updated_at",
        ]
        fallbacks = {
            "plan_id": "NULL",
            "channel_id": "NULL",
            "flow_revision_id": "NULL",
            "content_snapshot_json": "'{}'",
            "channel_snapshot_json": "'{}'",
            "stage": "NULL",
        }
        select_parts = [
            name if name in existing_columns else fallbacks[name]
            for name in target_columns
        ]
        cursor.execute(
            f"INSERT INTO publish_jobs ({', '.join(target_columns)}) "
            f"SELECT {', '.join(select_parts)} FROM publish_jobs_phase1_legacy"
        )
        cursor.execute("DROP TABLE publish_jobs_phase1_legacy")
        _create_publish_job_indexes(cursor)
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        raw.close()


def _create_publish_job_indexes(connection) -> None:
    statements = (
        "CREATE INDEX IF NOT EXISTS ix_publish_jobs_plan_id ON publish_jobs (plan_id)",
        "CREATE INDEX IF NOT EXISTS ix_publish_jobs_channel_id ON publish_jobs (channel_id)",
        "CREATE INDEX IF NOT EXISTS ix_publish_jobs_flow_revision_id ON publish_jobs (flow_revision_id)",
        "CREATE INDEX IF NOT EXISTS ix_publish_jobs_content_id ON publish_jobs (content_id)",
        "CREATE INDEX IF NOT EXISTS ix_publish_jobs_profile_id ON publish_jobs (profile_id)",
        "CREATE INDEX IF NOT EXISTS ix_publish_jobs_platform ON publish_jobs (platform)",
        "CREATE INDEX IF NOT EXISTS ix_publish_jobs_status ON publish_jobs (status)",
        "CREATE INDEX IF NOT EXISTS ix_publish_jobs_stage ON publish_jobs (stage)",
        "CREATE INDEX IF NOT EXISTS ix_publish_jobs_scheduled_at ON publish_jobs (scheduled_at)",
    )
    for statement in statements:
        if hasattr(connection, "exec_driver_sql"):
            connection.exec_driver_sql(statement)
        else:
            connection.execute(statement)


def bootstrap_phase2_records(db: Session) -> dict[str, int]:
    channels = _backfill_channels(db)
    flows = _ensure_facebook_flow(db)
    db.commit()
    return {"channels_backfilled": channels, "flows_seeded": flows}


def sync_channel_from_target(db: Session, target: PublishTarget) -> Channel:
    """Mirror one configured legacy PublishTarget into the canonical Channel model.

    Phase 3 still uses the proven target scanner/selector UI as the configuration
    mechanism, but every successful selection must immediately become a Channel
    so the formal PublishPlan path never depends on a process restart/bootstrap.
    """
    account = db.scalar(
        select(Account).where(
            Account.ix_profile_id == target.profile_id,
            Account.platform == target.platform,
        )
    )
    enabled = account.enabled if account is not None else True
    health_status = (
        account.status
        if account is not None and account.status not in {"", "unknown"}
        else "unknown"
    )

    channel = db.scalar(
        select(Channel).where(
            Channel.profile_id == target.profile_id,
            Channel.platform == target.platform,
            Channel.target_id == target.target_id,
        )
    )
    if channel is None:
        channel = Channel(
            profile_id=target.profile_id,
            platform=target.platform,
            target_id=target.target_id,
            target_name=target.target_name,
            target_type=target.target_type,
            target_url=target.target_url,
            enabled=enabled,
            health_status=health_status,
            last_checked_at=target.updated_at,
        )
        db.add(channel)
    else:
        channel.target_name = target.target_name
        channel.target_type = target.target_type
        channel.target_url = target.target_url
        channel.enabled = enabled
        if health_status != "unknown":
            channel.health_status = health_status
        channel.last_checked_at = target.updated_at
    return channel


def disable_channel_for_target(db: Session, target: PublishTarget) -> None:
    channel = db.scalar(
        select(Channel).where(
            Channel.profile_id == target.profile_id,
            Channel.platform == target.platform,
            Channel.target_id == target.target_id,
        )
    )
    if channel is None:
        return
    channel.enabled = False
    channel.health_status = "unconfigured"
    channel.last_checked_at = utcnow()


def _backfill_channels(db: Session) -> int:
    targets = list(db.scalars(select(PublishTarget)).all())
    before = int(db.scalar(select(Channel).count()) or 0) if False else None
    created = 0
    for target in targets:
        existing = db.scalar(
            select(Channel).where(
                Channel.profile_id == target.profile_id,
                Channel.platform == target.platform,
                Channel.target_id == target.target_id,
            )
        )
        sync_channel_from_target(db, target)
        if existing is None:
            created += 1
    return created


def _ensure_facebook_flow(db: Session) -> int:
    flow = db.scalar(
        select(Flow).where(Flow.platform == "facebook", Flow.key == "standard_post")
    )
    if flow is not None:
        if flow.current_revision_id is None and flow.revisions:
            flow.current_revision_id = flow.revisions[0].id
        return 0

    flow = Flow(
        platform="facebook",
        key="standard_post",
        name="Facebook 普通帖子",
        enabled=True,
    )
    db.add(flow)
    db.flush()

    revision = FlowRevision(
        flow_id=flow.id,
        version=1,
        label="v1.0 PoC baseline",
        status="published",
        notes="Phase 2 baseline mapped from the verified Facebook PoC sequence.",
        published_at=utcnow(),
    )
    db.add(revision)
    db.flush()

    steps = (
        (10, "CHECK_LOGIN", "检查登录", {}),
        (20, "VERIFY_ACTOR", "校验发布身份", {"gate": "actor_id == target_id"}),
        (30, "NAVIGATE", "打开目标主页", {}),
        (40, "CLICK_TEXT", "打开发帖 Composer", {}),
        (50, "INPUT_TEXT", "输入正文", {"unicode": "cdp_insert_text"}),
        (60, "CLICK_IF_EXISTS", "打开照片/视频入口", {"when": "has_media"}),
        (70, "UPLOAD_MEDIA", "上传媒体", {"when": "has_media"}),
        (80, "WAIT_MEDIA_READY", "等待媒体处理", {"when": "has_media"}),
        (90, "NEXT", "下一页 / 下一步", {"optional": True}),
        (100, "VERIFY_ACTOR", "发布前再次校验身份", {"gate": "actor_id == target_id"}),
        (110, "PUBLISH", "最终发布", {}),
        (120, "VERIFY_RESULT", "验证发布结果", {}),
    )
    for sort_order, action_type, name, config in steps:
        db.add(
            FlowStep(
                revision_id=revision.id,
                sort_order=sort_order,
                action_type=action_type,
                name=name,
                config_json=json.dumps(config, ensure_ascii=False),
                enabled=True,
            )
        )

    flow.current_revision_id = revision.id
    return 1
