# Phase 10 — Account Groups & Batch Task Architecture V1

Status: design baseline

This document defines how Social Publisher Desktop manages social-account groups and uses those groups as first-class batch-task targets. The product rule is simple:

> 用户先组织账号，再按分组创建任务；任务创建时解析并冻结具体目标，运行时不再动态读取分组成员。

This extends the Phase 10 product loop: Prepare → Publish → Run → Inspect.

---

## 1. Core principles

1. **Account Group is a first-class business object**, not only a UI filter.
2. **iXBrowser Group and Account Group are independent.** iX groups organize browser environments; account groups organize business/social accounts.
3. One social account has one **primary AccountGroup** in V1. Multi-dimensional organization is handled later by tags, not nested groups.
4. Batch-task creation may select one or multiple AccountGroups.
5. Group membership is dynamic only while editing a task. When a task is created/scheduled, the selected groups are resolved into immutable target snapshots.
6. No task silently expands because a group changes after task creation.
7. No unavailable target is silently discarded. Preflight must report eligible, blocked and needs-attention targets.
8. Same iX Profile is serialized by ProfileLock. Different profiles may run concurrently within the bounded Worker Pool.
9. Login and publishing operate on the real iXBrowser profile/window. React is the control plane, not a replacement browser.
10. 2FA, checkpoint and unknown security challenges become Waiting for User / Needs Review states; they are not bypassed.

---

## 2. Domain boundaries

```text
AccountGroup
    ↓
SocialAccount (current Account domain)
    ↓
BrowserProfile (iX environment)
    ↓
SocialIdentity / Channel
    ↓
Task Target Resolver
    ↓
Frozen Target Snapshot
    ↓
PublishPlan / OperationBatch
    ↓
Jobs
    ↓
ProfileLock + Worker Pool + iXBrowser
```

### iX group vs account group

```text
iXBrowser Group
├─ 美国环境
├─ 加拿大环境
└─ 测试环境

Account Group
├─ Store A
├─ Store B
├─ US Facebook
├─ 主力账号
└─ 备用账号
```

Never infer an AccountGroup from the iXBrowser group automatically.

---

## 3. AccountGroup model

Recommended V1 model:

```text
AccountGroup
├─ id
├─ name
├─ description / note
├─ sort_order
├─ enabled
├─ created_at
└─ updated_at
```

`Account` gains:

```text
group_id: nullable FK -> AccountGroup
```

Optional but recommended before group publishing:

```text
default_channel_id: nullable FK -> Channel
```

This prevents a Facebook account with Personal + multiple Pages from accidentally publishing to every discovered Channel when the user selects a group.

### Virtual group

`未分组` is a virtual group, not a real database row.

### Delete rule

A non-empty group cannot be deleted directly. User must first:

- move members to another group, or
- move members to 未分组.

This avoids destructive cascade behavior.

### Tags

Tags are a later many-to-many layer:

```text
AccountTag
AccountTagMembership
```

V1 should not implement nested groups, inherited groups, automatic rules or group permissions.

---

## 4. Social Account workspace

Route concept:

```text
准备 / 社交账号
```

Desktop layout:

```text
社交账号                                      [导入账号] [新建分组]

┌───────────────┬──────────────────────────────────────────────────────┐
│ 分组          │ 搜索账号...        [平台] [登录状态] [更多筛选]      │
│               │                                                      │
│ 全部账号  126 │ ☐ 账号        平台   环境      登录       默认身份   │
│ 未分组     8  │ ☐ John        FB     iX #017   已登录     John       │
│ Store A   38  │ ☐ Shop 01     FB     iX #021   需要2FA    Page A     │
│ Store B   24  │ ☐ Brand 02    IG     iX #033   未检查     @brand02   │
│ US        41  │                                                      │
│ 备用      15  │ 3 selected: [移动分组] [检查登录] [登录] [更多]     │
│               │                                                      │
│ + 新建分组    │                                                      │
└───────────────┴──────────────────────────────────────────────────────┘
```

### Group detail

Selecting Store A shows:

```text
Store A                                      38 accounts

已登录 31   需要2FA 3   未登录 2   异常 2

[批量检查] [批量登录] [打开浏览器工作区] [创建发布]

最近任务
- Store A · 登录检查 · 38 targets · 36 success · 2 waiting
- Store A · Facebook 发布 · 36 targets · 35 published · 1 review
```

Group is therefore both an organization unit and an operation entry point.

---

## 5. Unified task-target selector

All batch-capable workflows should reuse one selection interaction instead of inventing a new selector per page.

```text
选择目标

方式
● 分组
○ 单独选择账号

分组
☑ Store A     38
☑ Store B     24
☐ US          41

已解析
62 accounts
57 ready
3 need attention
2 blocked

[查看目标明细]
```

### Supported selection modes

V1:

- one AccountGroup
- multiple AccountGroups
- explicit individual accounts
- groups + explicit exclusions

Later:

- tags
- saved TargetSet

### Deduplication

If the same account is selected through multiple inputs, it resolves once.

If a task is profile-scoped (IP check/open profile), multiple accounts using the same profile resolve to one Profile target.

---

## 6. TaskTargetResolver

The selected group is not the execution target itself. Resolution depends on task type.

```text
TaskTargetResolver
├─ LOGIN             Group -> Accounts
├─ CHECK_LOGIN       Group -> Accounts
├─ CHECK_IP          Group -> unique BrowserProfiles
├─ OPEN_PROFILE      Group -> unique BrowserProfiles
├─ HEALTH_CHECK      Group -> Accounts + Profiles + Channels as required
└─ PUBLISH           Group -> default/explicit Channels
```

### Publish resolution safety

Publishing must never interpret "group" as "all discovered identities".

Default rule:

```text
AccountGroup
    ↓
Accounts
    ↓
default_channel_id
    ↓
Channels
```

If an account has no valid default Channel, it is `blocked` in preflight and shown to the user.

Advanced future option:

- publish to explicit selected Channels
- select a saved TargetSet

But there is no implicit "publish to every Page found in this profile" behavior.

---

## 7. Frozen target snapshot

This is mandatory.

Example:

```text
08/31  Store A = A1, A2, A3
08/31  create task scheduled for 09/01 09:00
08/31  add A4 to Store A
09/01  task still executes A1, A2, A3 only
```

Store two things:

```text
source_selection_json
- selected group ids
- manually included/excluded ids
- selection mode

resolved_targets_snapshot_json
- concrete account ids
- concrete profile ids
- concrete channel ids when applicable
- display names at creation time
- readiness result at creation time
```

The source selection is for audit/explanation. The resolved snapshot is the source of truth for execution.

For publishing, continue using the existing PublishPlan → PublishJob architecture and frozen content snapshot. Do not replace PublishPlan with a generic task model.

---

## 8. Batch task types

User-facing batch operations:

```text
账号类
├─ 批量检查登录
├─ 批量登录
└─ 批量刷新账号状态

环境类
├─ 批量检查 IP
├─ 批量打开环境
├─ 批量关闭环境
└─ 批量健康检查

发布类
├─ 批量立即发布
├─ 批量定时发布
└─ 批量发布前检查
```

Future platform-specific operations may be added through the same selector/resolver model.

---

## 9. Batch task execution model

Do not create one giant task that directly loops through 100 accounts without durable child jobs.

Recommended model for non-publish operations:

```text
OperationBatch
├─ id
├─ operation_type
├─ status
├─ source_selection_json
├─ resolved_targets_snapshot_json
├─ scheduled_at
├─ concurrency_limit
├─ execution_policy
├─ created_at
└─ updated_at

OperationJob
├─ id
├─ batch_id
├─ account_id? / profile_id? / channel_id?
├─ status
├─ stage
├─ started_at
├─ finished_at
├─ result_json
└─ error_message
```

Publishing remains:

```text
PublishPlan
    ↓
PublishJob per resolved Channel
    ↓
PublishAttempt
```

The UI may call both kinds "批量任务", but backend domains remain separate.

---

## 10. Execution policy

### Concurrency

```text
same Profile
→ strictly serialized by ProfileLock

different Profiles
→ bounded concurrent execution
```

Batch concurrency should have a safe application default and a configurable upper bound. Do not open unlimited Chromium profiles.

### Failure behavior

Default: **continue independent targets**.

One account requiring 2FA does not stop the other 37 accounts.

Each child target ends independently as:

- succeeded
- failed
- waiting_for_user
- needs_review
- blocked
- cancelled

Batch status is aggregated from child jobs.

### No silent skipping

If 38 accounts are selected and 2 cannot run:

```text
38 selected
36 executable
2 blocked
```

The 2 blocked targets remain visible in the task record. They are not silently removed.

---

## 11. Preflight

Every batch task has task-specific preflight before confirmation.

Example — group publishing:

```text
Store A · 发布前检查

38 accounts selected
36 ready
2 blocked

✓ 36 default Channels available
✓ 36 BrowserProfiles available
✓ content snapshot valid
✓ flow revision valid
! Account 17: no default Channel
! Account 22: Channel disabled

[返回修复] [创建任务]
```

Example — batch login:

```text
Store A · 登录检查

38 accounts
31 already logged in
4 can restore session/cookie
2 require credential login
1 credential not configured

[创建登录任务]
```

Runtime checks that require a live browser are performed after opening the iX profile and cannot be falsely presented as completed static preflight.

---

## 12. Login batch architecture

Real login happens inside iXBrowser.

```text
Account Group
    ↓
resolved Accounts
    ↓
Login Jobs
    ↓
BrowserRuntime / IXBrowserRuntime
    ↓
iX Profile window
    ↓
Login State Machine
```

Per-account strategy order:

```text
OPEN_PROFILE
↓
CHECK_EXISTING_SESSION
├─ valid -> VERIFY_IDENTITY -> SUCCESS
└─ invalid
    ↓
TRY_COOKIE_RESTORE (when configured)
    ├─ valid -> VERIFY_IDENTITY -> SUCCESS
    └─ invalid
        ↓
PASSWORD_LOGIN (when credentials are configured)
        ↓
OBSERVE_RESULT
        ├─ SUCCESS
        ├─ TWO_FACTOR_REQUIRED
        ├─ CHECKPOINT_REQUIRED
        ├─ INVALID_CREDENTIALS
        └─ UNKNOWN
```

2FA handling:

- user-owned TOTP secret may be referenced through Credential Vault and used locally
- SMS / email / app approval / security key -> Waiting for User
- checkpoint / identity challenge -> Needs Review / Manual Takeover
- no bypass of CAPTCHA, checkpoint or platform security controls

Cookie and credentials must not be stored as plaintext SQLite fields.

Recommended references:

```text
credential_ref
cookie_session_ref
```

Secrets live in Windows Credential Manager / DPAPI-backed storage.

---

## 13. Login Workbench

```text
运行 / 登录任务
Store A · 38 accounts

完成             24
登录中            3
等待              6
需要2FA            3
需要人工处理       2

账号        环境      状态             当前步骤           操作
John        #017      已完成           身份验证通过       查看
Mike        #018      登录中           Cookie 恢复        打开浏览器
Shop 02     #021      需要2FA          等待验证码         打开浏览器
Brand 04    #026      需要人工处理     Checkpoint         接管
```

Clicking `打开浏览器` or `接管` must foreground the corresponding real iXBrowser window.

Browser Workspace may arrange several iX windows for manual oversight, but it does not embed or replace the iX browser engine.

---

## 14. Batch publish UX

```text
新建发布

1 内容
Product A · Facebook 01

2 发布目标
● 按分组
☑ Store A (38)

发布身份
● 每个账号的默认发布身份

解析结果
38 accounts
36 Channels ready
2 blocked                          [查看]

3 时间
● 定时  2026-09-01 09:00
批量间隔 5 分钟

4 发布前检查
...

[保存草稿] [创建发布]
```

On creation:

```text
Group selection
↓
resolve exact Channels
↓
freeze channel targets
↓
freeze content snapshot
↓
freeze flow revision
↓
create PublishPlan + PublishJobs
```

Later group/account/channel changes do not mutate the existing plan.

---

## 15. Run center

The Run workspace should support batch grouping without hiding child details.

```text
Store A · Facebook 发布                 Running
36 targets · 18 completed · 3 running · 15 queued
███████████░░░░░░ 50%
[查看任务]

Store A · 登录检查                      Waiting for User
38 targets · 34 completed · 4 need attention
[处理 4 项]
```

Batch detail:

```text
Overview
Targets
Needs attention
Timeline
Advanced diagnostics
```

Do not expose WorkerTask IDs by default.

---

## 16. Inspect center

Human attention is aggregated across batch tasks.

```text
检查 / 需要处理

Store A · 登录任务
3 accounts need 2FA
[处理]

Store A · Facebook 发布
1 publication result uncertain
[检查]

US Group · IP检查
2 profiles changed exit IP
[检查]
```

Opening a batch inspection shows the exact affected children and safe actions.

---

## 17. Group-aware task history

Every AccountGroup detail can show recent tasks that were *created from that group selection*.

Important: historical records reference the group as source metadata but always display the frozen target count.

Example:

```text
Store A
Current members: 41

History
08/31 09:00 Facebook publish   38 frozen targets
08/30 18:00 Login check        38 frozen targets
```

This avoids the misleading impression that an old task also contained newly added members.

---

## 18. Batch task creation rules

1. Select group(s).
2. Resolve task-specific targets.
3. Deduplicate.
4. Run static preflight.
5. Show exact counts: selected / ready / blocked / needs runtime check.
6. User confirms.
7. Freeze resolved target snapshot.
8. Create durable child jobs.
9. Scheduler/Worker dispatches jobs with ProfileLock.
10. Runtime challenges become Waiting for User / Needs Review.
11. Run Center shows progress.
12. Inspect Center handles exceptions.

---

## 19. Implementation order

Recommended sequence:

### A. Account organization foundation
- AccountGroup model + migration
- Account.group_id
- group CRUD
- group sidebar
- batch move accounts
- 未分组 virtual group

### B. Account execution identity
- SocialAccount UI migration from legacy Accounts page
- default Channel selection per account
- login state normalization
- group readiness counts

### C. Secure login foundation
- CredentialRef
- CookieSessionRef
- Windows credential/cookie vault abstraction
- Login State Machine
- 2FA/checkpoint/manual takeover states

### D. Common target-selection layer
- GroupSelector
- TargetResolver
- TargetSnapshot
- preflight result model
- reusable selection UI

### E. Non-publish batch operations
- OperationBatch / OperationJob
- batch login
- batch login check
- batch IP/profile health checks
- group-aware Run and Inspect views

### F. Group-aware publishing
- select group(s) in New Publish
- resolve default Channels
- frozen target snapshot metadata
- PublishPlan creation from resolved Channels
- group source shown in plan/history

### G. Browser Workspace
- window foreground/focus
- arrange 1x1 / 2x2 / 3x2 where practical
- manual takeover from Login Workbench / Inspect

---

## 20. Product contract

The final product contract is:

```text
组织账号
↓
选择分组
↓
选择任务
↓
解析具体目标
↓
检查准备状态
↓
确认并冻结目标
↓
批量执行
↓
运行中心看进度
↓
检查中心处理异常
```

This is the standard interaction model for login, account checks, IP checks and publishing. The user should not have to repeatedly select dozens or hundreds of individual accounts after they have already organized them into groups.
