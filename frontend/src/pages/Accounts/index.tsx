import React, { useEffect, useState } from 'react'

import FacebookTargetPanel from '../../FacebookTargetPanel'
import { api, formatDateTime } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'

type BrowserProfile = {
  profile_id: number
  name: string
  group_name?: string | null
  is_available: boolean
  last_seen_at: string
}

export default function AccountsPage() {
  const [profiles, setProfiles] = useState<BrowserProfile[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = async () => setProfiles(await api<BrowserProfile[]>('/api/browser-profiles'))

  useEffect(() => {
    load().catch((error) => setMessage(error instanceof Error ? error.message : String(error)))
  }, [])

  const syncProfiles = async () => {
    setBusy(true)
    setMessage(null)
    try {
      const result = await api<{ fetched: number }>('/api/ixbrowser/sync', { method: 'POST' })
      await load()
      setMessage(`已同步 ${result.fetched} 个 iX 环境。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="iX账号中心"
        title="环境与发布渠道"
        description="统一管理 iXBrowser Environment，以及环境中真实可发布的 Facebook Profile / Page。"
        actions={<><PhaseBadge /><button className="primary" onClick={syncProfiles} disabled={busy}>{busy ? '同步中…' : '同步 iX 环境'}</button></>}
      />

      {message && <div className="notice">{message}</div>}

      <section className="v1-panel">
        <div className="v1-panel-heading"><div><h2>iX Environment</h2><p>Phase 1 只整理信息架构；分组与 Channel 正式模型在 Phase 2 接入。</p></div><span className="v1-muted">{profiles.length} 个环境</span></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>环境</th><th>分组</th><th>状态</th><th>最后同步</th></tr></thead>
            <tbody>
              {profiles.length === 0 ? (
                <tr><td colSpan={4}><div className="empty-state compact-empty"><strong>暂无已同步环境</strong><span>启动 iXBrowser 后点击“同步 iX 环境”。</span></div></td></tr>
              ) : profiles.map((profile) => (
                <tr key={profile.profile_id}>
                  <td><strong>{profile.name}</strong><br /><small>#{profile.profile_id}</small></td>
                  <td>{profile.group_name || '未分组'}</td>
                  <td><span className={`status-dot ${profile.is_available ? '' : 'neutral'}`}></span>{profile.is_available ? '正常' : '不可用'}</td>
                  <td>{formatDateTime(profile.last_seen_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <p className="v1-inline-note">下面保留现有 Facebook Target Actor PoC 管理能力。Phase 2 会将 Account + PublishTarget 收敛为 Channel，再进一步清理这里的旧概念。</p>
      <FacebookTargetPanel />
    </main>
  )
}
