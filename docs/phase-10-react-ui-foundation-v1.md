# Phase 10 — React UI Foundation V1

Status: implementation baseline

This phase turns the approved desktop information architecture into real React UI code. It is intentionally dependency-light in the first migration step: the project owns its visual primitives and tokens, while interactive primitives can later be replaced or backed by Base UI without changing page composition.

## 1. UI architecture

```text
React + TypeScript
│
├─ ui/
│  ├─ tokens.css        semantic design tokens
│  ├─ primitives.css    shared component styling
│  ├─ components.tsx    source-owned React primitives
│  └─ icons.tsx         one icon language
│
├─ app/
│  ├─ layout.tsx        Windows workspace shell
│  ├─ sidebar.tsx       task-oriented navigation
│  ├─ command-palette.tsx
│  └─ desktop-shell.css
│
└─ pages/
   ├─ Dashboard/        first migrated workspace
   └─ Review/           first-class inspection workspace
```

## 2. Component ownership

The project owns the source of its ordinary visual components.

Current primitives:

- Button
- StatusChip
- Panel
- ListRow
- ProgressBar
- EmptyState
- WorkspaceHeader
- Icon set
- Sidebar navigation
- Command Palette

This follows the same source-owned principle that makes shadcn-style systems attractive: visual code is not hidden behind a large theme API.

## 3. Semantic tokens

Pages must consume semantic tokens rather than hard-coded page colors.

Core surfaces:

```text
--sp-app-bg
--sp-sidebar-bg
--sp-surface
--sp-surface-subtle
--sp-surface-hover
--sp-surface-selected
```

Text:

```text
--sp-text
--sp-text-secondary
--sp-text-muted
--sp-text-faint
```

State:

```text
--sp-accent
--sp-success
--sp-warning
--sp-danger
--sp-info
--sp-neutral
```

Geometry:

```text
radius: 4 / 6 / 8 / 10
spacing: 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40
control heights: 30 / 36 / 40
```

## 4. Desktop shell

Primary layout:

```text
220px Sidebar
+
56px top command bar
+
remaining workspace
```

The shell is Windows-first and assumes a minimum working viewport of 1180px. Mobile collapse rules from the legacy web admin are not the target architecture.

Primary navigation:

```text
工作台
准备
发布
运行
检查
────────
设置
```

The first migration maps the existing preparation pages (Accounts / Assets / Flows) under the single `准备` navigation concept while keeping their existing routes available.

## 5. Workbench composition

The new Dashboard is not a KPI dashboard. Its hierarchy is:

1. Needs attention
2. Current runs
3. Upcoming scheduled publishing
4. Readiness

Compact summary values are allowed, but they are not the main visual content.

The page reads real existing APIs:

```text
/api/status
/api/tasks/publish-jobs
/api/publish-plans
```

No mock-only dashboard state is introduced.

## 6. Inspection workspace

`/review` is a first-class product route.

It filters the existing execution records into human action states:

- needs_review
- failed

The full attempt timeline and manual confirmation operations remain available in the existing task detail during this migration phase. Business logic is not duplicated into the new page until the review action API is moved into reusable hooks/services.

## 7. CSS migration rule

New Phase 10 work must not add:

```text
phase7.css
phase8.css
phase9.css
```

New styles belong to one of three scopes:

```text
ui/tokens.css                 semantic tokens only
ui/primitives.css             reusable component styles
<workspace>/<workspace>.css   genuinely workspace-specific composition
```

Legacy CSS remains temporarily loaded because unmigrated pages still depend on it. `tokens.css`, `primitives.css`, and `desktop-shell.css` are loaded after the legacy stack so migrated components have a stable layer without editing unrelated legacy screens.

## 8. Base UI / shadcn / TanStack migration

V1 does not add large runtime dependencies just to restyle one workspace. The next infrastructure step may introduce:

- Base UI-backed Dialog / Popover / Select / Menu primitives
- TanStack Query for server-state polling/cache
- TanStack Table + Virtual for large operational lists
- React Hook Form + Zod for forms

These should replace implementation details behind the current component contracts, not force a visual redesign.

## 9. Acceptance criteria

- Desktop shell uses the new 220px task-oriented sidebar.
- Workbench uses real API data.
- Dashboard no longer displays Phase progress or raw infrastructure metrics as its primary content.
- `needs_review` is visible from a dedicated Inspection workspace.
- Ctrl+K opens a real command palette.
- New UI uses semantic tokens and shared primitives.
- No new `phaseN.css` file is introduced.
- Legacy pages remain reachable while migration proceeds.
