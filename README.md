# Social Publisher

基于 **iXBrowser + Selenium** 的本地多账号、多平台矩阵内容发布与浏览器自动化系统。

> 当前阶段：**Facebook V1 Release Candidate（Phase 9）**。Facebook 的正式产品链路已经迁移到 `Channel → PublishPlan → PublishJob → Scheduler → Worker → Platform Adapter → PublishAttempt`。Instagram Feed Post 已进入 **Phase 8A Experimental**，在 Facebook RC 完成实机验收前暂停继续扩展 Instagram / Threads / X。

---

## 1. 产品定位

Social Publisher 的正式定位是：

> **基于独立浏览器环境的本地社交媒体矩阵自动发布平台。**

核心业务链：

```text
素材中心
   ↓
iX账号中心 / Channel
   ↓
流程中心
   ↓
发布中心
   ↓
PublishPlan
   ↓
计划中心 / Scheduler
   ↓
任务中心 / PublishJob / PublishAttempt
```

核心原则：

- 素材、渠道、流程、发布计划和实际执行任务必须分离。
- iXBrowser / Selenium / Worker / Profile Lock 属于执行基础设施，不作为普通用户 UI 的主体。
- 新平台复用现有一级导航，不为 Instagram / Threads / X 单独增加一级模块。
- 自动化流程采用受约束的 Browser Workflow，不开放任意 JS / Python / Shell。
- 只用于用户有权管理的账号、主页和渠道。
- CAPTCHA、Checkpoint、登录恢复、安全挑战必须进入人工处理，不做绕过。

---

## 2. V1 后台：8 个中心

正式路由已经建立：

```text
/             总览
/assets       素材中心
/accounts     iX账号中心
/flows        流程中心
/publish      发布中心
/plans        计划中心
/tasks        任务中心
/settings     配置中心
```

### 总览

回答系统当前状态：

- 今日计划
- 执行中
- 成功 / 失败 / 待人工确认
- Scheduler / Worker Pool / iXBrowser 健康状态
- Facebook / Instagram 平台流程状态

### 素材中心

管理发布内容：

- 文案
- 图片
- 视频
- 混合媒体
- Emoji / 完整 Unicode

Asset/Content 只描述“发什么”，不永久绑定账号或发布时间。

### iX账号中心

管理：

```text
iX Environment
   ├── Facebook Channel
   │    └── Profile / Page
   └── Instagram Channel
        └── Feed Account
```

V1 发布只选择 `Channel`。账号分组可直接用于批量选择。

### 流程中心

正式领域模型：

```text
Flow
└── FlowRevision
    └── FlowStep
```

发布计划必须绑定固定 `flow_revision_id`。后续流程升级不能改变已经创建的 Plan/Job。

### 发布中心

当前支持：

- 从素材中心选择 Asset
- 临时创建内容
- 按平台选择 Channel
- 分组全选
- 立即发布
- 定时发布
- 保存草稿
- 发布间隔

一个 V1 `PublishPlan` 只允许一个平台，避免跨平台 Flow 和验证语义混合。

### 计划中心

Scheduler 的 Source of Truth 是 **SQLite**。

电脑或 Backend 重启后，已保存计划不能丢失。

### 任务中心

统一展示：

- PublishJob 状态
- 当前 Stage
- PublishAttempt
- Timeline
- 执行耗时
- 失败原因
- `needs_review` 人工确认

### 配置中心

主要管理：

- 默认时区
- Worker 最大并发
- 默认发布间隔
- 失败重试
- Browser Warm Session TTL
- iXBrowser Local API
- 平台高级配置

---

## 3. 正式领域模型

```text
BrowserProfile
     │
     ▼
Channel

Asset / Content

Flow
└── FlowRevision
    └── FlowStep

PublishPlan
├── PublishJob
│   └── PublishAttempt
└── PublishJob
    └── PublishAttempt
```

### Channel

一个 Channel 代表一个真实可发布目标：

```text
channel_id
profile_id
platform
target_id
target_name
target_type
target_url
enabled
health_status
last_checked_at
```

稳定身份 ID 用于授权判断，名称只用于展示和导航。

### PublishPlan

表示一次用户发布意图：

```text
Asset / Content
Channels
立即 / 定时 / 草稿
时区
发布间隔
Flow Revision
```

### PublishJob

一个 Plan 选择 N 个 Channel，就生成 N 个独立 Job：

```text
Plan
├── Job → Channel 001
├── Job → Channel 002
└── Job → Channel 003
```

### PublishAttempt

记录每一次真实执行：

```text
attempt_no
status
stage
started_at
submitted_at
finished_at
browser_open_ms
platform_ms
media_ms
verification_ms
total_ms
result_json
error_message
```

---

## 4. Snapshot 原则

创建 Plan/Job 时固定关键输入：

```text
content snapshot
channel snapshot
flow_revision_id
scheduled_at
```

任务运行时不能重新读取“最新定义”改变已创建任务的行为。

---

## 5. Scheduler / Worker 架构

```text
React Admin
    ↓
FastAPI
    ↓
SQLite
    ↓
Scheduler
    ↓
Job Queue
    ↓
Bounded Worker Pool
    ↓
Profile Lock
    ↓
Browser Session Pool
    ↓
iXBrowser Local API
    ↓
Selenium
    ↓
Platform Adapter
```

Scheduler 只发现正式 Plan Job：

```text
WHERE plan_id IS NOT NULL
AND status = scheduled
AND scheduled_at <= now
```

执行规则：

- 同一个 iX Profile 同时最多运行 1 个发布任务。
- 不同 Profile 可使用 bounded Worker Pool 并发。
- Profile Lock 被其他操作占用时，Scheduler 延后任务，不把临时忙碌误判为发布失败。
- Channel 被停用时阻止 dispatch，但不修改已经冻结的 Job snapshot。
- Warm Session 在 TTL 内复用，超时后回收。

---

## 6. Facebook V1 发布安全模型

Facebook V1 正式生产 Adapter：

```text
FacebookCompositeAdapter
```

核心流水线：

```text
检查登录
   ↓
校验 actor_id == target_id
   ↓
打开目标
   ↓
打开 Composer
   ↓
输入正文
   ↓
上传媒体（如有）
   ↓
等待媒体处理
   ↓
Next（如页面需要）
   ↓
发布前再次校验身份
   ↓
Post
   ↓
验证结果
```

个人主页和公共主页共用同一条流水线，不按 `target_type` 维护两套发布逻辑。

### Target Actor Gate

真正的授权条件：

```text
current actor_id == configured target_id
```

`target_type` 只用于展示。

### needs_review

- 最终提交前明确失败 → `failed`
- 已可能点击最终 Post，但结果无法确认 → `needs_review`
- `needs_review` 永不自动重试
- Backend 在可能已经提交的阶段异常退出，也必须保守进入 `needs_review`
- 用户人工确认“已发布”后收口为成功
- 用户确认“未发布”后才允许创建安全的新 Attempt

---

## 7. 当前代码真实状态

### Facebook — V1 Release Candidate

已实现：

- iXBrowser 环境同步
- Browser open / attach / probe / close
- Worker Pool + Profile Lock
- Backend 重启后的保守恢复
- Channel 模型
- Flow / FlowRevision / FlowStep
- Asset / Content
- PublishPlan
- PublishJob
- PublishAttempt
- SQLite Scheduler
- 分组批量选择
- 发布间隔
- Browser Warm Session TTL
- Task Timeline / Stage / 性能数据
- `needs_review` 人工确认
- Facebook 个人主页 / 公共主页
- `actor_id / target_id` 强安全门禁
- 正文、图片、视频、混合媒体
- Unicode / Emoji（CDP `Input.insertText`）
- 公共主页 `Next → Post`
- 个人主页直接 Post
- 发布结果验证
- GitHub CI：Backend compile/import + Phase validators + Frontend TypeScript/Vite build

历史实机 PoC 已确认：

```text
Facebook 个人主页：图文发布成功
Facebook 公共主页：图文发布成功
Emoji / 非 BMP Unicode：输入链路已修复并验证
```

Phase 9 仍要求按真实生产 iX Profile 再完成完整 RC 验收。

### Instagram — Phase 8A Experimental

当前已有：

- Instagram Channel capture
- `ds_user_id` 稳定身份校验
- Feed Post Adapter
- 图片 / 视频 / 多媒体 Feed 发布基础流程
- 发布中心平台切换
- 平台无关的 `needs_review` 人工确认

当前不继续扩展：

- Story
- Reels 深度能力
- 音乐
- 协作者
- Threads
- X

Facebook RC 通过前冻结进一步平台扩张。

---

## 8. 兼容层与 Source of Truth

当前仓库仍保留部分 PoC / 迁移兼容对象，但必须明确边界。

| 对象 | 当前定位 |
|---|---|
| `Channel` | **V1 产品级发布目标 Source of Truth** |
| `PublishPlan` | **V1 发布意图 Source of Truth** |
| `PublishJob` | **V1 产品级任务** |
| `PublishAttempt` | **V1 真实执行记录** |
| `PublishTarget` | Facebook/Instagram 渠道发现与迁移兼容对象 |
| `Account` | 旧账号兼容模型，不能作为新 Plan 发布目标 |
| `WorkerTask` | Runtime 基础设施，不是产品层任务模型 |
| `content_id/profile_id` on formal Job | 旧路径兼容字段；正式 Plan Job 留空 |

新代码不得重新把 `PublishTarget / Account / WorkerTask` 提升为产品层发布 Source of Truth。

---

## 9. 前端架构

正式入口：

```text
frontend/src/main.tsx
    ↓
frontend/src/app/router.tsx
    ↓
frontend/src/app/layout.tsx
    ↓
frontend/src/pages/*
```

旧 anchor PoC shell 已在 Phase 9 删除：

```text
frontend/src/App.tsx
frontend/src/ContentComposer.tsx
frontend/src/AdminSidebar.tsx
```

仍保留并被正式页面使用：

```text
FacebookTargetPanel.tsx
FacebookFlowConfigPanel.tsx
InstagramChannelPanel.tsx
```

它们分别属于账号中心 / 流程中心的功能组件，不是旧入口。

UI 原则：

- Desktop：Sidebar + Header + Content
- Table first, Card second
- 任务/账号/素材/计划详情优先 Drawer
- Flow 页面可采用 Canvas + Step Inspector + Debug Log
- 不做大量渐变、巨型圆角、过度 AI SaaS 风格

---

## 10. V1 功能边界

### V1 要做

- 8 个中心
- Channel
- Asset
- Flow Revision / Step
- PublishPlan / PublishJob / PublishAttempt
- Facebook 普通帖子
- 立即 / 定时发布
- 多 Channel 批量发布
- 发布间隔
- SQLite Scheduler
- Worker Pool
- Profile Lock
- Browser Warm Session
- Timeline / Stage / 性能数据
- 普通失败重试
- `needs_review` 人工确认
- 配置中心

### V1 当前不做

- AI 文案生成
- 评论管理
- 私信管理
- 粉丝管理
- 数据分析中心
- 团队权限 / 审批流
- SaaS 多租户
- 任意 JavaScript / Python / Shell Workflow
- 复杂策略中心

---

## 11. 开发阶段状态

```text
Phase 1  ✅ 8 个中心 + 真实页面路由
Phase 2  ✅ Channel / Plan / Attempt / Flow 领域模型
Phase 3  ✅ Facebook PoC 迁移到正式产品页面与执行桥
Phase 4  ✅ SQLite Scheduler
Phase 5  ✅ 批量发布 / 分组 / 间隔 / Warm Session
Phase 6  ✅ Timeline / 性能 / needs_review 人工确认
Phase 7  ✅ Facebook Adapter 组合式收口
Phase 8  ✅ Instagram Feed Post 基础 Adapter（Experimental）
Phase 9  🚧 Facebook V1 Release Candidate 收口与实机验收
```

Phase 9 自动 RC gate：

```text
backend/validate_phase9.py
```

完整验收清单：

```text
docs/phase-9-facebook-v1-rc.md
```

**Phase 9 完成前，不继续扩展 Threads / X，也不继续堆 Instagram 新能力。**

---

## 12. 本地运行

### iXBrowser Local API

默认：

```text
http://127.0.0.1:53200/api/v2/
```

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

Web Admin：

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

Facebook 本地流程关键词：

```text
data/facebook_flow.json
```

---

## 13. GitHub / 本地开发约定

GitHub `main` 是源代码 Source of Truth。

本地自动镜像只同步源码；运行时数据必须留在本地。

不要提交：

- 密码
- Cookies
- API Token
- Proxy Credentials
- Facebook / Instagram Session Secrets
- 本地数据库
- 上传媒体
- `.env`

---

## 14. 安全与使用范围

系统只用于用户有权管理的账号、主页和渠道。

明确不做：

- 绕过 CAPTCHA
- 绕过 Checkpoint
- 绕过登录 / 账号恢复机制
- 绕过平台访问控制
- 规避安全挑战

遇到登录、Checkpoint 或安全验证，任务进入人工处理。

---

## 15. 新聊天接续说明

继续开发前先读取本 README 和 `docs/phase-9-facebook-v1-rc.md`。

当前最高优先级：

```text
Facebook V1 RC
→ CI 全部通过
→ 本地 iXBrowser 实机验收
→ 修复验收中发现的问题
→ Facebook V1 stable
```

不要重新从 Phase 1 开始，也不要在 Facebook RC 完成前继续扩平台功能。
