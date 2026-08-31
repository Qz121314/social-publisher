# Phase 10 — 登录基础层 V1

## 目标

把账号登录从“账号表里塞密码/Cookie”改成独立、安全、可扩展的登录基础层，为后续按分组批量恢复登录提供稳定边界。

用户可见界面统一使用中文；英文状态码只保留在代码和数据库内部。

## 已实现

### 1. Windows 安全凭据存储

`CredentialVault` 当前实现为 Windows DPAPI：

```text
Social Publisher
  ↓
CredentialVault
  ↓
Windows DPAPI
  ↓
data/secure/*.bin
```

`data/secure/*` 已加入 `.gitignore`。

普通 SQLite 不保存以下明文：

- 密码
- Cookie JSON
- TOTP Base32 密钥

SQLite 的 `account_auth_configs` 只保存：

- 登录账号标识
- 是否允许 Cookie / 密码 / TOTP
- 是否已配置对应凭据
- Cookie 数量
- 更新时间

### 2. Cookie Session 校验

Cookie 导入只接受 JSON，并按账号平台过滤：

- Facebook：只保留 `facebook.com` 域 Cookie
- Instagram：只保留 `instagram.com` 域 Cookie
- 第三方域名字段直接丢弃
- 未知 Cookie 字段不进入安全存储
- 单账号最大 512 KB / 500 条 Cookie

Cookie 保存成功不等于登录成功。后续 Login Executor 仍必须重新打开平台并验证真实登录身份。

### 3. Login State Machine

当前纯状态机：

```text
opening_profile
  ↓
checking_session
  ├─ 有效 → verifying_identity → success
  └─ 无效
       ↓
restoring_cookies
  ├─ 有效 → verifying_identity
  └─ 无效
       ↓
entering_credentials
  ├─ success → verifying_identity
  ├─ totp_required → submitting_totp
  ├─ other_mfa_required → waiting_for_user
  ├─ checkpoint → checkpoint
  ├─ invalid_credentials → failed
  └─ unknown → needs_review
```

原则：

- 健康 Session 不重新登录
- Checkpoint 不自动重试
- 未知安全状态不自动继续
- 非 TOTP 二次验证默认转人工
- 身份不一致进入 `needs_review`

### 4. TOTP

内置 RFC 6238 TOTP 生成能力，仅用于用户自己配置的 Authenticator Base32 密钥。

短信、邮件、App Approval、Security Key、Checkpoint 不做绕过。

### 5. 中文登录设置 UI

`准备 → 社交账号 → 登录设置` 可配置：

- 登录账号
- Cookie JSON
- 备用密码
- TOTP 密钥
- 是否允许各恢复策略
- 清除已保存的凭据

已保存的密码、Cookie、TOTP 不回显到前端。

## 尚未实现

这一版**没有**把自动登录真正提交到 Facebook / Instagram 页面。

下一轮需要实现：

```text
LoginExecutor
├─ 打开固定 iX Profile
├─ Existing Session Inspector
├─ Cookie Restore
├─ Password Login Adapter
├─ TOTP Handler
├─ MFA / Checkpoint Detector
├─ Identity Verifier
└─ Manual Takeover
```

完成后再把社交账号页的“恢复登录”动作和分组批量任务正式启用。

## 安全边界

- 不绕过 CAPTCHA / Checkpoint / WebAuthn / 平台访问控制。
- 不实现 WebDriver 隐藏、指纹伪装、随机行为模拟等反检测功能。
- Cookie / 密码 / TOTP 仅用于用户有权管理的账号。
- 账号始终使用其固定绑定的 iXBrowser Profile。
