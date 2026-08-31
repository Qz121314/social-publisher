# Social Publisher

本地运行的 **Windows 社交媒体矩阵管理与自动发布工作台**。

当前技术核心：**React + TypeScript + FastAPI + SQLite + iXBrowser Local API + Selenium**。Windows 桌面产品目标采用 **Tauri 2 + React/TypeScript + Python/FastAPI sidecar**。

> 当前阶段：**Phase 10 — Desktop Product Migration**。Facebook V1 RC 的发布执行链继续作为生产基础；Phase 10 正在把旧的“多个技术中心”重构为面向人的工作流，并把 iXBrowser、账号、登录、分组和批量任务逐步集成进 Social Publisher 工作台。

---

## 1. 产品定位

Social Publisher 的正式定位：

> **以 Social Publisher 为主工作台，以 iXBrowser 为 Browser Runtime Provider 的本地多账号自动发布系统。**

用户长期操作的是：

```text
账号
  ↓
分组
  ↓
内容
  ↓
任务
  ↓
结果
```

而不是直接操作：

```text
Profile / WebDriver / Worker / Job ID / FlowRevision / SDK
```

### 核心产品原则

1. **Social Publisher 是主控制台。** 能在工作台完成的操作，不要求用户回到 iXBrowser 管理界面重复操作。
2. **iXBrowser 只提供真实的隔离浏览器环境。** Profile 的创建、打开、关闭、窗口、Cookies、Proxy 等能力通过 Local API 被工作台调用。
3. **登录、发布、检查始终发生在真实 iXBrowser Profile 窗口中。** React 不模拟 Facebook / Instagram 登录页。
4. **账号与浏览器环境建立稳定绑定。** 不为同一账号在每次任务中随机创建新的 Profile。
5. **正常 Session 不主动重新登录。** 批量“登录”实际是批量检查并恢复登录状态。
6. **分组是批量任务的一级选择单位。** 用户正常路径应尽量接近：`选组 → 执行动作 → 只处理异常`。
7. **系统内部可以复杂，用户路径必须短。** TargetResolver、Snapshot、ProfileLock、Worker Pool、Preflight 等属于系统能力，不应成为用户必须逐步点击的页面。
8. 只用于用户有权管理的账号、主页和渠道；不绕过 CAPTCHA、Checkpoint、平台安全挑战或访问控制。

---

## 2. Phase 10 产品信息架构

正式产品一级导航：

```text
工作台
准备
发布
运行
检查
────────
设置
```

### 工作台

回答：

> 今天系统发生了什么？现在有什么需要处理？

优先展示：

- Needs Attention
- 正在运行
- 即将执行
- 今日已发布
- 准备状态

不是库存统计 Dashboard，不优先展示 Asset 数量、Job ID、Worker 指标。

### 准备

当前结构：

```text
准备
├─ 概览
├─ 浏览器环境
├─ 网络 / IP
├─ 社交账号
├─ 素材中心
└─ 自动化流程
```

网络 / IP 后续可以根据使用规模进一步收进“浏览器环境”的网络区域；底层仍保持独立服务边界。

### 发布

回答：

> 发什么？发给谁？什么时候发？

用户级概念：

```text
新建发布
草稿
已计划
日历
```

`PublishPlan` 是后台领域模型，不作为普通用户必须理解的一级概念。

### 运行

回答：

> 当前正在执行什么？执行到哪一步？

用户级状态：

- Scheduled
- Queued
- Running
- Waiting for User
- Needs Review
- Failed
- Published / Succeeded

### 检查

默认进入“需要处理”，用于统一处理：

- 2FA / MFA
- Checkpoint
- 登录异常
- 发布结果无法确认
- IP / 环境异常
- 明确失败

---

## 3. iXBrowser Runtime 边界

架构：

```text
Social Publisher Desktop
        ↓
BrowserRuntime
        ↓
IXBrowserRuntime
        ↓
iXBrowser Local API
        ↓
真实 iX Profile Window
        ↓
Selenium / CDP attach
        ↓
Facebook / Instagram
```

目标接口：

```text
BrowserRuntime
└─ IXBrowserRuntime
   ├─ list_profiles()
   ├─ create_profile()
   ├─ update_profile()
   ├─ delete_profile()
   ├─ open_profile()
   ├─ close_profile()
   ├─ health_check()
   ├─ arrange_windows()
   └─ attach_automation()
```

### 工作台应逐步接管的 iX 操作

- 同步环境
- 新建环境
- 修改环境
- 删除环境
- 打开 / 关闭
- 批量创建
- Proxy 配置与检测
- Cookie 导入 / Session 恢复
- 查询运行状态
- Windows 窗口定位、排列、置前

### 当前已实现

- iX Profile 同步
- BrowserProfile 本地镜像
- Browser open / attach / probe / close
- Browser Session Pool
- Profile Lock
- Warm Session TTL
- Phase 10 浏览器环境 React 工作区
- Profile / Session / Lock / Channel 的真实状态聚合

### 当前继续实现

- 从 Social Publisher 工作台直接创建新的 iX Profile
- 后续再接 Proxy / Account / Cookie / Login Engine

---

## 4. 浏览器环境与社交账号不是同一个对象

必须保持以下边界：

```text
BrowserProfile
= iX 指纹浏览器环境

SocialAccount / Account
= 平台登录账号

SocialIdentity / Channel
= 账号下真实可执行身份 / 发布目标
```

一个 iX Profile 可能对应：

```text
Facebook 登录账号 John
├─ John Personal
├─ Page A
└─ Page B
```

因此：

- `Profile != Account`
- `Account != Channel`
- 发布绝不能因为发现多个 Page 就默认全部发布。

每个账号应有明确的默认发布身份 / Channel，或者在创建任务时显式选择。

---

## 5. 社交账号与账号分组

账号分组是正式业务能力，不等同于 iXBrowser 自己的 Profile Group。

```text
iXBrowser Group
→ 组织浏览器环境

AccountGroup
→ 组织业务账号与批量任务
```

### AccountGroup V1

推荐模型：

```text
AccountGroup
├─ id
├─ name
├─ description
├─ sort_order
├─ enabled
├─ created_at
└─ updated_at
```

一个 SocialAccount 在 V1 有一个主分组；多维组织以后使用 Tag，而不是无限层级子分组。

### 用户操作原则

社交账号页面本身就是批量操作入口：

```text
Store A · 38 个账号

[恢复登录] [检查登录] [检查 IP] [发布] [更多]
```

不再要求用户经过：

```text
分组详情
→ 新建任务
→ Target Selector
→ Preflight 页面
→ 再确认
```

普通操作尽量缩短为：

```text
选组
→ 动作
→ 自动执行
→ 只有异常才叫用户处理
```

详细设计：

```text
docs/phase-10-account-groups-batch-tasks-v1.md
```

---

## 6. 批量任务与 Target Snapshot

分组是用户选择单位，但**不是运行时动态目标**。

任务创建时：

```text
AccountGroup
    ↓
TaskTargetResolver
    ↓
具体 Accounts / BrowserProfiles / Channels
    ↓
冻结 Target Snapshot
    ↓
Jobs
```

### 必须冻结目标

例如：

```text
08/31 Store A = A1, A2, A3
08/31 创建 09/01 09:00 的任务
08/31 晚上把 A4 加入 Store A
09/01 任务仍只执行 A1, A2, A3
```

保存：

```text
source_selection_json
resolved_targets_snapshot_json
```

### Resolver 按任务类型解析

```text
LOGIN        Group → Accounts
CHECK_LOGIN  Group → Accounts
CHECK_IP     Group → unique BrowserProfiles
OPEN_PROFILE Group → unique BrowserProfiles
PUBLISH      Group → explicit/default Channels
```

同一目标通过多个分组选中时必须去重。

---

## 7. 登录策略

“批量登录”产品语义应理解为：

> **批量检查并恢复登录状态，而不是把所有健康账号重新输入密码登录一次。**

默认 Login State Machine：

```text
OPEN FIXED IX PROFILE
        ↓
CHECK EXISTING SESSION
        ├─ valid → VERIFY IDENTITY → SUCCESS
        └─ invalid
              ↓
COOKIE / SESSION RESTORE
        ├─ valid → VERIFY IDENTITY → SUCCESS
        └─ invalid
              ↓
PASSWORD LOGIN
              ↓
OBSERVE RESULT
        ├─ SUCCESS
        ├─ TOTP REQUIRED
        ├─ OTHER MFA REQUIRED
        ├─ CHECKPOINT
        ├─ INVALID CREDENTIALS
        └─ UNKNOWN
```

### 优先级

1. **Existing Session** — 首选；健康 Session 不碰。
2. **Cookie / Session Restore** — Cookie 有效时可自动恢复，但必须重新验证真实身份。
3. **Username / Password** — 兜底。
4. **Built-in TOTP** — 用户自己的 TOTP Secret 可由本地 Credential Vault 安全读取并生成验证码。
5. **Manual 2FA / Checkpoint** — SMS、Email、App Approval、Security Key、Checkpoint、未知安全验证转人工。

### Cookie 原则

Cookie 不等于永久登录，也不能把“注入成功”当“登录成功”。

Cookie 应绑定：

```text
Account
+
BrowserProfile
+
Platform
```

不默认跨 Profile 自动复用。

### 凭据安全

普通 SQLite 不保存明文：

- Password
- Cookie blob
- TOTP Secret
- Proxy password

数据库只保存 `CredentialRef`；实际 Secret 目标使用 Windows Credential Manager / DPAPI 或等价本地加密存储。

---

## 8. 2FA / Checkpoint 与人工接管

2FA 不是“整个批量任务失败”。

例如：

```text
Store A · 恢复登录
38 accounts

31 已完成
3 自动处理中
2 需要 2FA
1 Checkpoint
1 密码错误
```

可自动处理：

- 用户配置的 TOTP Authenticator Secret

默认转人工：

- SMS Code
- Email Code
- App Approval
- Security Key / WebAuthn
- Checkpoint
- 未知 Security Challenge

人工处理入口：

```text
需要处理
→ [打开浏览器]
→ 对应真实 iX Profile Window 置前
→ 用户完成验证
→ Login Engine 再次检查 Session / Identity
```

不绕过平台安全验证。

---

## 9. Browser Workspace

Windows 桌面版目标不是把 Chromium 硬嵌到 React，而是进行**窗口级视觉整合**：

```text
Social Publisher
        +
真实 iXBrowser Windows
```

Tauri / Windows Window Manager 后续负责：

- 找到对应 iX 窗口
- 置前
- 移动 / 调整大小
- 多窗口平铺
- 跳转到需要人工处理的环境

Browser Workspace 是异常处理和人工接管工具，不应成为所有正常任务的强制步骤。

---

## 10. 正式发布领域模型

现有生产链继续保留：

```text
Asset / Content

Flow
└─ FlowRevision
   └─ FlowStep

BrowserProfile
   ↓
Channel

PublishPlan
├─ PublishJob
│  └─ PublishAttempt
└─ PublishJob
   └─ PublishAttempt
```

### Source of Truth

| 对象 | 定位 |
|---|---|
| `Channel` | 正式可发布目标 |
| `PublishPlan` | 发布意图 Source of Truth |
| `PublishJob` | 单目标正式发布任务 |
| `PublishAttempt` | 真实执行记录 |
| `PublishTarget` | 发现 / 迁移兼容对象 |
| `WorkerTask` | Runtime 基础设施，不是产品层发布任务 |

不要为了新的 UI 信息架构重命名或破坏现有领域模型。

### Snapshot 原则

创建 Plan / Job 时冻结：

```text
content snapshot
channel snapshot
flow_revision_id
scheduled_at
resolved target snapshot
```

素材库、账号分组或流程后续发生变化，不应静默修改已创建任务。

---

## 11. Scheduler / Worker / Lock

```text
React / Desktop Shell
    ↓
FastAPI
    ↓
SQLite
    ↓
Scheduler / Operation Engine
    ↓
Bounded Worker Pool
    ↓
Profile Lock
    ↓
Browser Session Pool
    ↓
iXBrowser
    ↓
Platform Adapter
```

规则：

- 同一个 iX Profile 同时最多执行 1 个浏览器敏感任务。
- 后续账号登录任务增加 Account Lock，避免同一账号在两个环境同时进行敏感登录。
- 不同 Profile 可以在 bounded Worker Pool 内并发。
- 不把临时锁冲突误判为业务失败。
- 批量任务不是一个巨大的 `for` 循环；每个目标有独立 Job / 状态。
- 一个账号失败或 Waiting for User 不阻塞整个分组剩余目标。

发布继续使用 `PublishPlan → PublishJob → PublishAttempt`；其他登录/IP/健康检查任务可以使用单独的 `OperationBatch → OperationJob`，不要破坏发布模型。

---

## 12. Facebook V1 安全模型

正式执行核心：

```text
检查登录
↓
校验当前 actor
↓
打开目标
↓
Composer
↓
正文 / 媒体
↓
发布前再次校验身份
↓
Post
↓
验证结果
```

授权门禁：

```text
current actor_id == configured target_id
```

`target_type` 只用于展示，不作为授权条件。

### needs_review

- 提交前确定失败 → `failed`
- 已可能执行最终 Post，但无法确认结果 → `needs_review`
- `needs_review` 不自动重试
- 用户确认未发布后，才允许创建安全的新 Attempt

### 禁止

- CAPTCHA 绕过
- Checkpoint 绕过
- WebDriver / `navigator.webdriver` 隐藏
- 浏览器指纹伪装用于规避平台检测
- 模拟随机鼠标 / 随机时间以规避平台审查
- 安全挑战绕过

系统优化方向是稳定 Session、正确身份门禁、合理并发、异常停机和人工接管，不是规避平台风控。

---

## 13. Phase 10 React UI System

已建立：

- Source-owned semantic design tokens
- React primitives
- Desktop shell
- Ctrl/Cmd + K Command Palette
- 工作台
- 检查入口
- 准备 Overview
- 浏览器环境工作区
- Profile / Session / Lock / Channel 状态聚合

UI 原则：

- Desktop operations workspace，不做营销型 Dashboard
- 1440×900 为主要目标，1180×720 为最低桌面尺寸
- Sidebar + compact topbar
- Segoe UI Variable / Segoe UI / Inter
- 低圆角、弱阴影、边框主导
- Table / dense list first
- Drawer 用于详情和轻量创建任务
- 一个局部区域只有一个主要动作
- 普通 UI 不暴露 WorkerTask ID、FlowRevision ID、ProfileLock 等底层概念

迁移期间旧 `/accounts`、`/assets`、`/flows`、`/tasks` 等页面可继续兼容，但新的主入口逐步迁移到 `/prepare/*`、`/run/*` 等 Phase 10 路由。

设计文档：

```text
docs/phase-10-product-ia-v2.md
docs/phase-10-core-wireframes-v1.md
docs/phase-10-desktop-ui-system-v1.md
docs/phase-10-react-ui-foundation-v1.md
docs/phase-10-account-groups-batch-tasks-v1.md
```

---

## 14. 当前实现状态

### 已完成

```text
Phase 1  ✅ 初始产品中心与真实路由
Phase 2  ✅ Channel / Plan / Attempt / Flow 领域模型
Phase 3  ✅ Facebook PoC → 正式执行桥
Phase 4  ✅ SQLite Scheduler
Phase 5  ✅ 批量发布 / 间隔 / Warm Session
Phase 6  ✅ Timeline / 性能 / needs_review
Phase 7  ✅ Facebook Adapter 收口
Phase 8  ✅ Instagram Feed 基础 Adapter（Experimental）
Phase 9  ✅ Facebook V1 RC 代码链与自动验证
Phase 10A ✅ React Desktop UI Foundation
Phase 10B ✅ Prepare / Browser Environment 第一版
```

### 仍需实机确认

Facebook V1 RC 的最终 Windows + iXBrowser + Facebook 真实环境验收仍需要在用户本机完成。CI 成功不等于完成真实平台实机验收。

### Phase 10 当前开发顺序

```text
1. iXBrowser Runtime 管理补全
   └─ 工作台创建 / 更新 / 删除 Profile

2. Network / Proxy
   └─ Proxy / Exit IP / Profile assignment

3. AccountGroup + SocialAccount
   └─ 分组、稳定 Profile 绑定、默认 Channel

4. Credential Vault / Cookie Session
   └─ Windows Credential Manager / DPAPI

5. Login Engine
   └─ Existing Session → Cookie → Password → TOTP → Manual

6. Group Batch Operations
   └─ 登录检查 / 恢复登录 / IP 检查 / 健康检查

7. 发布直接选择分组
   └─ Resolve + Snapshot + PublishJobs

8. Browser Workspace / Human Takeover

9. Tauri Windows Shell
```

Instagram / Threads / X 的扩展不是当前优先级；当前优先完成 Facebook 与桌面批量工作流。

---

## 15. 本地运行

### iXBrowser Local API

默认：

```text
http://127.0.0.1:53200/api/v2/
```

需要本机安装并启动 iXBrowser，并启用 Local API。

### Backend

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Web UI：

```text
http://127.0.0.1:5173
```

FastAPI Docs：

```text
http://127.0.0.1:8765/docs
```

Runtime database：

```text
data/social_publisher.db
```

Media：

```text
data/uploads/
```

---

## 16. GitHub / 本地数据规则

GitHub `main` 是源代码 Source of Truth。

运行时数据、账号凭据和本机环境必须留在本地。

严禁提交：

- 密码
- Cookies
- TOTP Secret
- API Token
- Proxy Credentials
- Facebook / Instagram Session Secrets
- 本地数据库
- 上传媒体
- `.env`

---

## 17. 新聊天接续说明

继续开发前优先读取本 README。

当前产品方向不要重新讨论：

```text
Social Publisher = 主工作台
IXBrowser = Browser Runtime Provider
```

当前用户操作模型：

```text
账号 → 分组 → 动作 → 自动执行 → 只处理异常
```

当前登录策略：

```text
Existing Session
→ Cookie / Session Restore
→ Password
→ Built-in TOTP
→ Manual 2FA / Checkpoint
```

当前开发任务从 **iXBrowser Runtime 管理补全** 继续，然后进入 AccountGroup、Credential/Cookie、Login Engine 和分组批量任务。