import React, { FormEvent, useEffect, useState } from 'react'

import { api } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'

type AppStatus = {
  ixbrowser: { connected: boolean }
  worker?: { max_workers: number; active_tasks: number }
  browser_pool?: {
    total_sessions: number
    warm_sessions: number
    expired_warm_sessions_total: number
    warm_session_ttl_seconds: number
  }
}

type RuntimeSettings = {
  warm_session_ttl_seconds: number
  worker_max_workers: number
  scheduler_poll_interval_seconds: number
  scheduler_batch_size: number
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
  const [runtime, setRuntime] = useState<RuntimeSettings | null>(null)
  const [warmTtl, setWarmTtl] = useState(60)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = async () => {
    const [nextStatus, nextRuntime] = await Promise.all([
      api<AppStatus>('/api/status'),
      api<RuntimeSettings>('/api/settings/runtime'),
    ])
    setStatus(nextStatus)
    setRuntime(nextRuntime)
    setWarmTtl(nextRuntime.warm_session_ttl_seconds)
  }

  useEffect(() => {
    load().catch((error) => setMessage(error instanceof Error ? error.message : String(error)))
  }, [])

  const saveRuntime = async (event: FormEvent) => {
    event.preventDefault()
    if (!Number.isInteger(warmTtl) || warmTtl < 0 || warmTtl > 3600) {
      setMessage('Warm Session TTL 必须是 0–3600 秒之间的整数。')
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      const next = await api<RuntimeSettings>('/api/settings/runtime', {
        method: 'PUT',
        body: JSON.stringify({ warm_session_ttl_seconds: warmTtl }),
      })
      setRuntime(next)
      setWarmTtl(next.warm_session_ttl_seconds)
      setMessage(`Warm Session TTL 已保存为 ${next.warm_session_ttl_seconds} 秒。`)
      await load()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="配置中心"
        title="系统配置"
        description="集中管理执行引擎、iXBrowser、平台与本地运行参数。"
        actions={<PhaseBadge>Phase 5</PhaseBadge>}
      />

      {message && <div className="notice">{message}</div>}
      <p className="v1-inline-note">Phase 5 首次接入可持久化 Runtime Setting：Worker 自己打开的 iXBrowser 在任务结束后可按 TTL 保持热会话；人工打开的浏览器不受自动 TTL 回收影响。</p>

      <div className="v1-settings-grid">
        <SettingPanel title="通用" description="默认发布行为" rows={[["默认时区", "Local / IANA"], ["默认平台", "Facebook"], ["批量发布间隔", "发布时单独设置"]]} />
        <SettingPanel title="执行引擎" description="Worker 与 Scheduler" rows={[["Worker 最大并发", String(runtime?.worker_max_workers ?? status?.worker?.max_workers ?? '—')], ["当前运行任务", String(status?.worker?.active_tasks ?? '—')], ["Scheduler 轮询", runtime ? `${runtime.scheduler_poll_interval_seconds}s` : '—'], ["needs_review 自动重试", "禁止"]]} />

        <section className="v1-panel">
          <div className="v1-panel-heading"><div><h2>iXBrowser</h2><p>本地浏览器生命周期与 Warm Session Pool。</p></div></div>
          <div className="v1-setting-list">
            <div className="v1-setting-row"><span>Local API</span><strong>127.0.0.1:53200/api/v2</strong></div>
            <div className="v1-setting-row"><span>连接状态</span><strong>{status?.ixbrowser.connected ? '正常' : '未连接'}</strong></div>
            <div className="v1-setting-row"><span>当前 Browser Sessions</span><strong>{status?.browser_pool?.total_sessions ?? 0}</strong></div>
            <div className="v1-setting-row"><span>Warm Sessions</span><strong>{status?.browser_pool?.warm_sessions ?? 0}</strong></div>
          </div>
          <form className="v1-runtime-setting-form" onSubmit={saveRuntime}>
            <label className="field-block">
              <span>Warm Session TTL（秒）</span>
              <input type="number" min={0} max={3600} step={1} value={warmTtl} onChange={(event) => setWarmTtl(Number(event.target.value))} />
              <small>默认 60 秒；0 表示任务结束后立即关闭 Worker 管理的浏览器。</small>
            </label>
            <button className="primary" type="submit" disabled={busy}>{busy ? '保存中…' : '保存 TTL'}</button>
          </form>
        </section>

        <SettingPanel title="平台配置" description="平台能力与 Flow" rows={[["Facebook 普通帖子", "已接正式 V1 Flow"], ["文字 / Emoji", "支持"], ["图片 / 视频", "支持"]]} />
        <SettingPanel title="存储" description="本地运行数据" rows={[["SQLite", "data/social_publisher.db"], ["媒体目录", "data/uploads/"], ["Runtime Settings", "SQLite / app_settings"]]} />
        <SettingPanel title="日志与高级" description="技术诊断默认折叠" rows={[["同 Profile 调度", "强制串行"], ["Profile Lock", "数据库支持"], ["WorkerTask UUID", "内部 Runtime"]]} />
      </div>
    </main>
  )
}
