import React, { useEffect, useState } from 'react'

import { api } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'

type AppStatus = {
  ixbrowser: { connected: boolean }
  worker?: { max_workers: number; active_tasks: number }
}

function SettingPanel({ title, description, rows }: { title: string; description: string; rows: [string, string][] }) {
  return (
    <section className="v1-panel">
      <div className="v1-panel-heading"><div><h2>{title}</h2><p>{description}</p></div></div>
      <div className="v1-setting-list">
        {rows.map(([label, value]) => <div className="v1-setting-row" key={label}><span>{label}</span><strong>{value}</strong></div>)}
      </div>
    </section>
  )
}

export default function SettingsPage() {
  const [status, setStatus] = useState<AppStatus | null>(null)

  useEffect(() => {
    api<AppStatus>('/api/status').then(setStatus).catch(() => undefined)
  }, [])

  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="配置中心"
        title="系统配置"
        description="集中管理通用、执行引擎、iXBrowser、平台、存储、日志和高级配置。"
        actions={<PhaseBadge />}
      />

      <p className="v1-inline-note">Phase 1 先建立正式配置分区并展示当前运行值；可持久化 Settings 领域模型将在后续阶段接入。</p>

      <div className="v1-settings-grid">
        <SettingPanel title="通用" description="默认发布行为" rows={[["默认时区", "Local"], ["默认平台", "Facebook"], ["默认发布方式", "立即发布（PoC）"]]} />
        <SettingPanel title="执行引擎" description="Worker 与重试规则" rows={[["Worker 最大并发", String(status?.worker?.max_workers ?? '—')], ["当前运行任务", String(status?.worker?.active_tasks ?? '—')], ["needs_review 自动重试", "禁止"]]} />
        <SettingPanel title="iXBrowser" description="本地浏览器基础设施" rows={[["Local API", "127.0.0.1:53200/api/v2"], ["连接状态", status?.ixbrowser.connected ? "正常" : "未连接"], ["Warm Session TTL", "约 60 秒（V1 目标）"]]} />
        <SettingPanel title="平台配置" description="平台能力与 Flow" rows={[["Facebook 普通帖子", "PoC 已验证"], ["文字 / Emoji", "支持"], ["图片 / 视频", "支持"]]} />
        <SettingPanel title="存储" description="本地运行数据" rows={[["SQLite", "data/social_publisher.db"], ["媒体目录", "data/uploads/"], ["流程关键词", "data/facebook_flow.json"]]} />
        <SettingPanel title="日志与高级" description="技术诊断默认折叠" rows={[["ChromeDriver 技术详情", "高级诊断"], ["Profile Lock", "高级诊断"], ["WorkerTask UUID", "高级诊断"]]} />
      </div>
    </main>
  )
}
