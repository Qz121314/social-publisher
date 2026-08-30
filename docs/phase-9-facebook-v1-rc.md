# Phase 9 — Facebook V1 Release Candidate

Phase 9 freezes new platform expansion and closes the Facebook V1 product path before further Instagram / Threads / X work.

## Release-candidate scope

The V1 Facebook product path is:

```text
Asset
  -> Channel
  -> PublishPlan
  -> PublishJob
  -> SQLite Scheduler
  -> bounded Worker Pool
  -> Profile Lock
  -> Browser Session Pool
  -> iXBrowser
  -> FacebookCompositeAdapter
  -> PublishAttempt / Timeline
```

Product-level source-of-truth rules:

- `Channel` is the publish destination used by new V1 plans.
- `PublishPlan` stores the user publish intent and freezes the flow revision and content snapshot.
- Each selected Channel creates one independent `PublishJob` with a channel snapshot.
- `PublishAttempt` records each real execution and its stage/timing/result.
- `PublishTarget` remains a compatibility/discovery object for current Facebook/Instagram channel capture. New V1 publishing must not schedule directly from it.
- `WorkerTask` remains runtime infrastructure and is not the product-level task model.

## Automatic RC gates

`backend/validate_phase9.py` checks that:

- the production Facebook adapter is the direct composite adapter;
- Channel identity uses `profile_id + platform + target_id`;
- formal jobs carry Plan/Channel/FlowRevision plus immutable snapshots;
- legacy `content_id/profile_id` job fields are nullable compatibility fields;
- the SQLite Scheduler only discovers formal Plan jobs;
- the Scheduler reserves a profile during a dispatch tick to prevent same-profile overlap;
- the frontend entry uses the routed V1 shell;
- all eight V1 centers remain registered;
- the disconnected anchor-based PoC shell files are absent.

CI must run this validator together with Phases 3–8 and the frontend TypeScript/Vite build.

## Facebook live acceptance checklist

These checks require the user's local Windows + iXBrowser environment and cannot be truthfully simulated by GitHub Actions.

### Single target

- [ ] Personal profile — text only
- [ ] Personal profile — text + image
- [ ] Personal profile — text + video
- [ ] Public Page — text only
- [ ] Public Page — text + image
- [ ] Public Page — text + video
- [ ] Emoji / non-BMP Unicode input

### Batch and scheduling

- [ ] Select an entire iX group
- [ ] Multi-Channel immediate publish
- [ ] Multi-Channel scheduled publish
- [ ] Configured interval is reflected in per-Job `scheduled_at`
- [ ] Same iX profile never runs two publishing jobs concurrently
- [ ] Different iX profiles can use the bounded Worker Pool concurrently
- [ ] Warm browser session is reused within TTL
- [ ] Idle warm session expires cleanly

### Recovery and safety

- [ ] Backend restart preserves scheduled jobs from SQLite
- [ ] Pre-submit failure becomes `failed`
- [ ] Uncertain post-submit state becomes `needs_review`
- [ ] `needs_review` is never automatically retried
- [ ] “Confirm published” closes the job as success
- [ ] “Confirm not published and retry” creates a safe new attempt
- [ ] Disabled Channel blocks dispatch without mutating the frozen snapshot
- [ ] CAPTCHA / Checkpoint / login challenge is handed to manual handling, never bypassed

## Phase 9 exit criteria

Phase 9 can be tagged as Facebook V1 stable only after both conditions are true:

1. GitHub CI passes all automatic RC gates.
2. The local Facebook live acceptance checklist above has been completed against the actual iXBrowser profiles used for production.

Instagram Phase 8A remains experimental during this freeze. No additional platform capability should be added until the Facebook RC is accepted.
