# Phase 10 — Unified Resource Entry V1

## Product rule

IP池、账号池、素材池必须同时支持：

```text
录入
├─ 单个新增
└─ 批量导入

操作
├─ 单个操作
├─ 当前选择批量操作
└─ 分组 / 集合操作
```

单个和批量只是入口不同，底层必须写入同一资源模型，不能维护两套数据结构。

## IP池

- 单个：`POST /api/proxy-pool`
- 批量：`POST /api/proxy-pool/import`
- 支持 `IP:Port:Username:Password`
- Proxy 用户名 / 密码继续由 Windows DPAPI 保存

## 账号池

- 单个：`POST /api/account-pool`
- 批量：`POST /api/account-pool/import`
- 单个和批量都允许账号在没有 iX Profile 的情况下进入账号池
- Password / Cookie / TOTP 继续进入 Credential Vault
- iX Profile 仍然在首次任务执行时按需创建并长期绑定

## 素材池

新增独立 `Asset` Source 模型：

```text
Asset
├─ text
├─ image
└─ video
```

创建 Asset 不创建 PublishJob。

入口：

- 单个文案：`POST /api/asset-pool/text`
- 单个图片 / 视频：`POST /api/asset-pool/media`
- 批量文案 CSV：`POST /api/asset-pool/text/import`
- 批量图片 / 视频：`POST /api/asset-pool/media/import`

未来 ContentPackage 组合 Asset；Publish Task 创建时再冻结 `content_snapshot`。

## UI

三个资源池统一顶部入口：

```text
[+ 新增] [批量导入]
```

用户可见文案统一中文。
