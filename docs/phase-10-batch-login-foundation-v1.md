# Phase 10 — 批量登录任务基础 V1

## 产品路径

```text
IP池 / 账号池准备完成
        ↓
账号池选择分组
        ↓
批量登录
        ↓
冻结当前账号快照
        ↓
BatchTask
        ↓
TaskJob × N
        ↓
按需创建 / 复用固定 iX Profile
        ↓
写入账号固定 SOCKS5
        ↓
复用单账号 LoginExecutor
        ↓
完成 / 只处理异常
```

用户界面不暴露 BatchTask、TaskJob、Target Snapshot 等工程术语。

## SOCKS5 导入

IP池继续支持：

```text
host:port
host:port:username:password
socks5://username:password@host:port
host,port,username,password,label
```

其中四段式是正式受支持格式，例如：

```text
128.241.28.247:37263:LR1LbJaq:AqkY3X3y6U
```

解析为：

- Host: `128.241.28.247`
- Port: `37263`
- Username: `LR1LbJaq`
- Password: `AqkY3X3y6U`

用户名 / 密码仍然进入 Windows DPAPI，不写普通 SQLite。

## 批量任务数据模型

### BatchTask

保存：

- task_type
- source_selection_json
- target_snapshot_json
- status
- total / succeeded / attention / failed 计数
- started_at / finished_at

### TaskJob

一个账号一个 Job，保存：

- account_id
- account_snapshot_json
- profile_id（执行时可补齐）
- status / stage
- result_json / error_message
- attempts / timestamps

任务创建以后，即使账号后来移出或加入分组，已创建 BatchTask 的目标集合不变。

## Runtime 物化

批量导入账号允许 `ix_profile_id = NULL`。

第一次真正需要登录时：

1. 如果已经有固定 iX Profile，继续复用。
2. 如果没有 Profile，账号必须先有固定 SOCKS5。
3. 使用确定性 Profile 名称查找上一次可能已创建但尚未绑定的环境，防止异常重试生成重复环境。
4. 没找到才调用 iX Local API 创建 Profile。
5. SOCKS5 用户名 / 密码从 DPAPI 读取后直接交给 iX。
6. 本地只镜像安全 Profile 元数据。
7. 将 Profile ID 永久绑定回 Account。
8. 进入现有 LoginExecutor。

## 登录执行

继续复用既有策略：

```text
Existing Session
→ Cookie Restore
→ Password
→ TOTP
→ Manual 2FA / Checkpoint
```

健康 Session 不重新登录。

## 并发

BatchTaskRunner V1 最大并发为 3。

点击一个包含数十或数百账号的分组不会同时启动全部 iX 窗口；其余 Job 保持 queued。

同一账号如果已经存在 queued / running 的登录 Job，新批量登录请求会被拒绝，避免同一账号重复进入两个登录任务。

## 异常状态

以下情况进入“需要处理”而不是继续硬跑：

- 未分配 SOCKS5
- SOCKS5 已停用 / 异常
- Profile 正被其他任务占用
- 2FA / Checkpoint
- 当前平台登录执行器尚未适配
- 后台在登录过程中重启

真正执行错误进入失败。

## 当前 UI

账号池支持：

```text
Store A
[批量登录]
```

以及：

```text
选择若干账号
[批量登录]
```

创建后在账号池顶部直接显示当前批量任务的：

- 进度
- 已完成
- 需要处理
- 失败
- 未完成 Job 当前阶段

后续运行中心会统一吸收所有 BatchTask 历史。
