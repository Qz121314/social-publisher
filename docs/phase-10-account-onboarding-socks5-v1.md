# Phase 10 — Account Onboarding + SOCKS5 V1

## 目标

把原来分散的“新建 iX 环境 / 网络 IP / 添加社交账号 / 打开浏览器登录”收成一条用户流程：

```text
添加账号
  ↓
新建独立 iX Profile（默认）
  ↓
可选 SOCKS5
  ↓
创建 Account 绑定
  ↓
打开真实 iXBrowser 窗口
  ↓
Facebook / Instagram 登录
```

`绑定已有 iX 环境` 保留为高级导入路径，不再是添加账号的默认流程。

## 产品边界

- Social Publisher 是账号、环境、网络和任务的工作台。
- iXBrowser 仍然拥有真实 Profile 与浏览器窗口。
- 登录页面始终是 iXBrowser 中真实的 Facebook / Instagram 页面，React 不模拟平台登录页。
- SOCKS5 是 BrowserProfile 的运行配置，不再建设单独的“网络 / IP”业务中心。
- `/prepare/network` 只保留兼容跳转，导航入口已删除。

## SOCKS5

V1 只开放自定义 SOCKS5：

```text
Host
Port
Username（可选）
Password（可选）
```

通过 `ixbrowser-local-api` 官方 `Proxy` / `update_profile_to_custom_proxy_mode` 能力写入 iX Profile。

### 数据安全

Social Publisher 普通 SQLite 仅镜像用于运维展示的非敏感字段：

```text
proxy_type
proxy_ip
proxy_port
real_ip
```

明确不镜像：

```text
proxy_user
proxy_password
平台密码
TOTP Secret
Cookie
```

代理用户名和密码仅在创建/修改请求期间传给本机 iXBrowser Local API，不由 Social Publisher 普通数据库持久化，也不在 UI 中回显已有值。

## 添加账号

默认：

```text
账号名称
平台
账号分组
环境模式 = 新建独立环境
环境名称（可选，默认账号名称）
SOCKS5（可选）
创建后立即打开 = 是
```

后端 `POST /api/accounts/onboard` 负责串联：

```text
create iX Profile
→ sync/materialize BrowserProfile
→ create Account(status=needs_login)
→ browser_sessions.open(profile_id)
```

如果 iX 已创建 Profile，但没有返回可绑定的 Profile ID，接口会明确停止并要求“同步后绑定已有环境”，不会建议再次点击创建，避免重复 Profile。

如果 Account 已经创建但浏览器打开失败，响应会返回 `open_error`。前端明确提示不要重复创建，可从“浏览器环境”再次打开。

## 环境网络管理

浏览器环境列表直接显示：

```text
SOCKS5 / 直连
Host:Port
出口 IP
```

`PUT /api/browser-profiles/{profile_id}/proxy` 修改网络配置。

安全约束：

- ProfileLock 存在时拒绝修改。
- iX 环境已打开时拒绝修改，要求先关闭。
- 修改完成后重新同步 BrowserProfile 安全元数据。

## 登录关系

本次不重写 LoginExecutor。账号创建完成后打开的是真实 iX Profile；后续账号行上的“恢复登录”仍复用 Phase 10 Facebook LoginExecutor：

```text
Existing Session
→ Cookie Restore
→ Password
→ TOTP
→ Manual MFA / Checkpoint
→ Confirm / Verify c_user identity
```

因此创建和恢复登录使用的是同一个固定 BrowserProfile，不存在 React 登录页或额外 Chromium。

## 不包含

- 不做 CAPTCHA / Checkpoint 绕过。
- 不做 WebDriver 隐藏或浏览器指纹规避。
- 不建设独立 ProxyEndpoint 库。
- 不在 V1 管理代理供应商库存、轮换池或自动换 IP。
- 不把代理凭据写入 Social Publisher SQLite。
