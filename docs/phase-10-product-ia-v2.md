# Phase 10 — Product Information Architecture V2

Status: design baseline

This document defines the user-facing information architecture for the future Windows desktop version of Social Publisher. It intentionally does not rename the backend domain model. The product UI is organized around human work: prepare → publish → run → inspect.

## 1. Benchmark principles

The V2 product shell combines mature interaction patterns rather than copying one product:

- Linear: attention-first inbox/triage, focused lists, filters, state-driven work.
- Raycast: universal search, action panel, keyboard-first shortcuts and command discovery.
- Postiz / mature social schedulers: composer, channel selection, scheduling and content reuse.
- Activepieces / n8n: visual flow definition separated from flow execution.
- Windmill: queued/running/completed jobs, run details, logs and scheduling are separate concepts.
- Social Publisher-specific: iXBrowser runtime, proxy/IP, social login, browser workspace and human takeover.

The dashboard must not become a collection of database-object statistics.

## 2. Top-level navigation

```text
Social Publisher Desktop

工作台
准备
发布
运行
检查
────────────
设置
```

Rules:

1. Top-level navigation describes what the user is trying to do, not internal data models.
2. Assets, Accounts, Flows, Plans and Tasks are no longer first-level product concepts.
3. Search / Command Palette is globally available with Ctrl+K.
4. Contextual secondary navigation is used inside each workspace.
5. Advanced diagnostics are progressively disclosed; ordinary users do not see worker IDs, flow revision IDs or raw selector configuration by default.

## 3. Global desktop shell

```text
┌──────────────────┬──────────────────────────────────────────────────────┐
│ Social Publisher │  Breadcrumb / Page title               Search Ctrl+K│
│                  │                                                      │
│ 工作台           │                                                      │
│ 准备             │               Current workspace                     │
│ 发布             │                                                      │
│ 运行             │                                                      │
│ 检查             │                                                      │
│                  │                                                      │
│ 设置             │                                                      │
│                  │                                                      │
│ Runtime ●        │                                                      │
└──────────────────┴──────────────────────────────────────────────────────┘
```

Global actions available from Ctrl+K / Action Panel:

- 新建发布
- 导入素材
- 打开 iX 环境
- 检查登录
- 批量检查
- 批量登录
- 打开需要处理
- 搜索账号 / 环境 / 素材 / 发布记录

## 4. Workspace 1 — 工作台

### User question

> 现在最需要我做什么？系统正在做什么？今天接下来会发生什么？发布条件是否正常？

### Information hierarchy

1. Needs attention
2. Running now
3. Upcoming today
4. Overall readiness

### Low-fidelity layout

```text
工作台                                      [新建发布]
今天 · 08/30                [搜索 / Ctrl+K]

需要处理 2      运行中 3      今日待执行 26      已发布 84
────────────────────────────────────────────────────────────

今日重点                               当前运行
┌────────────────────────────┐        ┌────────────────────────────┐
│ Facebook 登录 · John       │        │ Facebook · Page A          │
│ 需要验证码                 │        │ 图片上传中            4/8 │
│ [打开浏览器]               │        │ ███████████░░░░░           │
│                            │        │                            │
│ Facebook 发布 · Store A    │        │ Facebook 登录 · John       │
│ 发布状态待确认             │        │ 检查身份              2/5 │
│ [处理]                     │        │ ██████░░░░░░░░░           │
└────────────────────────────┘        └────────────────────────────┘

即将发布                               发布准备状态
09:00  Facebook · Page A              浏览器环境        正常
09:15  Facebook · Store B             Proxy / IP        1项异常
09:30  Instagram · Brand 02           社交账号          正常
10:00  Facebook · John                素材              就绪
                                      自动化流程        已验证
                                      [查看准备详情]
```

### Must NOT appear by default

- Asset totals
- FlowRevision IDs
- PublishPlan IDs
- WorkerTask IDs
- PublishAttempt IDs
- raw Selenium / DOM state
- large analytics charts
- browser profile inventory tables

The homepage is an action surface, not an inventory report.

## 5. Workspace 2 — 准备

### User question

> 发布前，我的浏览器、网络、账号、素材和流程是否准备好了？

### Secondary navigation

```text
准备
├─ 概览
├─ 浏览器环境
├─ 网络 / IP
├─ 社交账号
├─ 素材中心
└─ 自动化流程
```

### Overview low-fidelity layout

```text
准备
发布前所有依赖集中在这里

整体准备度  92%                              [批量检查]
────────────────────────────────────────────────────────

浏览器环境              网络 / IP
12 正常 / 1 异常         11 正常 / 2 待处理
[查看环境]               [查看网络]

社交账号                素材中心
18 已登录 / 2 待处理     126 可用内容
[查看账号]               [打开素材中心]

自动化流程
Facebook Post · 已验证
Instagram Feed · Experimental
[查看流程]

需要修复
• iX #017 出口 IP 已变化                        [处理]
• Facebook · John 需要重新确认登录              [打开浏览器]
```

### Browser Environment subpage

The iXBrowser profile is a browser runtime resource, not the social account itself.

```text
浏览器环境
[搜索] [筛选状态] [批量启动] [批量关闭] [批量检查]

环境      Runtime     Proxy       Social           Status        Action
#001      iX ●        US #12      Facebook John    正常          打开
#014      iX ●        CA #04      Instagram Brand  正常          检查
#017      iX ○        US #22      Facebook Store   IP变化        详情
```

Environment detail owns:

- iX profile metadata
- current runtime state
- assigned proxy
- current observed exit IP
- associated social accounts
- open / close / arrange window / take over
- health checks

### Network / IP subpage

Owns:

- Proxy endpoints
- batch import
- connectivity check
- exit IP check
- country / region / latency
- assignment to browser environment
- IP change alerts

Social accounts do not directly own proxy credentials; browser environment does.

### Social Account subpage

Owns:

- platform account
- login state
- associated BrowserProfile
- discovered identities / Pages
- credential reference
- login workflow
- human takeover when MFA/checkpoint appears

### Automation Flow subpage

Ordinary UI:

```text
Facebook 发帖
打开环境
  ↓
检查登录
  ↓
检查身份
  ↓
打开 Composer
  ↓
写入内容
  ↓
上传媒体
  ↓
发布
  ↓
验证结果
```

Raw selector/keyword groups live under Advanced Diagnostics, not the primary flow editor.

## 6. Core sub-workspace — 素材中心

素材中心 belongs to 准备 but is important enough to have its own full workspace view.

### User question

> 我提前准备了哪些可复用内容？发布时能不能直接选择？

### Secondary navigation

```text
素材中心
├─ 全部
├─ 文案
├─ 图片
├─ 视频
├─ 内容组合
└─ 素材集合
```

### Low-fidelity layout

```text
素材中心                                      [上传素材] [新建内容组合]
[搜索素材]   [类型] [标签] [最近使用]

收藏 / 最近使用
┌──────────────────────┐  ┌──────────────────────┐
│ Summer Campaign      │  │ Product A            │
│ 10 文案 · 30 图片    │  │ 6 组合 · 18 图片     │
│ 5 视频 · 6 内容组合  │  │ 最近使用 2小时前     │
└──────────────────────┘  └──────────────────────┘

内容库
[缩略图] product-01.jpg      图片    product-a,sale
[缩略图] launch-video.mp4    视频    launch,vertical
[文案]   Facebook Copy 07    文案    facebook,us
```

### Content Package

A ContentPackage is the primary reusable publishing content unit.

```text
内容组合：Product A · Facebook 01

文案
Summer sale ...

媒体
01.jpg   02.jpg   03.jpg

适用平台
Facebook

标签
product-a / us / summer

[保存]
```

### Asset rules

1. Asset = one source item: text, image or video.
2. AssetCollection = organizational grouping.
3. ContentPackage = reusable publish-ready composition.
4. Publishing references ContentPackage but freezes a snapshot when creating a plan.
5. Editing the library after scheduling must never mutate already-created jobs.

## 7. Workspace 3 — 发布

### User question

> 发什么？发到哪里？什么时候发？

### Secondary navigation

```text
发布
├─ 新建发布
├─ 草稿
├─ 已计划
└─ 日历
```

Plans are a backend domain model. The product calls them scheduled publications, not PublishPlans.

### New Publish low-fidelity layout

```text
新建发布

1 内容
────────────────────────────────────────────────────────
[选择内容组合]
Product A · Facebook 01
文案 + 3 图片
[预览] [更换]

2 发布位置
────────────────────────────────────────────────────────
Facebook
☑ John
☑ Page A
☑ Store B

3 发布时间
────────────────────────────────────────────────────────
○ 立即发布
● 定时发布       2026-09-02 09:00

批量间隔
[ 5 ] 分钟

4 发布前检查
────────────────────────────────────────────────────────
✓ 3 个 Channel 可用
✓ 浏览器环境正常
✓ 账号登录正常
✓ 素材文件正常
! 1 个 Proxy 延迟偏高                         [查看]

                              [保存草稿] [创建发布]
```

### Calendar

Calendar is a view of scheduled publications, not a separate top-level center.

Views:

- Day
- Week
- Month
- List

Drag/drop rescheduling may come later; V1 priority is correctness and inspectability.

### Must NOT appear

- Worker configuration
- direct FlowRevision selection for normal users
- attempt internals
- database IDs

## 8. Workspace 4 — 运行

### User question

> 当前系统正在执行什么？执行到了哪一步？

### Secondary navigation

```text
运行
├─ 正在运行
├─ 等待执行
└─ 最近运行
```

### Low-fidelity layout

```text
运行
[全部] [发布] [登录] [检查] [平台] [环境]

Facebook 发布 · Page A                         Running
图片上传中                                      00:24
████████████░░░░                                 4 / 8
Environment #001 · Facebook

Facebook 登录 · John                           Waiting for User
需要验证码                                      01:38
Environment #014
[打开浏览器]

Proxy 检查 · Environment #017                  Queued
计划 09:15
```

### Run detail

Default human-readable timeline:

```text
09:30:02  启动任务
09:30:04  打开浏览器环境
09:30:06  登录检查通过
09:30:08  身份检查通过
09:30:11  打开帖子编辑器
09:30:13  写入正文
09:30:15  上传图片
09:30:21  图片处理完成
09:30:22  准备发布
09:30:24  已提交发布
09:30:27  发布结果验证成功
```

Advanced diagnostics collapsible panel may expose:

- facebook_state
- actor_id / target_id
- job id / attempt id
- duration_ms
- selector diagnostics
- raw errors

### User-facing run states

- Queued
- Scheduled
- Running
- Waiting for User
- Needs Review
- Failed
- Published / Succeeded

Fine-grained browser states are sub-statuses, not first-class product statuses.

## 9. Workspace 5 — 检查

### User question

> 哪些结果需要我处理？哪些成功？哪些明确失败？

### Secondary navigation

```text
检查
├─ 需要处理
├─ 失败
├─ 已发布
└─ 全部记录
```

Default page is 需要处理, not All.

### Low-fidelity layout

```text
检查 / 需要处理                                     3

Facebook 发布 · Store A
发布状态无法确认
系统已经执行 Post，但没有独立确认发布结果。
2 分钟前
[打开 Facebook] [标记已发布] [确认未发布并重试]
────────────────────────────────────────────────────────

Facebook 登录 · John
需要验证码
6 分钟前
[打开浏览器]
────────────────────────────────────────────────────────

Environment #017
出口 IP 已变化
12 分钟前
[重新检测] [查看环境]
```

### Inspection model

Needs Review is a first-class human work queue inspired by inbox/triage patterns. Unknown or uncertain states are surfaced for action instead of being hidden in logs.

A successful publication page can show:

- channel / identity
- content snapshot preview
- scheduled / submitted / verified times
- permalink when available
- execution duration

## 10. Settings

Settings is global configuration, not daily work.

Recommended groups:

```text
设置
├─ 应用
├─ Browser Runtime
├─ Scheduler / Worker
├─ 平台
├─ 存储
├─ 安全与凭据
├─ 通知
└─ 高级诊断
```

Raw Facebook keyword configuration, Selenium timeouts and debugging controls belong under 高级诊断.

## 11. Current → V2 migration map

| Current product page | V2 destination | Decision |
| --- | --- | --- |
| 总览 Dashboard | 工作台 | Replace information hierarchy |
| 素材中心 Assets | 准备 → 素材中心 | Expand substantially |
| iX账号中心 Accounts | 准备 → 浏览器环境 + 社交账号 | Split responsibilities |
| 流程中心 Flows | 准备 → 自动化流程 | Keep, simplify normal UI |
| 发布中心 Publisher | 发布 → 新建发布 | Keep as core action |
| 计划中心 Plans | 发布 → 已计划 / 日历 | Remove top-level nav |
| 任务中心 Tasks | 运行 | Reframe around live execution |
| Existing attempts/review states | 检查 | Create dedicated human queue |
| 配置中心 Settings | 设置 | Reorganize by desktop concerns |

## 12. Product-level object language

User-facing objects:

- 浏览器环境
- 网络 / IP
- 社交账号
- 素材
- 内容组合
- 发布
- 运行任务
- 检查事项

Backend domain objects remain independent:

- BrowserProfile / Channel
- Asset
- Flow / FlowRevision
- PublishPlan
- PublishJob
- PublishAttempt

UI language must not leak backend naming unless advanced diagnostics is open.

## 13. Desktop-specific architecture implication

The future Windows app is treated as a workspace shell:

```text
Tauri + React Desktop UI
        │
        ├─ Global Search / Command Palette
        ├─ Workspace Navigation
        ├─ Native Notifications
        ├─ System Tray
        ├─ Window Manager
        └─ Credential Vault
                │
                ▼
Python Local Core
        │
        ├─ BrowserRuntime
        ├─ ProxyService
        ├─ AccountService
        ├─ PreflightEngine
        ├─ LoginEngine
        ├─ PublishEngine
        ├─ JobEngine
        └─ InspectionService
                │
                ▼
            iXBrowser
```

The iXBrowser browser window is visually coordinated with Social Publisher, not forced into the app process.

## 14. Phase 10 implementation order

1. Approve this information architecture.
2. Produce low-fidelity wireframes for each workspace using this exact hierarchy.
3. Produce one shared desktop design system / component language.
4. Generate high-fidelity mockups for 工作台, 准备, 素材中心, 发布, 运行, 检查.
5. Define URL/route migration and component boundaries.
6. Implement the new desktop-oriented frontend shell without changing the backend domain model first.
7. Then implement BrowserRuntime / Proxy / Account / Preflight boundaries.

Do not begin large visual implementation before steps 1–4 are stable.
