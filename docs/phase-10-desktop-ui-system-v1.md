# Phase 10 — Desktop UI System V1

Status: design-system baseline for the future Windows desktop app

This document defines the visual, interaction and component system that all Phase 10 high-fidelity workspaces must share. It is intentionally stricter than the current web admin so that the product stops accumulating page-specific CSS and phase-specific visual conventions.

## 1. Product design position

Social Publisher Desktop is an operations/workspace product, not a marketing dashboard.

Design references are used as interaction benchmarks, not as skins to copy:

- Linear: dense but calm task lists, attention-first triage, restrained chrome.
- Raycast: command palette, keyboard-first actions, fast direct manipulation.
- Postiz / mature social schedulers: composer, content reuse, channel selection and calendar scheduling.
- Activepieces / n8n: workflow definition separated from workflow execution.
- Windmill: queued/running/completed job states, run detail and progressive diagnostics.
- Windows 11 desktop conventions: native-feeling shell, compact controls, predictable keyboard focus and window behavior.

The product-specific layer remains:

- iXBrowser Runtime
- Proxy / exit IP
- Social account login and identity
- Human browser takeover
- Content library / ContentPackage
- Batch scheduled publishing
- Run / inspection workflow

## 2. Design principles

### 2.1 Action before inventory

A page should first answer what the user can or must do next. Counts and inventories are secondary.

### 2.2 State before decoration

Color, emphasis and hierarchy communicate operational state. Decorative gradients, oversized illustrations and ornamental charts are avoided.

### 2.3 List first, card second

Use lists and tables for operational collections. Use cards only when the object benefits from preview, grouping or a clear task action.

Good card candidates:

- ContentPackage
- Asset collection
- Needs Review item
- Browser environment summary
- Preflight result

Poor card candidates:

- every PublishJob
- every setting
- every status metric

### 2.4 Progressive disclosure

Normal UI uses user concepts. Technical details live behind `高级诊断`.

Normal UI must not expose by default:

- worker IDs
- PublishAttempt IDs
- FlowRevision IDs
- raw selectors
- raw Selenium exceptions
- Profile Lock implementation
- internal browser states

### 2.5 Desktop density

The product should feel like professional Windows operations software, not a mobile layout stretched to desktop.

- compact row heights
- restrained padding
- short headers
- multiple columns where useful
- drawers for detail
- keyboard focus states everywhere

## 3. Target platform and window model

Primary target: Windows desktop via Tauri + React.

Recommended application window:

- preferred design canvas: 1440 × 900
- comfortable range: 1280 × 800 to 1920 × 1200+
- minimum supported app viewport: 1180 × 720
- below minimum width: use horizontal protection / drawers rather than collapsing the whole product into a phone-style navigation

V1 desktop is not a mobile-first product. Mobile web breakpoints from the current admin are not the architecture target.

### 3.1 Window chrome

Use a custom Tauri title bar only if native drag/maximize/minimize behavior remains correct. Otherwise retain native Windows chrome.

Application content begins with:

```text
┌─────────────────────────────────────────────────────────────┐
│ title bar / Windows controls                                │
├──────────────┬──────────────────────────────────────────────┤
│ Sidebar      │ Workspace Header / Command                   │
│              ├──────────────────────────────────────────────┤
│              │ Current workspace                            │
│              │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

## 4. Layout system

### 4.1 Sidebar

Expanded width: 220 px
Collapsed width: 56 px

The default desktop state is expanded.

Top-level order:

```text
工作台
准备
发布
运行
检查
────────
设置
```

Rules:

- one line label only
- icon + label
- no explanatory subtitle under every nav item
- selected item uses a subtle surface change and a small accent indicator
- Settings separated toward bottom
- Runtime health / user area pinned at bottom

Do not reproduce the current two-line navigation entries such as `中心名称 + 描述`; they consume too much vertical space and make navigation look like cards.

### 4.2 Workspace header

Height target: 56–64 px, not a large card.

Structure:

```text
Breadcrumb / Page title              Search Ctrl+K    Primary action
```

Page titles should not sit inside a bordered white panel.

### 4.3 Content padding

Default workspace padding:

- horizontal: 24 px
- vertical: 20–24 px

Dense list pages may use 20 px horizontal padding.

### 4.4 Content width

Do not force every page into one fixed centered 1220/1360 px shell.

Use three modes:

- `standard`: readable operational workspace up to ~1440 px content width
- `wide`: tables, Publisher and browser environments use all available workspace width
- `canvas`: Flow / Browser Workspace can use the full remaining viewport

### 4.5 Grid

Use a 12-column logical grid with 16 px gutters for dashboard/preparation compositions.

Common patterns:

- 6 + 6: two main operational panels
- 8 + 4: main work + compact contextual panel
- 4 + 4 + 4: only for short readiness/summary blocks

Do not create 5–6 equal KPI cards simply to fill the screen.

## 5. Spacing scale

Base rhythm: 4 px, with an 8 px primary spacing system.

Tokens:

```text
space-1   4
space-2   8
space-3   12
space-4   16
space-5   20
space-6   24
space-8   32
space-10  40
```

Rules:

- row internal gap: 8–12
- card/list section gap: 16
- workspace section gap: 24
- major page groups: 32

Avoid arbitrary values unless required by a native control.

## 6. Typography

Primary Windows font stack:

```css
font-family: "Segoe UI Variable", "Segoe UI", Inter, system-ui, sans-serif;
```

No bundled custom font is required for V1.

Type scale:

| Role | Size | Weight | Use |
| --- | ---: | ---: | --- |
| Page title | 24 | 650 | workspace title |
| Section title | 16 | 650 | panel/list section |
| Dialog title | 18 | 650 | modal / drawer |
| Body | 13 | 400–500 | default desktop text |
| Emphasis | 13 | 600 | names / primary values |
| Secondary | 12 | 400–500 | metadata |
| Caption | 11 | 500 | timestamps / compact hints |
| Mono diagnostic | 11–12 | 400 | IDs / technical diagnostics only |

Rules:

- no 36–58 px web-style H1 inside the desktop app
- avoid uppercase section labels for Chinese UI
- tabular numbers for times, counts, IP addresses and durations
- line height 1.4–1.55 for normal text

## 7. Surface and color tokens

V1 is light-first. Dark mode can be added later only after the component system stabilizes.

Suggested semantic tokens:

```text
app-bg             #F5F6F8
sidebar-bg         #F8F9FB
surface            #FFFFFF
surface-subtle     #F8F9FA
surface-hover      #F3F5F7
border             #E3E6EA
border-strong      #CDD2D8
text               #171A1F
text-secondary     #5F6875
text-muted         #89919D
accent             #2563EB
accent-hover       #1D4ED8
focus              #3B82F6
success            #16805A
warning            #B7791F
danger             #B42318
review              #A15C16
```

Semantic surfaces must be pale and restrained. Do not fill entire large cards with saturated status colors.

Examples:

- success: neutral surface + green dot/chip
- warning: pale amber chip / narrow left indicator
- needs review: pale amber/orange surface only on the actionable item
- failure: red text/border used locally, not entire page

## 8. Radius and shadow

The product should not look excessively rounded.

Radius tokens:

```text
radius-sm   4 px
radius-md   6 px
radius-lg   8 px
radius-xl   10 px   // dialogs / large browser workspace only
```

Do not use 16–24 px SaaS cards.

Shadow:

- default panels: no shadow, 1 px border
- floating command palette / menu: low shadow
- Drawer / modal: medium shadow
- browser workspace window preview: subtle window shadow only

The design is border-led, not shadow-led.

## 9. Iconography

Use one consistent outline icon set for product chrome.

Recommended implementation direction: Lucide-style 16/18 px line icons or equivalent.

Rules:

- 16 px in lists/buttons
- 18 px in primary nav
- 20 px maximum for ordinary workspace actions
- platform logos may retain brand appearance where recognition matters
- avoid emoji as product icons

## 10. Core components

### 10.1 AppShell

Owns:

- sidebar
- workspace header
- global command palette
- global notifications/toast layer
- drawer/modal portals
- runtime health indicator

### 10.2 SidebarItem

States:

- default
- hover
- active
- focus-visible
- disabled only when a feature is truly unavailable

No descriptive subtitle in default nav.

### 10.3 PageHeader

Props/concepts:

```text
title
breadcrumb?
description?       // optional and short
actions?
secondaryNav?
```

The description is optional; operational pages should not repeatedly explain their underlying technical models.

### 10.4 SecondaryNav

For workspace sub-navigation:

```text
准备: 概览 / 浏览器环境 / 网络-IP / 社交账号 / 素材中心 / 自动化流程
发布: 新建发布 / 草稿 / 已计划 / 日历
运行: 正在运行 / 等待执行 / 最近运行
检查: 需要处理 / 失败 / 已发布 / 全部记录
```

Desktop presentation: compact horizontal tabs under PageHeader, or a narrow contextual rail only when the section becomes too large.

### 10.5 Button

Variants:

- Primary
- Secondary
- Ghost
- Danger
- Icon

Sizes:

```text
sm  30 px
md  34 px
lg  38 px  // exceptional primary forms only
```

Only one visually dominant Primary CTA per local task area.

### 10.6 StatusChip

User-level states only:

```text
Draft
Ready
Scheduled
Queued
Running
Waiting for User
Needs Review
Failed
Published
```

Fine-grained execution stages appear as secondary text.

### 10.7 DataList / DataTable

Default row height:

- compact: 40 px
- normal: 48 px
- rich: 56–64 px

Rules:

- sticky header where long lists justify it
- row selection on click when a detail drawer exists
- row actions on hover or right edge
- columns prioritize user meaning before IDs
- IDs only inside detail/diagnostics

### 10.8 Drawer

Preferred detail surface for:

- run detail
- environment detail
- account detail
- scheduled item detail
- published record detail

Width:

- normal: 560–640 px
- diagnostic/rich: 720 px

Use modal dialogs only for short decisions/forms. Use full pages for complex editors.

### 10.9 NeedsReviewCard

Structure:

```text
Platform / target                    Needs Review
Human-readable reason
What the system already did
What the user should do next

[Primary safe action] [Secondary action]
```

Never make `重试` the dominant action when submission may already have happened.

### 10.10 RunRow

Structure:

```text
Platform · target                         Running
Content / job type
Current human-readable stage       elapsed
Progress / current step
Environment
[Open browser] [View process]
```

### 10.11 Timeline

Normal timeline is human language and chronological.

Advanced diagnostic events are a separate disclosure.

### 10.12 Preflight

Preflight is one of the primary product components.

Rows:

```text
浏览器环境
网络 / IP
社交账号
素材
自动化流程
```

Each row owns:

```text
state
summary
blocking?
action
```

Overall state:

```text
Ready
Warning
Blocked
```

A warning may allow publication only if the rule is explicitly non-blocking. Identity mismatch, missing local file, missing login and security challenge are blocking.

### 10.13 AssetCard

Use for visual media and collection browsing, not every text row.

Image/video card:

- thumbnail
- type
- title
- dimensions/duration
- tags
- status

Text assets can default to list/table view.

### 10.14 ContentPackageCard

Primary reusable publishing asset.

Shows:

- package name
- short text preview
- media count / thumbnails
- platform compatibility
- tags
- last used
- select/open actions

### 10.15 BrowserEnvironmentRow

Preferred list model:

```text
iX #001
associated social account / identity
Runtime status
Proxy + observed exit IP
Login state
Last check
[Open browser]
```

Do not conflate browser environment with the social account object.

### 10.16 BrowserWorkspace

This is visual integration, not process embedding.

Two modes:

1. Side-by-side workspace: Social Publisher arranges the real iXBrowser window next to the application.
2. Workspace controller: the app shows environment/control information while the external browser remains separately managed.

The UI must not fake a live embedded browser if the actual process is external.

## 11. Command Palette

Shortcut: `Ctrl+K`.

Primary commands:

- 新建发布
- 搜索素材 / 内容组合
- 打开浏览器环境
- 检查登录
- 检查 IP
- 批量检查
- 批量登录
- 打开需要处理
- 跳转到运行中的任务
- 跳转到账号 / 环境 / 发布记录

Search result sections:

```text
Actions
Environments
Accounts
Content
Scheduled
Runs
Inspection
```

Keyboard support:

- Up / Down select
- Enter execute/open
- Esc close

## 12. Feedback and state patterns

### Loading

Prefer skeleton or local row loading over full-page spinners.

### Empty

Empty states should contain:

- what is empty
- why it matters
- one next action

Do not use decorative illustrations unless they add actual instruction.

### Error

Operational error message:

```text
What failed
What remains safe/unsafe
Recommended next action
```

Raw stacktrace belongs under diagnostics.

### Toast

Use for transient success such as:

- settings saved
- asset imported
- check started

Do not use toast as the only place to report an important task failure or Needs Review item.

## 13. Motion

Motion is functional only.

Suggested durations:

- hover/focus: 100–140 ms
- menu/popover: 120–160 ms
- drawer: 160–220 ms
- progress state changes: subtle

Respect reduced-motion preference.

No large page-slide animations between main workspaces.

## 14. Accessibility and keyboard rules

- every interactive control has visible focus
- minimum target height for ordinary controls: 30 px desktop
- icon-only buttons require accessible labels/tooltips
- status cannot rely on color alone
- Escape closes popover/drawer where safe
- Enter activates selected command/list item
- dangerous actions require explicit confirmation when irreversible
- text/background contrast must remain readable on all semantic surfaces

## 15. Desktop-specific interaction rules

### 15.1 Right-click / context menu

Useful for dense operational lists:

- environment
- asset/package
- scheduled publication
- run

Context actions duplicate discoverable visible actions; they must not be the only access path.

### 15.2 Multi-select

Support checkbox/multi-select where batch operations are expected:

- Browser environments
- Proxy endpoints
- Social accounts
- Assets
- Channels
- scheduled publications where safe

Selection creates a compact action bar rather than moving all actions into each row.

### 15.3 Browser takeover

`打开浏览器` / `人工处理` should:

- open or focus the correct iX profile
- arrange the browser window predictably
- surface the corresponding environment/task in Social Publisher
- not attempt to bypass MFA/checkpoint/security challenge

## 16. High-fidelity page composition rules

### 工作台

Use four major areas only:

1. 今日重点
2. 当前运行
3. 今天计划
4. 准备状态

A tiny top status summary may exist, but no large KPI wall.

### 准备

Preparation overview is readiness-led. Subpages are operational lists.

### 素材中心

Use visual grid for image/video/package/collection discovery and list view for large-scale management. Provide a view toggle if useful.

### 发布

Use a clear 4-step composition:

1. 内容
2. 发布位置
3. 时间/间隔
4. 发布前检查

The final CTA stays visible near the bottom/right action area. Do not expose database model names.

### 运行

List-first. Current runs are visually prioritized; queued items are quieter. Run details open in Drawer.

### 检查

Default to Needs Review queue. The action to safely resolve the item is the visual focus.

### 设置

Use a left settings category rail + right form/details area rather than many equal cards.

## 17. CSS / frontend architecture target

The current frontend globally imports many style files in `main.tsx`. Phase 10 must migrate toward a stable system instead of continuing `phaseN.css` growth.

Target structure:

```text
frontend/src/
  ui/
    tokens.css
    reset.css
    shell/
      AppShell.tsx
      app-shell.css
    components/
      Button.tsx
      StatusChip.tsx
      PageHeader.tsx
      SecondaryNav.tsx
      DataList.tsx
      Drawer.tsx
      CommandPalette.tsx
      Preflight.tsx
      RunRow.tsx
      NeedsReviewCard.tsx
      AssetCard.tsx
      ContentPackageCard.tsx
  workspaces/
    Dashboard/
    Prepare/
    Assets/
    Publish/
    Run/
    Inspect/
    Settings/
```

Rules:

1. `main.tsx` should eventually import only base/reset/tokens and the application entry stylesheet.
2. Component styles belong with the component or in a bounded UI layer.
3. No new `phase7.css`, `phase8.css`, etc.
4. No new generic global selectors such as `table`, `h1`, `.panel` for product components.
5. New Phase 10 components use explicit names or CSS Modules/scoped styling.
6. Existing CSS is removed only after the corresponding old component/page is migrated and visually verified.

## 18. Current frontend migration findings

Observed current constraints that Phase 10 must correct:

- the application shell currently uses a 236 px admin sidebar and two-line nav items
- page headers are rendered as large bordered panels
- the base stylesheet includes web-style large H1 sizing and global table/panel selectors
- `main.tsx` imports a growing collection of global styles, including historical phase-specific styles
- Dashboard still exposes technical terms such as PublishPlan / PublishJob and implementation-health detail directly in the normal view
- Assets still behaves mostly as a technical ContentItem table rather than a reusable content library
- Publisher contains much of the correct underlying business flow, but its UI exposes implementation terminology and needs to move to the new ContentPackage + Preflight interaction model
- Tasks already contains useful Timeline / Needs Review logic that should be preserved while the product presentation is split into `运行` and `检查`

These are migration observations, not reasons to rewrite the backend domain model.

## 19. Migration sequence

Do not restyle every existing page at once.

Recommended implementation order:

### UI Foundation

1. tokens / reset
2. AppShell + Sidebar
3. PageHeader + SecondaryNav
4. Buttons / chips / fields
5. Drawer / CommandPalette
6. list/table primitives

### First high-fidelity workspace

7. 工作台

Use this page to validate the desktop shell and visual language.

### Preparation

8. 准备概览
9. 浏览器环境
10. 素材中心

### Execution

11. 发布
12. 运行
13. 检查

### Remaining

14. 自动化流程
15. 设置
16. remove superseded legacy global CSS

## 20. High-fidelity approval gate

Before implementation of all six pages, create one high-fidelity `工作台` design using this system.

Approve or revise:

- shell density
- sidebar
- typography
- status hierarchy
- spacing
- component radius
- button hierarchy
- information density

Only after that visual baseline is accepted should the other workspaces be rendered in high fidelity.

## 21. Phase 10 Step 3 exit criteria

This design-system step is complete when:

- shell dimensions are fixed
- spacing/type/radius/color rules are fixed
- component inventory is fixed
- desktop interaction rules are fixed
- CSS migration boundaries are fixed
- no business page code has been prematurely rewritten

Next step: produce one high-fidelity 工作台 mockup from this design system, review it, then propagate the accepted system to Prepare / Assets / Publish / Run / Inspect.