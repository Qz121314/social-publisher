# Phase 10 — Core Workspace Wireframes V1

Status: low-fidelity product architecture baseline

This document translates the Phase 10 information architecture into six core user-facing workspaces. It intentionally avoids visual styling decisions and implementation details. The goal is to lock hierarchy, task flow, navigation and progressive disclosure before high-fidelity Windows desktop UI work begins.

## 0. Global rules

### Top-level navigation

```text
工作台
准备
发布
运行
检查
────────
设置
```

### Global desktop shell

```text
┌──────────────────┬─────────────────────────────────────────────────────────────┐
│ Social Publisher │ Breadcrumb / Page title               Search / Ctrl+K      │
│                  │                                                             │
│ 工作台           │                                                             │
│ 准备             │                     Current workspace                       │
│ 发布             │                                                             │
│ 运行             │                                                             │
│ 检查             │                                                             │
│                  │                                                             │
│ 设置             │                                                             │
│                  │                                                             │
│ Runtime status   │                                                             │
└──────────────────┴─────────────────────────────────────────────────────────────┘
```

### Global interaction principles

1. Action first: show the next useful action before secondary statistics.
2. Attention first: unresolved problems appear before completed history.
3. Progressive disclosure: technical diagnostics are hidden behind `高级诊断`.
4. User-level states only in ordinary UI: Draft / Ready / Scheduled / Queued / Running / Needs Review / Failed / Published.
5. Search / Command Palette (`Ctrl+K`) can jump to environment, account, asset, package, scheduled item, run or inspection item.
6. Top-level pages do not expose `PublishJob`, `PublishAttempt`, worker IDs, profile locks, raw selectors or flow revision IDs by default.

---

# 1. 工作台

## User question

> 现在最需要我处理什么？系统正在做什么？今天接下来会发生什么？发布条件是否正常？

## Layout

```text
工作台                                            [新建发布]
今天 · 系统状态                                      [Ctrl+K]

┌───────────────────────────────┬─────────────────────────────────────┐
│ 今日重点                      │ 当前运行                            │
│                               │                                     │
│ 2 个需要处理                  │ Facebook · Page A                  │
│                               │ 图片上传中            4 / 8         │
│ Facebook 登录 · John          │ ███████████░░░                     │
│ 需要验证码        [处理]      │                                     │
│                               │ Facebook 登录 · Store B             │
│ Facebook 发布 · Store A       │ 正在检查身份          2 / 5         │
│ 发布状态待确认    [处理]      │ ███████░░░░░░                     │
│                               │                                     │
│ [查看全部需要处理]            │ [查看全部运行]                      │
└───────────────────────────────┴─────────────────────────────────────┘

┌───────────────────────────────┬─────────────────────────────────────┐
│ 今天计划                      │ 准备状态                            │
│                               │                                     │
│ 09:00 Facebook · Page A       │ 浏览器环境        正常              │
│ 09:15 Facebook · Store B      │ 代理 / IP         1 项异常          │
│ 09:30 Instagram · Brand 02    │ 社交账号          正常              │
│ 10:00 Facebook · John         │ 素材              就绪              │
│                               │ 自动化流程        已验证            │
│ [查看发布日历]                │ [进入准备]                          │
└───────────────────────────────┴─────────────────────────────────────┘
```

## Keep on dashboard

- Needs Review / blocking items.
- Current active runs.
- Near-term schedule.
- Overall readiness.
- One primary CTA: `新建发布`.

## Do not put on dashboard

- Asset totals.
- Account totals.
- Flow counts.
- Raw logs.
- Historical charts unless a later analytics product requirement justifies them.
- Browser workspace preview by default; browser workspace belongs under 准备 / 运行 / 检查 contextually.

---

# 2. 准备

## User question

> 在开始发布之前，我缺什么？哪里需要修复？

## Secondary navigation

```text
准备
├─ 概览
├─ 浏览器环境
├─ 网络 / IP
├─ 社交账号
├─ 素材中心
└─ 自动化流程
```

## 准备概览 wireframe

```text
准备
发布前条件与资源

整体准备度                                      Ready 4 / 5
██████████████████████████░░░░

┌──────────────────────────┬──────────┬──────────────────────────────┐
│ 浏览器环境               │ 正常     │ 18 / 18 个环境可用           │
│ iXBrowser Runtime        │          │ [管理环境]                   │
├──────────────────────────┼──────────┼──────────────────────────────┤
│ 网络 / IP                │ 1项异常  │ iX #017 出口 IP 已变化        │
│ Proxy / Connection       │          │ [修复]                       │
├──────────────────────────┼──────────┼──────────────────────────────┤
│ 社交账号                 │ 正常     │ 16 / 16 身份已确认           │
│ Login / Identity         │          │ [管理账号]                   │
├──────────────────────────┼──────────┼──────────────────────────────┤
│ 素材中心                 │ 就绪     │ 12 个可发布内容组合          │
│ Content Library          │          │ [打开素材中心]               │
├──────────────────────────┼──────────┼──────────────────────────────┤
│ 自动化流程               │ 已验证   │ Facebook V1 可用             │
│ Publishing Flows         │          │ [查看流程]                   │
└──────────────────────────┴──────────┴──────────────────────────────┘
```

## Browser environment workspace

```text
浏览器环境                                      [导入/同步 iX]

筛选: [全部] [运行中] [需要检查] [未登录]
搜索环境...

┌────────────────────────────────────────────────────────────────────┐
│ iX #001    ● Running                                              │
│ Facebook · John                                                   │
│ Proxy: US Residential   IP: 73.x.x.x   Login: 正常                │
│                                                                    │
│ [打开浏览器] [检查登录] [检查 IP] [更多]                          │
└────────────────────────────────────────────────────────────────────┘
```

### Browser workspace behavior

`打开浏览器` launches the real iXBrowser profile and uses the Windows desktop window manager to place the browser next to Social Publisher. The product does not hard-embed the Chromium process.

---

# 3. 素材中心

## User question

> 我已经准备了哪些内容？哪些内容可以直接用于发布？

## Secondary navigation

```text
素材中心
├─ 全部
├─ 文案
├─ 图片
├─ 视频
├─ 内容组合
└─ 素材集合
```

## Main wireframe

```text
素材中心                                  [上传素材] [新建内容组合]
搜索素材...          筛选: 类型 / 标签 / 集合 / 使用状态

[全部] [文案] [图片] [视频] [内容组合] [素材集合]

最近使用
┌────────────────────┐ ┌────────────────────┐ ┌────────────────────┐
│ Product A · FB 01  │ │ Summer Campaign    │ │ Store B Weekend    │
│ 内容组合           │ │ 素材集合           │ │ 内容组合           │
│                    │ │                    │ │                    │
│ 文案 1             │ │ 图片 30            │ │ 文案 1             │
│ 图片 3             │ │ 文案 10            │ │ 视频 1             │
│ Facebook           │ │ 视频 5             │ │ Facebook           │
│                    │ │                    │ │                    │
│ [选择] [详情]      │ │ [打开]             │ │ [选择] [详情]      │
└────────────────────┘ └────────────────────┘ └────────────────────┘

全部素材
┌────────┬────────────────────────────┬───────────┬──────────┬──────────────┐
│ 类型   │ 名称                       │ 标签      │ 最近使用 │ 状态         │
├────────┼────────────────────────────┼───────────┼──────────┼──────────────┤
│ 图片   │ product-a-01.jpg           │ product-a │ 今天     │ 可用         │
│ 文案   │ Product A Copy 01          │ facebook  │ 今天     │ 可用         │
│ 视频   │ promo-short-01.mp4         │ reels     │ 昨天     │ 已检测       │
└────────┴────────────────────────────┴───────────┴──────────┴──────────────┘
```

## Content Package editor

```text
内容组合 / Product A · Facebook 01

名称
[Product A · Facebook 01                         ]

文案
[选择文案]  Product A Copy 01

媒体
[+ 添加图片/视频]
┌──────┐ ┌──────┐ ┌──────┐
│ img1 │ │ img2 │ │ img3 │
└──────┘ └──────┘ └──────┘

适用平台
Facebook ✓    Instagram ○

标签
product-a   us   summer

                              [保存内容组合]
```

## Asset rules

- Asset = reusable source item: text / image / video.
- AssetCollection = organization/folder-like collection.
- ContentPackage = publishable composition of text + media + platform applicability.
- Publishing references ContentPackage where possible.
- Publish creation freezes a snapshot; later edits to the source package do not mutate already-created scheduled work.

---

# 4. 发布

## User question

> 我要发什么？发到哪里？什么时候发？

## Secondary navigation

```text
发布
├─ 新建发布
├─ 草稿
├─ 已计划
└─ 日历
```

## New publish wireframe

```text
新建发布

1 内容
┌───────────────────────────────────────────────────────────────────┐
│ [选择内容组合]                                                    │
│                                                                   │
│ Product A · Facebook 01                                           │
│ 文案 1 · 图片 3                                                   │
│                                                   [预览] [更换]   │
└───────────────────────────────────────────────────────────────────┘

2 发布位置
┌───────────────────────────────────────────────────────────────────┐
│ Facebook                                                          │
│ ☑ Page A                 iX #001      Ready                       │
│ ☑ Store B                iX #014      Ready                       │
│ ☑ John                   iX #017      IP 需检查                   │
│                                                                   │
│ [选择账号 / Channel]                                             │
└───────────────────────────────────────────────────────────────────┘

3 时间
┌───────────────────────────────────────────────────────────────────┐
│ ○ 立即发布                                                       │
│ ● 定时发布   2026-09-03  09:00                                  │
│                                                                   │
│ 批量间隔     [ 5 ] 分钟                                          │
└───────────────────────────────────────────────────────────────────┘

4 发布前检查
┌───────────────────────────────────────────────────────────────────┐
│ 内容           ✓                                                 │
│ 2 个发布位置   ✓                                                 │
│ Store B         ✓                                                │
│ John            ⚠ IP 需要重新检查                               │
│                                                                   │
│                         [修复问题]                                │
└───────────────────────────────────────────────────────────────────┘

                         [保存草稿]       [创建发布]
```

## Publishing rules

- No user-facing `PublishPlan` wording.
- Immediate and scheduled publishing are one workflow.
- Multi-channel publishing is first-class.
- Batch interval is defined here.
- Preflight blocks unsafe execution before jobs enter the queue.
- At `创建发布`, content, channel and flow snapshots are frozen.

## Calendar

Use a schedule-first visual model similar to mature social schedulers:

```text
日历
[日] [周] [月]

09:00  Facebook · Page A      Product A FB 01
09:05  Facebook · Store B     Product A FB 01
09:10  Facebook · John        Product A FB 01
```

---

# 5. 运行

## User question

> 系统现在正在执行什么？执行到哪里？是否需要人工接管？

## Secondary navigation

```text
运行
├─ 正在运行
├─ 等待执行
└─ 最近运行
```

## Main wireframe

```text
运行

[正在运行 3] [等待执行 26] [最近运行]

┌────────────────────────────────────────────────────────────────────┐
│ Facebook 发布 · Page A                              Running        │
│ Product A · Facebook 01                                            │
│                                                                    │
│ 当前步骤      图片上传中                                           │
│ ████████████████░░░░░░                         4 / 8              │
│                                                                    │
│ iX #001   Facebook   运行 00:00:24                                │
│                                                                    │
│ [打开浏览器] [查看过程]                                            │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│ Facebook 登录 · John                                 Waiting User  │
│                                                                    │
│ Facebook 要求 Two-factor authentication                            │
│                                                                    │
│ [打开浏览器进行人工处理]                                           │
└────────────────────────────────────────────────────────────────────┘
```

## Run detail

Default timeline is human-readable:

```text
09:30:02  启动任务
09:30:04  打开 Facebook
09:30:06  登录检查通过
09:30:08  发布身份检查通过
09:30:11  打开帖子编辑器
09:30:13  写入正文
09:30:15  上传图片
09:30:21  图片处理完成
09:30:22  准备发布
```

Advanced diagnostics are collapsed:

```text
高级诊断
actor_id
facebook_state
selector / surface
flow revision
attempt
raw error
```

## Run principles

- Runs are not the same thing as definitions.
- Waiting for User is explicit and visually distinct from Failed.
- Same iX profile execution remains serialized by runtime infrastructure.
- User sees current work state, not internal worker mechanics.

---

# 6. 检查

## User question

> 哪些事情需要我确认？哪些明确失败？哪些已经成功？

## Secondary navigation

```text
检查
├─ 需要处理
├─ 失败
├─ 已发布
└─ 全部记录
```

Default route: `需要处理`.

## Needs Review wireframe

```text
检查 / 需要处理                                      3

┌─────────────────────────────────────────────────────────────────────┐
│ Facebook 发布 · Store A                          Needs Review       │
│ 2 分钟前                                                            │
│                                                                     │
│ 系统已执行最终 Post，但没有独立确认帖子结果。                        │
│ 自动重试可能造成重复发布。                                          │
│                                                                     │
│ [打开 Facebook]  [标记已发布]  [确认未发布并重新执行]               │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Facebook 登录 · John                             Waiting User       │
│                                                                     │
│ Facebook 要求验证码。                                               │
│                                                                     │
│ [打开浏览器]                                                        │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Network · iX #017                                 Environment       │
│                                                                     │
│ 出口 IP 已从 73.x.x.x 变更为 64.x.x.x。                            │
│                                                                     │
│ [重新检测] [确认变化]                                               │
└─────────────────────────────────────────────────────────────────────┘
```

## Failure page

Only deterministic failures belong here:

- media file missing
- login definitely invalid
- target actor mismatch before submission
- browser/runtime unavailable
- pre-submit Facebook interaction failure

An uncertain post-submit state does **not** belong in Failed; it belongs in Needs Review.

## Published page

```text
已发布

时间       平台       目标         内容组合            结果
09:00      Facebook  Page A       Product A FB 01     Published
09:05      Facebook  Store B      Product A FB 01     Published
```

---

# 7. Existing V1 → V2 product migration

| Current page | V2 destination | Action |
|---|---|---|
| Dashboard | 工作台 | Rewrite hierarchy, keep useful status data |
| Assets | 准备 → 素材中心 | Expand into Asset / Collection / ContentPackage |
| Accounts | 准备 → 浏览器环境 + 社交账号 | Split responsibilities |
| Flows | 准备 → 自动化流程 | Keep, hide raw keyword details behind advanced settings |
| Publisher | 发布 → 新建发布 | Become primary creation experience |
| Plans | 发布 → 已计划 / 日历 | Remove first-level navigation |
| Tasks | 运行 + 检查 | Split active execution from outcome triage |
| Settings | 设置 | Keep first-level utility area |

---

# 8. Product state model

User-level states:

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

Runtime sub-states such as `media_processing`, `next_ready`, `post_ready`, `checking_identity`, `browser_starting` are diagnostic/run-progress states, not top-level product statuses.

---

# 9. Windows desktop implementation constraints for later phases

These wireframes assume the final product is a Windows desktop application:

- Tauri + React desktop shell.
- Python local core / sidecar retained for automation and scheduling.
- iXBrowser used as Browser Runtime Provider through Local API.
- Real iXBrowser windows visually coordinated by a Windows window manager rather than hard-embedded.
- Windows Credential Manager / DPAPI for account and proxy secrets; SQLite stores references, not plaintext passwords.
- System tray and background scheduler are desktop-level capabilities.
- Browser takeover is explicit and always tied to one concrete environment/run/review item.

---

# 10. Exit criteria for this design step

Before high-fidelity UI work:

1. Confirm the six workspace boundaries.
2. Confirm `素材中心` uses ContentPackage as the preferred publish source.
3. Confirm `发布` absorbs Plans.
4. Confirm `任务中心` splits into `运行` and `检查`.
5. Confirm `准备` separates Browser / Network / Social Account / Assets / Flow.
6. Confirm the dashboard remains an action/attention surface, not a statistics dashboard.

After approval, proceed to Phase 10 UI System: desktop shell, component hierarchy, spacing/density rules, status language, list/card patterns, command palette and high-fidelity mockups.