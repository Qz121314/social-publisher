# Social Publisher

基于 **iXBrowser + Selenium** 的本地多账号、多平台矩阵内容发布与浏览器自动化系统。

> 当前阶段：Facebook 单次自动发布链路已经完成核心 PoC，并已实际验证个人主页、公共主页、正文、图片和完整 Unicode/Emoji 输入。下一阶段不继续在现有 PoC 页面上堆功能，而是按照本文定义的 **V1 产品体系**重新整理领域模型、后台信息架构和自动化流程体系。

---

## 1. 产品定位

Social Publisher 不应被定义为“Facebook 自动发帖脚本”，也不只是“多账号管理工具”。正式定位是：

> **基于独立浏览器环境的本地社交媒体矩阵自动发布平台。**

核心业务链：

```text
素材中心
   ↓
准备“发什么”

iX账号中心
   ↓
准备“谁来发 / 发到哪里”

流程中心
   ↓
定义“怎么发”

发布中心
   ↓
创建一次发布

计划中心
   ↓
管理“什么时候执行”

任务中心
   ↓
观察实际执行结果

配置中心
   └── 控制系统级运行规则
```

产品设计原则：

- 素材、账号/渠道、自动化流程、发布计划和实际执行任务必须分离。
- iXBrowser / Selenium / Worker / Profile Lock 是执行基础设施，不应成为普通用户 UI 的主体。
- 平台扩展不能增加新的一级导航，例如以后增加 Instagram / Threads，应复用“账号中心、流程中心、配置中心”。
- 自动化流程采用 **受约束的 Browser Workflow**，而不是任意 JS / Python / Shell 脚本平台。
- 自动发布只用于用户有权管理的账号、主页和渠道；安全验证、CAPTCHA、Checkpoint 等必须人工处理。

---

# 2. V1 一级导航：8 个中心

正式 V1 后台固定为：

```text
总览
素材中心
iX账号中心
流程中心
发布中心
计划中心
任务中心

────────
配置中心
```

后续“策略中心”“数据中心”等不进入当前 V1。

---

## 2.1 总览

定位：回答“系统现在运行得怎么样，有什么需要处理”。

核心内容：

```text
今日计划
执行中
今日成功
异常 / 待人工确认

即将执行
最近异常
系统健康状态
```

系统状态包含：

- iXBrowser
- Scheduler
- Worker Pool
- 当前平台流程健康状态

普通总览不展示：

- Chrome debugging address
- Profile Lock owner ID
- WorkerTask UUID
- Selenium 技术细节

这些进入高级诊断。

---

## 2.2 素材中心

定位：整个系统的内容资产库，而不是简单上传文件页面。

素材对象包括：

```text
素材
├── 文案
├── 图片
├── 视频
├── 标签
├── 分组
└── 使用记录
```

V1 功能：

- 新建 / 编辑 / 复制素材
- 文案、图片、视频、组合素材
- 多图、视频、Emoji / 完整 Unicode
- 文件夹 / 分组
- 标签
- 搜索
- 批量上传
- 批量删除
- 批量移动
- 使用记录
- “使用此素材发布”入口

设计原则：

> Content/Asset 本身只负责“内容是什么”，不直接绑定具体账号、时间或一次执行任务。

---

## 2.3 iX账号中心

定位：统一管理 iXBrowser 环境和其中真实可发布的社媒渠道。

推荐层级：

```text
iX Environment
    │
    ├── Facebook Channel
    │      └── Profile / Page
    ├── Instagram Channel
    └── Threads Channel
```

普通用户看到的状态：

```text
正常
正在运行
未配置
需要登录
异常
```

默认隐藏：

```text
Selenium attached
c_user
i_user
actor_id
target_id
debugging_address
Profile Lock
```

点击“高级信息 / 诊断”后才展示。

### iX 分组

V1 必须支持账号分组，例如：

```text
美国
├── 001
├── 002
└── 003

加拿大
├── 004
└── 005

测试
└── 006
```

发布中心必须支持直接选择整个组。

### Channel 模型

长期设计中，`Account + PublishTarget` 应逐步收敛为统一的 **Channel（发布渠道）**：

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

一个 Channel 代表一个真实可执行的发布目标。

---

## 2.4 流程中心

定位：定义浏览器自动化“怎么执行”。

这是 Social Publisher 与普通社媒 API 管理工具最大的区别。

流程中心管理：

```text
Facebook
├── 普通帖子
├── Reels（未来）
└── Story（未来）

Instagram（未来）
Threads（未来）
X（未来）
```

### 当前 Facebook 普通帖子真实流程

已经跑通的核心顺序：

```text
检查登录
   ↓
校验发布身份 actor_id == target_id
   ↓
打开目标主页
   ↓
打开发帖 Composer
   ↓
输入正文
   ↓
是否有媒体？
   ├── 否 ─────────────┐
   └── 是              │
       ↓               │
   点击“照片/视频”      │
       ↓               │
   上传媒体             │
       ↓               │
   等待媒体完成         │
       └───────────────┘
           ↓
   下一页 / 下一步（如存在）
           ↓
   再次校验 actor_id == target_id
           ↓
   最终发布
           ↓
   验证结果
```

个人主页和公共主页使用同一条发布流水线，不按 `target_type` 写两套逻辑；流程根据当前 Composer 可见状态决定是直接 Post 还是先 Next。

### Flow Step

V1 允许的动作类型限制为：

```text
CHECK_LOGIN
VERIFY_ACTOR
NAVIGATE
CLICK_TEXT
CLICK_IF_EXISTS
INPUT_TEXT
UPLOAD_MEDIA
WAIT_ELEMENT
WAIT_TEXT
WAIT_MEDIA_READY
NEXT
PUBLISH
VERIFY_RESULT
```

V1 不开放：

```text
任意 JavaScript
任意 Python
任意 Shell
```

### Flow Revision

正式流程必须支持版本：

```text
Facebook 普通帖子
v1.4  当前
v1.3
v1.2
```

创建发布计划时绑定固定 `flow_revision_id`。后续修改流程不能影响已经创建的计划或正在执行的任务。

### 流程调试

支持逐阶段调试，例如：

```text
01 检查登录       ✓ 0.2s
02 校验身份       ✓ 0.1s
03 打开目标       ✓ 1.5s
04 打开 Composer  ✓ 1.1s
05 输入正文       ✓ 0.4s
06 上传媒体       ✓ 2.1s
07 下一页         ✓ 0.8s
08 最终发布       未执行
```

调试模式默认不执行最终 Publish；如需真实测试发布必须显式开启。

当前已有的“Facebook 流程关键词”以后归入流程步骤/平台高级设置，不继续作为一级主导航。

---

## 2.5 发布中心

定位：用户每天使用频率最高的“创建一次发布”页面。

核心布局：

```text
内容 / 素材                    发布目标
────────────────────────────────────────
从素材中心选择                 美国组
或临时创建内容                 ☑ 001 Page A
                               ☑ 002 Page B
文案                           ☑ 003 Profile C
图片 / 视频

────────────────────────────────────────
发布方式
● 立即发布
○ 定时发布  2026-08-30 19:00
○ 保存草稿

发布间隔  10 秒

                [创建发布任务]
```

高级选项默认折叠：

- 任务间隔
- 并发策略
- 账号执行顺序
- 流程版本

设计原则：

- UI 可以一次完成发布创建。
- 后端仍然拆成 Content/Asset + PublishPlan + PublishJob。
- “立即发布”与“定时发布”最终走同一调度流水线。

---

## 2.6 计划中心

定位：管理未来发布安排。

视图：

```text
月
周
列表
```

列表示例：

```text
今天
18:00  Summer A   Facebook × 5   已计划
18:30  Product B  Facebook × 3   已计划

明天
09:00  Summer C   Facebook × 7   已计划
```

计划详情：

```text
计划 #P1042

素材
Summer Campaign

时间
2026-08-30 18:30

渠道
001
002
003
004
005

间隔
10 秒

[修改]
[立即执行]
[取消计划]
```

Scheduler 的 Source of Truth 必须是 SQLite，而不是仅依赖进程内调度器。

---

## 2.7 任务中心

定位：所有实际执行任务和运行历史的统一中心。

顶部状态：

```text
全部
等待
执行中
成功
失败
待人工确认
```

任务表格至少显示：

```text
状态
账号 / Channel
平台
素材
当前步骤
计划时间
耗时
```

### 执行 Stage

任务运行时不能只显示 `running`，还要暴露当前阶段：

```text
opening_browser
checking_login
checking_identity
navigating
opening_composer
writing_text
uploading_media
waiting_media
advancing
ready_to_submit
submitting
verifying
```

### 任务详情 Timeline

示例：

```text
18:00:00  任务进入队列
18:00:01  启动 iXBrowser
18:00:04  Selenium 已连接
18:00:04  身份校验成功
18:00:05  Composer 打开
18:00:06  正文输入完成
18:00:07  照片/视频入口已点击
18:00:08  媒体上传
18:00:10  媒体处理完成
18:00:11  下一页
18:00:12  发布前身份检查通过
18:00:12  发帖
18:00:15  验证成功
```

同时记录：

```text
总耗时
浏览器启动耗时
平台自动化耗时
媒体耗时
验证耗时
```

### 错误展示

默认只显示用户可理解的信息：

```text
失败阶段：上传媒体
原因：Facebook“照片/视频”入口无法交互
建议：重新执行任务
```

ChromeDriver / Python Stacktrace 默认折叠在“技术详情”。

### needs_review

必须继续作为一级安全状态：

```text
系统可能已经点击最终发布，
但无法确认平台是否成功发布。

为了避免重复发布，禁止自动重试。

[打开 Facebook]
[确认已发布]
[确认未发布并重新执行]
```

---

## 2.8 配置中心

正式结构：

```text
配置中心
├── 通用
├── 执行引擎
├── iXBrowser
├── 平台配置
├── 存储
├── 日志
└── 高级
```

### 通用

- 默认时区
- 日期格式
- 默认平台
- 默认发布方式

### 执行引擎

- Worker 最大并发
- 默认任务间隔
- 普通失败重试次数
- 任务超时
- `needs_review` 永不自动重试

### iXBrowser

- Local API Host / Port
- Browser Warm Session TTL
- 空闲自动关闭
- 最大同时打开浏览器数

建议默认 Warm Session TTL：约 60 秒，而不是每个任务结束立即关闭，也不是所有环境永久常驻。

### 平台配置

例如 Facebook：

```text
状态
当前默认 Flow Revision
支持能力（文字/图片/视频/Emoji）
高级关键词
平台诊断
```

---

# 3. 正式领域模型

V1 长期目标模型：

```text
BrowserProfile
     │
     ▼
Channel

Asset / Content
├── Text
└── Media

Flow
└── FlowRevision
     └── FlowStep

PublishPlan
     │
     ├── PublishJob
     │     └── PublishAttempt
     │
     └── PublishJob
           └── PublishAttempt
```

核心关系：

```text
Environment → Channel

Asset

Flow → Revision → Step

Publish Plan → Publish Job → Publish Attempt
```

---

## 3.1 BrowserProfile

对应 iXBrowser Profile，只负责环境属性：

```text
profile_id
name
group
availability
last_seen
```

不在这个模型里混入 Facebook Composer 业务逻辑。

---

## 3.2 Channel

长期用于收敛目前的 `Account + PublishTarget` 概念。

一个 Channel = 一个真实可发布渠道：

```text
iX 003
└── Facebook
    └── Private companionship
        target_id = ...
```

身份授权仍以稳定 ID 为准，名称只用于展示和导航。

---

## 3.3 Asset / Content

内容只描述：

```text
标题
正文
媒体
标签
分组
```

不在 Content 创建时永久绑定账号和发布时间。

---

## 3.4 PublishPlan

表示用户的一次发布意图：

```text
内容
选择的 Channels
立即 / 定时
时区
间隔
绑定的 Flow Revision
```

---

## 3.5 PublishJob

一个 Plan 选择 N 个 Channel，就创建 N 个独立 Job：

```text
Plan
├── Job → Channel 001
├── Job → Channel 002
└── Job → Channel 003
```

同一 Content + 同一 Channel 必须允许今天发布一次、明天再次发布，因此未来不能继续依赖当前：

```text
UNIQUE(content_id, profile_id)
```

作为长期任务模型约束。

---

## 3.6 PublishAttempt

记录 Job 每一次真实执行：

```text
attempt_no
status
stage
started_at
submitted_at
finished_at
browser_open_ms
platform_ms
total_ms
result_json
error_message
```

`WorkerTask` 可以继续作为内部 runtime task，但不应成为产品领域的一等对象。

---

# 4. Snapshot 原则

创建 PublishPlan / PublishJob 时必须固定关键执行输入：

```text
content snapshot
channel / target snapshot
flow_revision_id
scheduled_at
```

例如任务创建时绑定 `Facebook Flow v1.4`，即使之后管理员发布了 `v1.5`，已经创建的任务仍按 v1.4 执行。

不要在真正运行的那一刻重新读取所有“最新定义”导致任务行为漂移。

---

# 5. Scheduler / Worker 正式执行架构

目标结构：

```text
                    React Admin
                         │
                         ▼
                     FastAPI
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
   Asset Service     Plan Service    Channel Service
        │                │                │
        └──────────┬─────┴────────────────┘
                   │
                   ▼
               SQLite DB
                   │
                   ▼
               Scheduler
                   │
                   ▼
                Job Queue
                   │
                   ▼
              Worker Pool
                   │
                   ▼
              Profile Lock
                   │
                   ▼
            Browser Session Pool
                   │
                   ▼
              iXBrowser API
                   │
                   ▼
               Selenium
                   │
                   ▼
               Flow Engine
                   │
                   ▼
             Platform Adapter
```

Scheduler 只负责发现到期任务并安全入队：

```text
SELECT due jobs
WHERE status = scheduled
AND scheduled_at <= now

scheduled → queued
→ Worker Pool
```

数据库是任务真相来源。电脑/Backend 重启后，计划不能丢失。

---

# 6. Facebook 发布安全模型

这一部分已经实现，后续重构必须保留。

### Target Actor Gate

Facebook 发布前的真正授权条件：

```text
current actor_id == configured target_id
```

`target_type` 只作为显示信息，不用于决定是否允许发布。

至少在关键阶段校验：

```text
身份切换后
进入目标页面后
进入下一步前
点击最终发布前
```

### needs_review

- 提交前明确失败 → `failed`
- 已可能执行最终 Post，但无法确认结果 → `needs_review`
- `needs_review` 禁止自动重试
- Backend 在可能已提交的阶段异常退出，也应保守进入 `needs_review`

---

# 7. 当前已经实现并验证的能力

> 本节描述当前代码真实状态，不代表新的 V1 页面体系已经完成。

技术栈：

- Windows 10/11
- Python 3.12
- FastAPI
- React + TypeScript + Vite
- SQLite + SQLAlchemy
- Selenium 4
- iXBrowser Local API
- 本地媒体目录 `data/uploads/`
- bounded Worker Pool（当前默认 3）
- database-backed Profile Lock

当前能力：

- iXBrowser 环境同步
- Selenium open / attach / probe / close
- Worker Pool + Profile Lock
- Backend 重启后的保守任务恢复
- 文案 / 图片 / 视频 / 混合媒体模型
- 多选 iX 创建发布任务
- Facebook 发布目标扫描
- Facebook 个人主页 / 公共主页 Target Actor 模型
- `target_id / actor_id` 强安全门禁
- Facebook Composer 自动识别
- 正文输入
- 完整 Unicode / Emoji 输入（CDP `Input.insertText`）
- 必须先点击“照片/视频”再上传媒体
- 图片上传与附件验证
- 媒体处理等待
- 公共主页 `Next → Post` staged flow
- 个人主页直接 Post flow
- 发布结果验证
- `failed / needs_review` 区分
- Facebook 流程关键词本地可配置
- GitHub Actions：Backend compile/import + Frontend build

已实际完成的关键测试：

```text
Facebook 个人主页：图文发布成功
Facebook 公共主页：图文发布成功
带 Emoji / 非 BMP Unicode 正文：已修复 ChromeDriver send_keys 限制
```

---

# 8. 当前代码与新体系的迁移关系

| 当前实现 | V1 新体系 |
|---|---|
| `ContentComposer` | 发布中心 |
| `ContentItem / MediaAsset` | 素材中心 |
| `BrowserProfile` | iX账号中心 |
| `Account` | 逐步合并进 Channel |
| `PublishTarget` | Channel |
| `FacebookTargetPanel` | iX账号中心详情 / 渠道管理 |
| Composer 诊断 | 流程中心测试 / 渠道健康检查 |
| Facebook 流程关键词 | 流程中心 Step / 配置中心高级设置 |
| `PublishJob` | 任务中心 |
| `WorkerTask` | 内部 Runtime Attempt/Task |
| `ProfileLock` | 内部执行设施 |
| Worker 并发设置 | 配置中心 |
| iX Open/Close/Probe | iX账号中心高级操作 |
| `/contents/{id}/run` | 未来由 PublishPlan 调度替代 |

---

# 9. 前端正式信息架构

当前前端仍是 PoC：`App + FacebookTargetPanel + FacebookFlowConfigPanel` 纵向渲染并通过页面 anchor 导航。

V1 必须改成真实路由：

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

推荐目录：

```text
frontend/src/
├── app/
│   ├── router.tsx
│   ├── layout.tsx
│   └── sidebar.tsx
│
├── pages/
│   ├── Dashboard/
│   ├── Assets/
│   ├── Accounts/
│   ├── Flows/
│   ├── Publisher/
│   ├── Plans/
│   ├── Tasks/
│   └── Settings/
│
├── components/
│   ├── Table/
│   ├── Drawer/
│   ├── Status/
│   ├── FilterBar/
│   ├── Dialog/
│   └── EmptyState/
│
└── features/
```

### UI 原则

- 风格参考成熟开发者后台：Linear / Vercel / GitHub / n8n / Kestra 类信息密度。
- `Table first, Card second`。
- 不做大量渐变、巨型圆角卡片、过度“AI SaaS”风格。
- Desktop 以左侧 Sidebar + Header + Content 为主。
- 任务、账号、素材、计划详情优先用右侧 Drawer，减少频繁跳页。
- 状态色统一：
  - 绿色：success / healthy
  - 蓝色：running
  - 灰色：draft / queued
  - 红色：failed
  - 橙色：needs_review / warning
- Flow 页面例外，可采用 `Canvas + Step Inspector + Debug Log`。

---

# 10. Backend 目标目录

正式重构后建议逐步收敛为：

```text
backend/app/
├── domains/
│   ├── assets/
│   ├── accounts/
│   ├── flows/
│   ├── publishing/
│   ├── tasks/
│   └── settings/
│
├── automation/
│   ├── engine.py
│   ├── scheduler.py
│   ├── workers.py
│   └── browser_pool.py
│
└── platforms/
    ├── facebook/
    │   ├── adapter.py
    │   ├── identity.py
    │   ├── composer.py
    │   ├── media.py
    │   ├── verifier.py
    │   ├── diagnostics.py
    │   └── config.py
    │
    └── future/
```

当前 Facebook Adapter 经过 PoC 已形成较深继承链。正式 V1 应逐步改成组合式模块，而不是继续增加更多 Adapter 子类。

---

# 11. V1 功能边界

## V1 要做

- 总览
- 素材中心
- iX账号中心 + 分组
- Channel 模型
- 流程中心
- Facebook Flow Revision / Step
- 发布中心
- 立即发布
- 定时发布
- 多渠道批量发布
- 发布间隔
- 计划中心
- Scheduler
- 任务中心
- Stage / Timeline / 性能数据
- 普通失败重试
- `needs_review` 人工确认
- Browser Warm Session TTL
- 配置中心
- Facebook 平台配置与高级关键词

## 当前不做

- AI 文案生成
- 评论管理
- 私信管理
- 粉丝管理
- 数据分析中心
- 团队权限 / 审批流
- 云同步 / SaaS 多租户
- 任意 JavaScript/Python/Shell Workflow
- 复杂策略中心

---

# 12. 后续可选模块（V2+）

### 策略中心

未来处理：

```text
随机间隔
发布时间窗口
每日账号上限
循环素材
随机素材
不同账号不同文案
账号优先级
发布频率
```

### 数据中心

未来处理发布数量、成功率、平台/账号表现等统计。

这些暂时不进入 V1 一级导航。

---

# 13. 下一阶段开发顺序

新的聊天窗口 / 新开发阶段必须优先按以下顺序推进：

```text
Phase 1
重做后台信息架构和真实页面路由
→ 8 个中心建立页面骨架

Phase 2
重构领域模型
→ Account / PublishTarget 收敛为 Channel
→ Content 与执行 Job 解耦
→ PublishPlan
→ PublishAttempt
→ Flow / FlowRevision / FlowStep

Phase 3
迁移现有 Facebook PoC 能力
→ iX账号中心
→ 流程中心
→ 发布中心
→ 任务中心

Phase 4
Scheduler
→ 立即发布 / 定时发布统一流水线

Phase 5
批量发布
→ 分组选择
→ 发布间隔
→ Worker 调度
→ Browser Warm Session TTL

Phase 6
任务 Timeline / 性能分析 / 人工确认体验

Phase 7
Facebook Adapter 内部组合式收口

Phase 8
扩展 Instagram / Threads / X 等 Platform Adapter
```

**不要直接在当前长页面 PoC 上继续堆 Scheduler UI。**

---

# 14. 当前本地运行环境

iXBrowser Local API 默认：

```text
http://127.0.0.1:53200/api/v2/
```

Backend：

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
```

Frontend：

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

Facebook 本地流程关键词配置：

```text
data/facebook_flow.json
```

---

# 15. GitHub / 本地开发约定

GitHub `main` 是源代码 Source of Truth。

本地开发环境配置了自动镜像逻辑，源代码目录会定期同步 `origin/main`。运行时数据（数据库、uploads、本地流程配置、`.env` 等）必须保持本地，不被代码镜像清理。

不要把以下内容提交到 Git：

- 密码
- Cookies
- API Token
- Proxy Credentials
- Facebook Session Secrets
- 本地数据库
- 上传媒体
- `.env`

---

# 16. 安全与使用范围

系统仅用于用户有权管理的账号、主页和发布渠道。

明确不做：

- 绕过 CAPTCHA
- 绕过 Checkpoint
- 绕过登录/账号恢复安全机制
- 绕过平台访问控制
- 规避安全挑战

遇到 Facebook 登录、Checkpoint 或安全验证，任务进入人工处理流程。

---

# 17. 新聊天接续说明

如果在新的 ChatGPT 对话中继续开发，请先读取本 README，并遵守以下最高优先级产品决策：

```text
V1 一级导航：
总览 / 素材中心 / iX账号中心 / 流程中心 /
发布中心 / 计划中心 / 任务中心 / 配置中心

核心领域模型：
Environment → Channel
Asset
Flow → FlowRevision → FlowStep
PublishPlan → PublishJob → PublishAttempt

核心执行架构：
Scheduler
→ Job Queue
→ Worker Pool
→ Profile Lock
→ Browser Session Pool
→ iXBrowser
→ Flow Engine
→ Platform Adapter
```

当前 Facebook 单次发布 PoC 已经基本完成，**下一步不是重新调研 Facebook 基础发布，也不是直接堆定时功能，而是先按上述体系重构后台产品结构和领域模型。**
