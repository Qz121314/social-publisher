# Messenger Relay V1

## 1. 定位

Messenger Relay 是 Social Publisher 后续新增的 Facebook 私信中继能力。

它不是客服系统，也不是自动回复机器人。

它只负责：

```text
Facebook Messenger
      ↕
Social Publisher Messenger Relay
      ↕
customer-service
```

客服分流、客服在线状态、会话归属、权限隔离、统计等业务逻辑继续由 `customer-service` 负责。

---

## 2. 核心目标

V1 目标：

1. 在本地 Windows 环境中复用现有 iXBrowser Facebook 账号环境。
2. 监听 Facebook Page 新私信。
3. 正确识别 Facebook Account、Page、Thread、Sender、Message。
4. 将入站消息转发到 `customer-service`。
5. 接收 `customer-service` 的客服回复，并发送回正确 Facebook Thread。
6. 保证回复始终使用正确 Facebook Page 身份。
7. 支持一个 Facebook Account 管理多个 Facebook Pages。
8. 支持后续一个 Social Publisher 实例运行多个独立 Facebook Account Relay Worker。
9. Facebook Relay 不承担 Round Robin、客服 ACL 或客服 UI。
10. 后续可迁移到 VPS 长期运行，但 V1 先在本地真实 iXBrowser 环境验证。

---

## 3. 总体架构

```text
                     Facebook Messenger
                              ↕
────────────────────────────────────────────
                 Local Windows Runtime
────────────────────────────────────────────

iXBrowser Profile
      ↓
Facebook Account Session
      ↓
Messenger Relay Worker
      ↓
Relay Manager / FastAPI
      ↓ HTTPS / WSS
────────────────────────────────────────────
                    Cloud
────────────────────────────────────────────
customer-service
      ↓
Conversation / Assignment / ACL
      ↓
客服 A / B / C / D / E
```

Social Publisher 负责 Facebook Channel Runtime；`customer-service` 负责客服业务。

---

## 4. 技术边界

### 4.1 Control Plane

继续由现有 Social Publisher FastAPI 管理：

- Relay Worker 启动 / 停止
- Facebook Account 与 Relay Worker 绑定
- Page 列表和启用状态
- Relay 状态
- Heartbeat
- 日志与异常
- `customer-service` Endpoint 配置
- AUTH_REQUIRED / CHECKPOINT 等人工处理状态

### 4.2 Data Plane

新增独立 Node.js Relay Worker。

建议：

```text
Node.js 22+
FacebookTransport abstraction
MQTT / WebSocket
HTTP client
```

V1 第一套实验 Transport：

```text
FcaTransport
→ VangBanLaNhat/fca-unofficial
```

该依赖只作为 Transport Adapter，不允许让 Social Publisher 业务代码直接依赖其内部 API。

后续允许替换为：

```text
FbchatTransport
PlaywrightTransport
OfficialApiTransport
其他 Messenger Gateway Transport
```

---

## 5. FacebookTransport 接口

Relay 内部必须定义稳定抽象层，例如：

```text
connect()
disconnect()
listenMessages()
sendMessage()
sendAttachment()
markRead()
healthCheck()
```

Social Publisher 和 `customer-service` 不应感知 FCA、MQTT 或 Facebook 内部协议细节。

---

## 6. 账号、Profile、Page、Worker 关系

核心规则：

```text
1 Facebook Account
= 1 固定 iX Profile
= 1 独立 Session
= 1 Relay Account Context
= 1 独立 Relay Worker
```

一个 Facebook Account 可以管理多个 Page：

```text
Account A
├─ Page A1
├─ Page A2
└─ Page A3
```

不要为每个 Page 创建独立 Facebook 登录环境。

未来多账号：

```text
Relay Worker A → Account A → N Pages
Relay Worker B → Account B → N Pages
Relay Worker C → Account C → N Pages
```

不同 Facebook Account 的 Cookie、Session、运行状态和日志必须隔离。

---

## 7. 消息标准模型

入站消息至少标准化为：

```text
channel = facebook
facebook_account_id
page_id
thread_id
sender_id
message_id
timestamp
text
attachments
direction = inbound
```

出站至少包含：

```text
facebook_account_id
page_id
thread_id
conversation_id
message_id / request_id
text
attachments
direction = outbound
```

`page_id + thread_id` 必须能稳定映射到 `customer-service` Conversation。

---

## 8. customer-service 集成规则

Relay 收到新 Facebook Thread：

```text
Facebook
↓
Messenger Relay
↓
customer-service inbound API
↓
查找已有 Conversation
├─ 已存在 → 原 assigned_agent
└─ 不存在 → 执行 customer-service 当前分流规则
```

Relay 不实现：

- Round Robin
- 在线客服选择
- 客服容量
- 会话保护规则
- 客服额度
- 会话 ACL
- 管理员权限

这些逻辑只有 `customer-service` 是 Source of Truth。

客服回复：

```text
Agent
↓
customer-service
↓
Messenger Relay outbound
↓
正确 Facebook Page + Thread
↓
Customer
```

---

## 9. Page Identity Safety

这是 Messenger Relay 的最高优先级安全要求之一。

任何出站回复发送前必须验证：

```text
conversation.page_id
==
relay outbound page_id
==
当前 Facebook Page Context
```

不一致必须拒绝发送并记录错误。

禁止出现：

```text
Page A 的客户
↓
错误地以 Page B 身份回复
```

多 Page 测试必须作为正式验收项。

---

## 10. 稳定性要求

Relay 必须逐步实现：

- MQTT / WebSocket 断线检测
- 自动重连
- Heartbeat
- Worker crash 自动恢复
- Message ID 去重
- Echo message 过滤
- 同 Thread 消息顺序保护
- Relay 重启后 Conversation Mapping 不丢
- Session 失效识别
- AUTH_REQUIRED 状态
- CHECKPOINT 状态
- 发送失败重试与最终失败状态
- 漏消息补偿机制后续设计

不得在认证失败时无限快速重试 Facebook 登录。

---

## 11. 安全与凭据

继续遵守 Social Publisher 当前安全边界：

普通 SQLite 不保存：

- Facebook Password
- Cookie Blob
- AppState / Session Blob
- TOTP Secret
- Proxy Username / Password

Windows 本地优先复用现有 DPAPI Credential Vault。

Relay Worker 只能通过受控接口获取运行所需 Session，不允许把 Cookie/AppState 输出到普通日志。

必须审计第三方非官方 Transport，重点检查：

- 是否上传 Cookie / AppState
- 是否调用未知外部 API
- 是否存在遥测
- 是否动态下载或执行远程代码
- 依赖供应链风险

---

## 12. 与 iXBrowser 的关系

V1 继续坚持：

```text
iXBrowser
= 真实隔离浏览器 Runtime
```

负责：

- 固定 Profile
- Facebook 正常登录
- Cookie / Session 环境
- 代理配置
- MFA / Checkpoint 人工处理

Relay 目标是尽量使用轻量 Session / MQTT 通信，不应长期通过 Selenium 循环点击 Meta Inbox DOM。

如果底层非官方 Transport 不稳定，允许增加 Playwright / Selenium Business Suite Transport 作为后续 fallback，但不作为 V1 首选路径。

---

## 13. 与自动发帖的协同

Messenger Relay 与现有 Facebook 自动发帖共用：

- Account
- AccountGroup
- BrowserProfile
- ProxyAssignment
- Credential Vault
- LoginExecutor
- Browser Session Pool
- Profile Lock
- Channel / Page 身份数据

但业务流程必须隔离：

```text
Publish Domain
!=
Messenger Relay Domain
```

发布失败不得直接导致 Relay 数据丢失；Relay Worker 崩溃不得拖垮发布主进程。

FastAPI 是控制面，Node Relay Worker 是独立数据面。

---

## 14. Profile Lock 与并发

如果 Relay 不需要浏览器窗口长期打开，则发布任务可以正常临时打开固定 iX Profile。

如果某 Transport 需要占用浏览器：

- 必须接入现有 Profile Lock。
- 不允许 Relay 和 Publish Job 同时无协调控制同一 Profile。
- 必须定义暂停 / 恢复 / 共享 Session 的明确策略。

---

## 15. 本地 V1 验收范围

第一轮只做：

```text
1 Windows PC
1 iX Profile
1 Facebook Account
1 Facebook Page
2 个 customer-service Agent
文字消息
```

必须跑通完整闭环：

```text
Customer → Facebook Page
→ Relay 收到
→ customer-service
→ 分配 Agent
→ Agent 回复
→ Relay
→ Facebook Customer 收到
```

第二轮扩大到：

```text
1 Facebook Account
3 Facebook Pages
2~5 Agents
```

重点验证：

- 三个 Page 同时收消息
- `page_id` 正确
- Thread 不串
- 回复 Page Identity 正确
- Message ID 去重
- Relay 重启恢复
- MQTT 自动重连

---

## 16. 稳定性验收

按以下顺序验证：

```text
24 小时
↓
72 小时
↓
7 天
```

记录：

- 入站延迟
- 出站延迟
- MQTT 断线次数
- 自动恢复次数
- 漏消息
- 重复消息
- Session 失效
- Checkpoint
- Page Identity Error
- Worker crash

在 7 天测试通过前，不把该非官方 Transport 定义为生产稳定能力。

---

## 17. 后续 VPS 方向

V1 验证成功后才进入 VPS 迁移。

长期结构：

```text
VPS
├─ Account A Runtime / Relay Worker
├─ Account B Runtime / Relay Worker
└─ Account C Runtime / Relay Worker
        ↓
customer-service / Cloudflare
```

每个 Facebook Account 仍保持独立 Profile、独立 Session、独立 Worker 和稳定网络出口。

VPS 迁移属于后续阶段，不阻塞本地 Messenger Relay V1。

---

## 18. 明确不做

Messenger Relay V1 不实现：

- 自动聊天机器人
- AI 自动客服
- 私信营销群发
- CAPTCHA 绕过
- Checkpoint 绕过
- MFA 绕过
- 自动规避平台安全控制
- 为逃避平台识别而伪造随机浏览器指纹
- 在 Social Publisher 内重新实现 customer-service 分流系统

---

## 19. 后续开发顺序

建议在现有发布主线稳定后进入：

```text
Phase MR-0  第三方 Transport 安全审计
Phase MR-1  单账号 / 单 Page 收消息 POC
Phase MR-2  单 Page 双向收发闭环
Phase MR-3  接入 customer-service
Phase MR-4  单账号 / 三 Page 验证
Phase MR-5  去重 / 重连 / Heartbeat / 状态机
Phase MR-6  图片和基础附件
Phase MR-7  72 小时 / 7 天稳定性测试
Phase MR-8  多 Facebook Account Worker 隔离
Phase MR-9  Social Publisher Relay UI
Phase MR-10 VPS 迁移验证
```

当前阶段只记录为正式规划要求，不打断现有 Social Publisher 发布功能开发顺序。
