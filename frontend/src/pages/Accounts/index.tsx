import React, { useEffect, useMemo, useState } from 'react'

import FacebookTargetPanel from '../../FacebookTargetPanel'
import InstagramChannelPanel from '../../InstagramChannelPanel'
import { api, formatDateTime } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'

type BrowserProfile = {
  profile_id: number
  name: string
  group_name?: string | null
  is_available: boolean
  last_seen_at: string
}

type Channel = {
  id: string
  profile_id: number
  platform: string
  target_name: string
  target_type: string
  enabled: boolean
  health_status: string
  last_checked_at?: string | null
}

const healthLabels: Record<string, string> = {
  healthy: '正常',
  ok: '正常',
  running: '正在运行',
  unknown: '未检查',
  unconfigured: '未配置',
  warning: '需要确认',
  error: '异常',
  needs_login: '需要登录',
}

function targetTypeLabel(channel: Channel) {
  if (channel.platform === 'facebook') return channel.target_type === 'page' ? '公共主页' : '个人主页'
  if (channel.platform === 'instagram') return 'Instagram 账号'
  return channel.target_type
}

export default function AccountsPage() {
  const [profiles, setProfiles] = useState<BrowserProfile[]>([])
  const [channels, setChannels] = useState<Channel[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const loadProfiles = async () => setProfiles(await api<BrowserProfile[]>('/api/browser-profiles'))
  const loadChannels = async () => setChannels(await api<Channel[]>('/api/channels'))
  const load = async () => Promise.all([loadProfiles(), loadChannels()])

  useEffect(() => {
    load().catch((error) => setMessage(error instanceof Error ? error.message : String(error)))
    const timer = window.setInterval(() => loadChannels().catch(() => undefined), 3000)
    return () => window.clearInterval(timer)
  }, [])

  const profileById = useMemo(
    () => new Map(profiles.map((profile) => [profile.profile_id, profile])),
    [profiles],
  )

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
        title="环境与多平台发布渠道"
        description="Environment 负责浏览器环境；Channel 代表 Facebook / Instagram 等真实可执行发布身份。"
        actions={<><PhaseBadge>Phase 8</PhaseBadge><button className="primary" onClick={syncProfiles} disabled={busy}>{busy ? '同步中…' : '同步 iX 环境'}</button></>}
      />

      {message && <div className="notice">{message}</div>}

      <section className="v1-panel">
        <div className="v1-panel-heading"><div><h2>发布渠道 Channel</h2><p>发布中心只选择 Channel，不直接依赖裸 iX profile_id。</p></div><span className="v1-muted">{channels.length} 个渠道</span></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>iX 环境</th><th>分组</th><th>平台</th><th>发布目标</th><th>状态</th><th>最后检查</th></tr></thead>
            <tbody>
              {channels.length === 0 ? (
                <tr><td colSpan={6}><div className="empty-state compact-empty"><strong>暂无 Channel</strong><span>在下方平台配置中识别发布身份后，会自动生成正式 Channel。</span></div></td></tr>
              ) : channels.map((channel) => {
                const profile = profileById.get(channel.profile_id)
                const label = channel.enabled ? (healthLabels[channel.health_status] ?? channel.health_status) : '已停用'
                return (
                  <tr key={channel.id}>
                    <td><strong>{profile?.name || `iX #${channel.profile_id}`}</strong><br /><small>#{channel.profile_id}</small></td>
                    <td>{profile?.group_name || '未分组'}</td>
                    <td><strong>{channel.platform === 'instagram' ? 'Instagram' : channel.platform === 'facebook' ? 'Facebook' : channel.platform}</strong></td>
                    <td><strong>{channel.platform === 'instagram' ? `@${channel.target_name}` : channel.target_name}</strong><br /><small>{targetTypeLabel(channel)}</small></td>
                    <td><span className={`status-dot ${channel.enabled ? '' : 'neutral'}`}></span>{label}</td>
                    <td>{formatDateTime(channel.last_checked_at)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="v1-panel">
        <div className="v1-panel-heading"><div><h2>iX Environment</h2><p>环境只描述浏览器容器、分组和可用性，不承担具体平台发布身份语义。</p></div><span className="v1-muted">{profiles.length} 个环境</span></div>
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

      <InstagramChannelPanel />

      <p className="v1-inline-note">Facebook 仍保留经过实测的 Target Actor 扫描 / 配置工具；Instagram 使用 ds_user_id 作为稳定身份门禁。两个平台最终都同步为统一 Channel。</p>
      <FacebookTargetPanel />
    </main>
  )
}
