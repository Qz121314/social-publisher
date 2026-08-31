# Phase 10 — Account Groups Implementation V1

This increment turns the account-group design baseline into a working product slice.

Implemented:

- `AccountGroup` persistence independent from iXBrowser Profile groups.
- Existing SQLite databases gain nullable `accounts.group_id` through a narrow startup migration.
- Existing accounts remain in the virtual `未分组` bucket.
- Account-group create, rename/update and delete-empty-only behavior.
- Batch move accounts between groups or back to `未分组`.
- Account create API can assign a group while preserving the stable account ↔ iX Profile binding.
- New React route: `/prepare/accounts`.
- Left group rail + right account list workspace.
- Add account, new/edit group and batch move interactions.
- Existing Facebook / Instagram identity discovery tools remain available under an Advanced section instead of occupying the primary account workflow.
- Legacy `/accounts` route redirects to `/prepare/accounts`; the migrated legacy page file is removed.

Not implemented in this increment:

- Credential Vault / DPAPI.
- Cookie Session storage.
- Login State Machine / session recovery.
- Built-in TOTP.
- Account-level lock.
- Default publish Channel selection.
- Group-to-task TargetResolver / frozen target snapshots.

The next increment should build the credential/session boundary and login-state read model on top of this account/group structure rather than adding another account-selection UI.
