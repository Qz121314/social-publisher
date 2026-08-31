# Phase 10 — Facebook 单账号登录执行器 V1

## 产品规则

用户可见界面统一使用中文。Facebook、iXBrowser、Cookie、TOTP 等产品/技术专名可以保留原名，但操作、状态、错误、确认和帮助文案必须中文化。

用户正常操作保持最短路径：

```text
社交账号
→ 恢复登录
→ 自动执行
→ 只有必要时人工处理
```

不新增独立“登录中心”。

## 真实执行边界

登录始终发生在账号绑定的真实 iXBrowser Profile 窗口：

```text
Social Publisher
→ Account
→ fixed iX Profile
→ BrowserSessionManager
→ Selenium / CDP attach
→ Facebook
```

Social Publisher 不创建独立 Chrome，也不在 React 中模拟 Facebook 登录页。

## V1 登录顺序

```text
打开固定 iX 环境
→ 检查 Existing Session
→ Cookie Restore
→ Username / Password
→ Authenticator TOTP
→ Verify Login Identity
```

如果出现以下状态，停止自动处理并转人工：

- SMS / Email 验证码
- App Approval
- Security Key / WebAuthn
- Facebook Checkpoint
- 未知 Security Challenge
- 无法确认页面状态

不实现 CAPTCHA / Checkpoint 绕过、WebDriver 掩码、指纹伪装或反检测逻辑。

## Facebook 登录身份与发布身份分离

Facebook 登录账号使用 `c_user` 作为已观察的登录身份 ID。

```text
Account Login Identity
= c_user

Publish Channel / Page Identity
= Channel / target actor
```

二者不可混用。Page 身份不能覆盖登录账号身份。

新增 `AccountLoginIdentity`：

```text
account_id
platform_identity_id
confirmed_at
last_verified_at
```

第一次检测到有效登录时不会静默绑定身份：

```text
检测到 c_user
→ 保留 iXBrowser 窗口
→ 用户确认当前账号
→ 保存 AccountLoginIdentity
```

后续登录恢复：

```text
observed c_user == confirmed identity
→ 登录成功

observed c_user != confirmed identity
→ needs_review
→ 停止后续操作
```

系统不会自动覆盖已经确认的身份绑定。

## Cookie 恢复

Cookie 从 Windows DPAPI CredentialVault 解密后，仅在该账号固定 iX Profile 中恢复。

使用 CDP `Network.setCookie`，原因是它可以正确恢复 `.facebook.com` 等 Domain Cookie，同时避免依赖 Selenium 当前页面 Host 的限制。

Cookie 恢复后必须重新打开 Facebook 并重新判断：

- 是否登录
- 是否进入 MFA / Checkpoint
- 当前 `c_user`

“Cookie 写入成功”不等于“登录成功”。

## Password + TOTP

账号密码仅在 Existing Session 和 Cookie 无效后使用。

标准 Authenticator TOTP 只有在页面明确出现 Authenticator / Code Generator 等可确认信号时才自动提交。

通用验证码框、短信、邮件和设备批准不会被误当成 TOTP 自动填写。

## Profile Lock

单账号登录操作使用现有 `ProfileLock`：

```text
one iX Profile
→ one browser-sensitive operation at a time
```

如果环境正在执行发布或其他浏览器任务，登录接口返回冲突，不抢占、不并发操作同一窗口。

## 浏览器关闭策略

- 成功且本次由 LoginExecutor 打开的窗口：可以关闭，Session 已持久存在于固定 Profile。
- 原本就是用户打开的窗口：不主动关闭。
- MFA / Checkpoint / 首次身份确认 / Needs Review：保留窗口供人工检查。

未来批量任务将交给 bounded Worker Pool 和 Browser Session Pool 统一控制并发。

## API

```text
POST /api/accounts/{account_id}/login/recover
POST /api/accounts/{account_id}/login/check
POST /api/accounts/{account_id}/login/confirm-identity
```

原有登录配置：

```text
GET   /api/accounts/auth/{account_id}
PATCH /api/accounts/auth/{account_id}
```

## 当前 UI

`准备 → 社交账号` 每个 Facebook 账号直接显示：

```text
[恢复登录] [登录设置]
```

首次身份确认使用轻量确认弹窗，不跳新页面。

Instagram 暂时只显示未接入，避免假装已经支持真实登录执行。

## CI 范围

CI 可以验证：

- FastAPI 登录路由存在
- `AccountLoginIdentity` 表创建
- Login State Machine 转移
- Facebook 登录页面状态分类
- Authenticator TOTP 与 Checkpoint 的优先级
- 前端 TypeScript / Vite build

CI 不能验证：

- 本机 iXBrowser 是否运行
- 真实 Facebook 页面是否变更
- 真实账号 Cookie 是否有效
- 真实账号密码 / 2FA 是否能完成

因此合并后仍需要 Windows + iXBrowser + 自有 Facebook 测试账号做一次真实单账号测试，才能进入批量登录阶段。
