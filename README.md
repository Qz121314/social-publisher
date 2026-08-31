# Social Publisher

本地运行的 **Windows 社交媒体矩阵管理与自动发布工作台**。

当前技术核心：**React + TypeScript + FastAPI + SQLite + iXBrowser Local API + Selenium**。桌面版目标：**Tauri 2 + React/TypeScript + Python/FastAPI sidecar**。

> 当前阶段：**Phase 10 — Resource Pools + Desktop Product Migration**。

---

## 1. 产品定位

Social Publisher 的正式定位：

> **Social Publisher 是资源、任务和异常处理的主工作台；iXBrowser 只提供真实隔离浏览器环境。**

用户长期操作的对象只有：

```text
IP池
账号池
素材池
任务
结果
```

而不是：

```text
iX Profile
WebDriver
WorkerTask
Job ID
FlowRevision
SDK
```

### 核心原则

1. **能在 Social Publisher 完成的操作，不要求用户回到 iXBrowser 管理界面。**
2. **iXBrowser 是 Browser Runtime Provider，不是业务工作台。**
3. **登录、检查、发布始终发生在真实 iXBrowser Profile 窗口中。** React 不模拟 Facebook / Instagram 登录页。
4. **资源先准备，Runtime 后创建。** 批量导入账号时不要求提前创建 iX Profile。
5. **账号最终固定绑定一个长期复用的 iX Profile 和稳定 SOCKS5。** 不在每次任务随机更换。
6. **分组是批量任务一级选择单位。** 用户正常路径尽量保持：`选组 → 动作 → 自动执行 → 只处理异常`。
7. **健康 Session 不主动重新登录。** “批量登录”实际是批量检查并恢复登录状态。
8. **任务创建后冻结目标和内容快照。** 后续资源池变化不能静默影响已创建任务。
9. **用户可见 UI 统一使用中文。** 英文领域名仅保留在代码、数据库和开发文档。
10. 不绕过 CAPTCHA、Checkpoint、MFA、安全挑战或平台访问控制。

---

## 2. V1 产品架构

```text
                    Social Publisher
                           │
          ┌────────────────┼────────────────┐
          │                │                │
        IP池             账号池            素材池
          │                │                │
          └────────────────┼────────────────┘
                           ↓
                        任务系统
                           │
          ┌────────────────┼────────────────┐
          │                │                │
       登录任务        账号维护任务        发帖任务
          │                │                │
          └────────────────┼────────────────┘
                           ↓
                        运行中心
                           ↓
                        检查中心
                           ↓
                    iXBrowser Runtime
```

正式一级导航：

```text
工作台
准备
发布
运行
检查
────────
设置
```

### 准备

```text
准备
├─ 概览
├─ IP池
├─ 账号池
├─ 素材池
└─ 自动化流程
```

`浏览器环境` 保留为高级运行诊断页面，不再是账号录入前置步骤。

---

## 3. Resource Layer

### 3.1 IP池

IP池管理可复用 SOCKS5：

```text
ProxyEndpoint
├─ id
├─ protocol = socks5
├─ host
├─ port
├─ label
├─ credential refs
├─ health status
├─ exit IP
├─ country / region
├─ latency
└─ assigned accounts
```

支持：

- TXT / CSV / 粘贴批量导入
- `host:port`
- `host:port:username:password`
- `socks5://username:password@host:port`
- CSV `host,port,username,password,label`
- 批量删除未分配 IP
- 账号池批量自动分配 IP
- 后续接入批量 SOCKS5 健康检测 / 出口 IP 检测

安全规则：

- SOCKS5 Host / Port 可以进入 SQLite。
- Proxy Username / Password 不进入普通 SQLite。
- Windows 使用 DPAPI 保存代理凭据。

### 3.2 账号池

账号池是主要业务资源：

```text
AccountGroup
    ↓
SocialAccount / Account
    ├─ Cookie
    ├─ Password
    ├─ TOTP
    ├─ ProxyAssignment
    ├─ BrowserProfile（运行时按需创建）
    └─ Channel / Publish Identity
```

批量导入 CSV 标准表头：

```text
账号名称,平台,分组,登录账号,密码,2fa,cookie,proxy,备注
```

规则：

- `平台` 当前批量登录主线优先 Facebook，Instagram 保留同一资源模型。
- `分组` 不存在时可自动创建。
- `proxy` 可以填写 IP池 ID 或 `host:port`。
- Cookie / Password / TOTP 直接进入 Credential Vault。
- 批量导入完成时 `ix_profile_id` 可以为空。
- 点击后续批量登录时，系统才为缺少 Runtime 的账号创建固定 iX Profile。

### 3.3 素材池

素材池最终统一管理：

```text
素材池
├─ 文案
├─ 图片
├─ 视频
├─ 内容组合 ContentPackage
└─ 素材分组 / 标签
```

`ContentPackage` 是实际可发布组合：

```text
产品 A · FB-01
├─ 文案
├─ 图片 01 / 02 / 03
├─ 平台
└─ 标签
```

素材池是可编辑 Source；创建任务以后必须冻结 `content_snapshot`。

---

## 4. 账号与 Runtime 的正确关系

账号资源和 iX 环境不是同一个对象：

```text
Account
= 业务账号资源

BrowserProfile
= iX 真实指纹浏览器运行环境

Channel
= 账号下真实可执行发布身份
```

账号生命周期：

```text
批量导入账号
↓
加入分组
↓
分配固定 SOCKS5
↓
状态 = 已准备
↓
创建批量登录任务
↓
若没有 iX Profile → 自动创建
↓
把固定 SOCKS5 写入该 Profile
↓
打开真实 iXBrowser 窗口
↓
恢复登录
↓
身份验证
↓
长期复用该 Profile
```

因此：

> **账号池可以先存在，iX Profile 不必先存在。**

---

## 5. 登录策略

默认 Login State Machine：

```text
固定 iX Profile
      ↓
Existing Session
      ↓ 无效
Cookie Restore
      ↓ 无效
Password
      ↓
TOTP
      ↓
Manual MFA / Checkpoint
      ↓
Identity Verify
```

优先级：

1. Existing Session
2. Cookie / Session Restore
3. Username / Password
4. Built-in TOTP
5. Manual MFA / Checkpoint

### 2FA

可自动处理：

- 用户自己配置的 TOTP Authenticator Secret

默认人工：

- SMS
- Email Code
- App Approval
- Security Key / WebAuthn
- Checkpoint
- 未知 Security Challenge

### 身份确认

Facebook 登录成功后必须验证真实登录账号身份，例如 `c_user`。

```text
当前身份
==
已确认账号身份
```

不一致立即停止，不自动覆盖绑定。

---

## 6. 批量任务

资源池完成后，用户不应该再逐个账号操作。

例如：

```text
Store A
50 个账号

[批量登录]
[账号维护]
[发布]
```

内部：

```text
Group
↓
TargetResolver
↓
冻结目标 Snapshot
↓
BatchTask
↓
TaskJob × N
↓
TaskAttempt
```

发布领域继续复用：

```text
PublishPlan
↓
PublishJob × N
↓
PublishAttempt
```

### Target Snapshot

任务创建时冻结当时具体账号 / Channel 列表。

如果任务创建后又把新账号加入分组，旧任务不会自动扩大目标范围。

### 账号维护 / 养号任务

产品层定义为**可配置的正常账号维护流程**，例如：

- 检查登录状态
- 打开指定页面
- 检查账号状态
- 按计划发布已有内容
- 必要时人工处理异常

不实现：

- WebDriver 隐藏
- 指纹伪造用于逃避识别
- 模拟随机鼠标轨迹用于规避检测
- CAPTCHA / Checkpoint 绕过

---

## 7. iXBrowser Runtime

```text
Social Publisher
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
```

Runtime 负责：

- create profile
- update profile
- open / close
- SOCKS5 configuration
- Browser Session Pool
- Profile Lock
- Selenium attach
- 后续 Windows 窗口置前 / 排列

正常用户不需要频繁进入 iXBrowser 管理界面。

---

## 8. 发布领域模型

现有成熟发布链继续保留：

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

Source of Truth：

| 对象 | 定位 |
|---|---|
| `Channel` | 正式发布目标 |
| `PublishPlan` | 发布意图 |
| `PublishJob` | 单目标发布任务 |
| `PublishAttempt` | 真实执行记录 |
| `PublishTarget` | 发现 / 兼容对象 |
| `WorkerTask` | Runtime 内部任务 |

不要为了 UI 信息架构重命名或破坏这些领域模型。

---

## 9. 安全与数据边界

普通 SQLite 不保存：

- Account Password
- Cookie Blob
- TOTP Secret
- Proxy Username
- Proxy Password

Windows 本地使用 DPAPI 加密存储。

普通 SQLite 保存：

- 账号资源元数据
- 分组
- IP Host / Port
- Proxy / Profile / Channel 关系
- 凭据是否已配置
- 健康状态
- 任务 / 运行 / 结果记录

不允许把 iX Profile 原始 payload 整包复制进数据库；只镜像安全白名单字段。

---

## 10. 当前已实现

截至当前 Phase 10：

- React Desktop UI Foundation
- 工作台 / 准备 / 检查新信息架构
- AccountGroup
- 账号分组工作台
- iX Profile 同步 / 创建 / 打开 / 关闭 / 探测
- SOCKS5 通过 iX Local API 配置
- Browser Session Pool
- Profile Lock
- Windows DPAPI Credential Vault
- Cookie 安全存储与域名过滤
- Password / TOTP 安全存储
- Facebook 单账号 LoginExecutor
- Existing Session → Cookie → Password → TOTP → 人工处理
- Facebook 登录身份确认
- **IP池数据模型与批量导入基础**
- **账号池允许在没有 iX Profile 时先导入资源**
- **账号 CSV 批量导入基础**
- **账号批量自动分配未占用 IP 基础**

保留的高级兼容入口：

- `/prepare/environments`：iXBrowser 运行环境诊断
- 单账号手工创建 + iX 环境 onboarding API

这些不再是主业务路径。

---

## 11. 接下来开发顺序

```text
1. IP池真实批量健康检测 / 出口 IP
2. 账号池导入体验和批量编辑收口
3. BatchTask / TaskJob 基础
4. 选择分组 → 批量登录
5. 批量登录时自动创建 iX Profile + 写入固定 SOCKS5
6. 运行中心展示批量登录进度
7. 2FA / Checkpoint → 检查中心人工处理
8. 素材池 ContentPackage
9. 分组 → 批量发帖
10. 账号维护任务
11. Tauri 2 Windows Desktop Shell / Window Manager
12. Messenger Relay：按 `docs/messenger-relay-v1.md` 从 MR-0 安全审计和 POC 开始
```

Messenger Relay 已列为正式后续能力，但当前不打断发布主线；待现有发布能力稳定后按独立 MR 阶段开发。

---

## 12. 开发约束

- 用户界面统一中文。
- GitHub `main` 是源码 Source of Truth。
- SQLite 是 Scheduler / Task 的本地 Source of Truth。
- 不把 CI 通过描述成真实 Windows / iXBrowser / Facebook 已经运行验证。
- 真实平台行为必须在本机 iXBrowser 环境中实测。
- 不为了“优化”重新设计已经稳定的发布领域模型。
- 新功能优先复用资源池、任务引擎、Snapshot、Lock、Browser Session Pool。
- 清理旧入口必须在新路径完成迁移和验证后进行。

详细 Phase 10 设计见 `docs/`。

---

## 13. Messenger Relay（正式规划）

Social Publisher 后续增加独立 `Messenger Relay` 领域，用于把 Facebook Page 私信双向中继到 `customer-service`。

核心链路：

```text
Facebook Messenger
        ↕
Social Publisher Messenger Relay
        ↕
customer-service
        ↓
现有分流规则 / Conversation Ownership / ACL
        ↓
客服 A / B / C / D / E
```

职责边界：

- Social Publisher 负责 Facebook Account、固定 iX Profile、Session、Page Identity、私信监听和消息发送。
- `customer-service` 继续作为分流规则、客服状态、Conversation 归属、会话隔离和客服工作台的唯一 Source of Truth。
- Messenger Relay 本身不实现自动聊天机器人，不重新实现客服分流。
- FastAPI 作为控制面；Facebook Messenger 数据面使用独立 Relay Worker，V1 计划以 Node.js 22+ 和可替换 `FacebookTransport` 抽象实现。
- V1 首先本地运行，复用现有 iXBrowser 环境；先完成单账号 / 单 Page 双向 POC，再验证单账号 / 三 Page、多 Page Identity、消息去重、MQTT/WebSocket 重连和长期稳定性。
- 一个 Facebook Account 固定对应一个 iX Profile、独立 Session 和独立 Relay Worker；一个 Account 可以管理多个 Pages。
- Cookie / AppState / Password 等敏感信息不得进入普通 SQLite 或普通日志，继续复用 Credential Vault / DPAPI 安全边界。
- 不绕过 CAPTCHA、Checkpoint、MFA 或平台安全挑战。
- 本地 24h → 72h → 7 天稳定性验证通过后，再考虑多账号和 VPS 长期运行。

完整要求：[`docs/messenger-relay-v1.md`](docs/messenger-relay-v1.md)。
