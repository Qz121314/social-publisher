# Phase 2 — V1 Domain Model

Phase 2 converts the Phase 1 product shell into a stable backend domain model while keeping the verified Facebook PoC path runnable.

## Canonical V1 graph

```text
BrowserProfile → Channel

ContentItem (Asset)

Flow → FlowRevision → FlowStep

PublishPlan → PublishJob → PublishAttempt
```

## Compatibility boundary

The existing `Account`, `PublishTarget`, `/contents/{id}/run`, `WorkerTask`, Profile Lock and Facebook adapter remain available during Phase 2. They are compatibility infrastructure, not the final V1 product model.

- Existing `PublishTarget` rows are backfilled into `Channel` on startup.
- Matching `Account.enabled/status` values are folded into Channel state.
- Existing PoC `PublishJob` rows are preserved.
- The old `UNIQUE(content_id, profile_id)` restriction is removed during the SQLite migration.
- Formal PublishPlan jobs use `plan_id + channel_id + snapshots`; `content_id/profile_id` are nullable compatibility fields.
- Formal jobs are not yet sent through the legacy Worker path. That execution migration belongs to Phase 3/4.

## Snapshot rules

Creating a PublishPlan freezes:

- content text and media metadata;
- channel/profile/target identity;
- `flow_revision_id`;
- per-job `scheduled_at` after applying the requested interval.

A scheduled local time is normalized to UTC while the requested IANA timezone is retained on the plan.

## Seeded Facebook flow

Startup creates the baseline `Facebook 普通帖子` flow when missing. Revision `v1.0 PoC baseline` contains only the constrained V1 action types and maps the already verified PoC sequence, including the `actor_id == target_id` gates.

## Phase 2 API surface

```text
GET  /api/domain/status
GET  /api/assets
POST /api/assets
GET  /api/channels
GET  /api/flows
GET  /api/publish-plans
POST /api/publish-plans
GET  /api/publish-plans/{plan_id}
GET  /api/publish-attempts
```

The scheduler is intentionally not started here. SQLite is now ready to become its source of truth in Phase 4.
