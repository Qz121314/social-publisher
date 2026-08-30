from __future__ import annotations

import inspect
from pathlib import Path

from sqlalchemy import UniqueConstraint

from app.models.channel import Channel
from app.models.content import PublishJob
from app.models.publishing import PublishAttempt, PublishPlan
from app.services.platforms.facebook_composite import FacebookCompositeAdapter
from app.services.platforms.registry import get_platform_adapter
from app.services.publishing_domain import create_publish_plan
from app.services.scheduler import PublishScheduler


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = ROOT / "frontend" / "src"


# Facebook remains the V1 release-candidate production adapter.
facebook = get_platform_adapter("facebook")
assert isinstance(facebook, FacebookCompositeAdapter)

# Channel is the product-level publish destination. The compatibility
# PublishTarget tables may still exist for platform discovery, but formal V1
# publishing must be keyed by Channel + immutable snapshots.
channel_columns = set(Channel.__table__.columns.keys())
assert {
    "id",
    "profile_id",
    "platform",
    "target_id",
    "target_name",
    "target_type",
    "target_url",
    "enabled",
    "health_status",
}.issubset(channel_columns)
channel_unique_sets = {
    tuple(column.name for column in constraint.columns)
    for constraint in Channel.__table__.constraints
    if isinstance(constraint, UniqueConstraint)
}
assert ("profile_id", "platform", "target_id") in channel_unique_sets

# Formal plan/job/attempt ownership is present and legacy direct job fields are
# nullable compatibility fields rather than the V1 source of truth.
assert PublishPlan.__table__.c.flow_revision_id.nullable is False
assert PublishPlan.__table__.c.content_snapshot_json.nullable is False
job_columns = set(PublishJob.__table__.columns.keys())
assert {
    "plan_id",
    "channel_id",
    "flow_revision_id",
    "content_snapshot_json",
    "channel_snapshot_json",
}.issubset(job_columns)
assert PublishJob.__table__.c.content_id.nullable is True
assert PublishJob.__table__.c.profile_id.nullable is True
assert PublishAttempt.__table__.c.job_id.nullable is False
assert PublishAttempt.__table__.c.attempt_no.nullable is False

plan_source = inspect.getsource(create_publish_plan)
assert "select(Channel)" in plan_source
assert "content_id=None" in plan_source
assert "profile_id=None" in plan_source
assert "content_snapshot_json=snapshot_json" in plan_source
assert "channel_snapshot_json=json.dumps(channel_snapshot(channel)" in plan_source

# Scheduler only discovers formal Plan jobs from SQLite and reserves an iX
# profile for the rest of the dispatch tick, preventing same-profile overlap.
scheduler_source = inspect.getsource(PublishScheduler.run_once)
assert "PublishJob.plan_id.is_not(None)" in scheduler_source
assert 'PublishJob.status == "scheduled"' in scheduler_source
assert "busy_profile_ids.add(profile_id)" in scheduler_source

# The product shell must be the routed 8-center V1 application, not the old
# anchor-based PoC shell.
main_tsx = (FRONTEND_SRC / "main.tsx").read_text(encoding="utf-8")
router_tsx = (FRONTEND_SRC / "app" / "router.tsx").read_text(encoding="utf-8")
assert "AppRouter" in main_tsx
for legacy_import in ("./App", "./ContentComposer", "./AdminSidebar"):
    assert legacy_import not in main_tsx
for route in (
    'path="assets"',
    'path="accounts"',
    'path="flows"',
    'path="publish"',
    'path="plans"',
    'path="tasks"',
    'path="settings"',
):
    assert route in router_tsx

# These files belonged only to the disconnected PoC shell and must not return.
for legacy_path in (
    FRONTEND_SRC / "App.tsx",
    FRONTEND_SRC / "ContentComposer.tsx",
    FRONTEND_SRC / "AdminSidebar.tsx",
):
    assert not legacy_path.exists(), f"legacy PoC file still present: {legacy_path.name}"

print("phase9 facebook v1 release-candidate architecture ok")
