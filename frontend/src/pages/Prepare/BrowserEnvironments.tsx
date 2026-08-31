import React, { useEffect, useMemo, useState } from 'react'

import { api, formatDateTime } from '../../app/api'
import { BrowserIcon, SearchIcon } from '../../ui/icons'
import { Button, EmptyState, StatusChip, WorkspaceHeader } from '../../ui/components'
import PrepareNav from './PrepareNav'

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

type BrowserSession = {
  profile_id: number
  attached: boolean
  alive: boolean
  opened_at?: string | null
  last_used_at?: string | null
  managed_by_worker?: boolean
  warm_remaining_seconds?: number | null
  current_url?: string | null
  title?: string | null
  window_count?: number
  error?: string | null
}

type ProfileLock = {
  profile_id: number
  owner_id: string
  task_id?: string | null
  expires_at: string
}

type BrowserSessionResponse = { items: BrowserSession[]; count: number }
type ProfileLockResponse = { items: ProfileLock[]; count: number }
type Filter = 'all' | 'open' | 'available' | 'attention'

const filters: Array<{ value: Filter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'open', label: '已打开' },
  { value: 'available', label: '可用' },
  { value: 'attention', label: '需要检查' },
]

function platformName(value: string) {
  if (value === 'facebook') return 'Facebook'
  if (value === 'instagram') return 'Instagram'
  return value
}

function channelHealthy(channel: Channel) {
  return channel.enabled && ['healthy', 'ok', 'running'].includes(channel.health_status)
}

export default function BrowserEnvironmentsPage() {
  const [profiles, setProfiles] = useState<BrowserProfile[]>([])
  const [channels, setChannels] = useState<Channel[]>([])
  const [sessions, setSessions] = useState<BrowserSession[]>([])
  const [locks, setLocks] = useState<ProfileLock[]>([])
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [selected, setSelected] = useState<number[]>([])
  const [busyProfile, setBusyProfile] = useState<number | null>(null)
  const [batchBusy, setBatchBusy] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = async () => {
    try {
      const [nextProfiles, nextChannels, sessionResult, lockResult] = await Promise.all([
        api<BrowserProfile[]>('/api/browser-profiles'),
        api<Channel[]>('/api/channels'),
        api<BrowserSessionResponse>('/api/browser-sessions'),
        api<ProfileLockResponse>('/api/profile-locks'),
      ])
      setProfiles(nextProfiles)
      setChannels(nextChannels)
      setSessions(sessionResult.items)
      setLocks(lockResult.items)
      setMessage(null)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    }
  }

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 5000)
    return () => window.clearInterval(timer)
  }, [])

  const sessionByProfile = useMemo(() => new Map(sessions.map((item) => [item.profile_id, item])), [sessions])
  const lockByProfile = useMemo(() => new Map(locks.map((item) => [item.profile_id, item])), [locks])
  const channelsByProfile = useMemo(() => {
    const result = new Map<number, Channel[]>()
    channels.forEach((channel) => {
      const list = result.get(channel.profile_id) ?? []
      list.push(channel)
      result.set(channel.profile_id, list)
    })
    return result
  }, [channels])

  const visibleProfiles = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    return profiles.filter((profile) => {
      const session = sessionByProfile.get(profile.profile_id)
      const lock = lockByProfile.get(profile.profile_id)
      const profileChannels = channelsByProfile.get(profile.profile_id) ?? []
      const hasChannelIssue = profileChannels.some((channel) => channel.enabled && !channelHealthy(channel))

      if (filter === 'open' && !session?.alive) return false
      if (filter === 'available' && !profile.is_available) return false
      if (filter === 'attention' && profile.is_available && !lock && !hasChannelIssue && session?.alive !== false) return false

      if (!keyword) return true
      const channelText = profileChannels.map((channel) => `${channel.platform} ${channel.target_name}`).join(' ')
      return `${profile.name} ${profile.group_name ?? ''} ${profile.profile_id} ${channelText}`.toLowerCase().includes(keyword)
    })
  }, [profiles, search, filter, sessionByProfile, lockByProfile, channelsByProfile])

  const selectedSet = useMemo(() => new Set(selected), [selected])
  const allVisibleSelected = visibleProfiles.length > 0 && visibleProfiles.every((profile) => selectedSet.has(profile.profile_id))

  const toggleProfile = (profileId: number) => {
    setSelected((current) => current.includes(profileId)
      ? current.filter((id) => id !== profileId)
      : [...current, profileId])
  }

  const toggleVisible = () => {
    if (allVisibleSelected) {
      const visibleIds = new Set(visibleProfiles.map((profile) => profile.profile_id))
      setSelected((current) => current.filter((id) => !visibleIds.has(id)))
      return
    }
    setSelected((current) => Array.from(new Set([...current, ...visibleProfiles.map((profile) => profile.profile_id)])))
  }

  const syncProfiles = async () => {
    setSyncing(true)
    setMessage(null)
    try {
      const result = await api<{ fetched: number }>('/api/ixbrowser/sync', { method: 'POST' })
      await load()
      setMessage(`已从 iXBrowser 同步 ${result.fetched} 个环境。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setSyncing(false)
    }
  }

  const runProfileAction = async (profileId: number, action: 'open' | 'probe' | 'close') => {
    setBusyProfile(profileId)
    setMessage(null)
    try {
      await api(`/api/browser-profiles/${profileId}/${action}`, { method: 'POST' })
      await load()
      setMessage(action === 'open'
        ? `iX #${profileId} 已打开并附加到本地 Runtime。`
        : action === 'close'
          ? `iX #${profileId} 已关闭。`
          : `iX #${profileId} 会话探测完成。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyProfile(null)
    }
  }

  const runBatch = async (action: 'open' | 'probe' | 'close') => {
    if (selected.length === 0) return
    if (action === 'open' && selected.length > 4) {
      setMessage('为避免一次启动过多 Chromium 环境，批量打开一次最多选择 4 个环境。')
      return
    }
    setBatchBusy(true)
    setMessage(null)
    let succeeded = 0
    const failed: number[] = []
    for (const profileId of selected) {
      const session = sessionByProfile.get(profileId)
      if (action === 'probe' && !session?.alive) continue
      try {
        await api(`/api/browser-profiles/${profileId}/${action}`, { method: 'POST' })
        succeeded += 1
      } catch {
        failed.push(profileId)
      }
    }
    await load()
    setBatchBusy(false)
    setMessage(failed.length > 0
      ? `批量操作完成：成功 ${succeeded}，失败 ${failed.length}（iX ${failed.map((id) => `#${id}`).join('、')}）。`
      : `批量操作完成：成功处理 ${succeeded} 个环境。`)
  }

  const openedCount = sessions.filter((item) => item.alive).length
  const availableCount = profiles.filter((item) => item.is_available).length
  const lockedCount = locks.length

  return (
    <main className="prepare-workspace">
      <WorkspaceHeader
        title="浏览器环境"
        description="管理 iXBrowser Profile 与当前本地会话。账号身份属于社交账号层，Proxy / IP 将由独立网络服务补齐。"
        actions={(
          <>
            <Button onClick={load}>刷新</Button>
            <Button variant="primary" onClick={syncProfiles} disabled={syncing}>{syncing ? '同步中…' : '同步 iX 环境'}</Button>
          </>
        )}
      />
      <PrepareNav />

      {message && <div className="prepare-message">{message}</div>}

      <div className="environment-summary-strip">
        <div><span>已同步</span><strong>{profiles.length}</strong><small>iX Profiles</small></div>
        <div><span>可用</span><strong>{availableCount}</strong><small>最近一次同步存在</small></div>
        <div><span>已打开</span><strong>{openedCount}</strong><small>Runtime Sessions</small></div>
        <div><span>任务占用</span><strong>{lockedCount}</strong><small>Profile Locks</small></div>
      </div>

      <section className="environment-table-shell">
        <div className="environment-toolbar">
          <div className="environment-search">
            <SearchIcon />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索环境、分组或账号…" />
          </div>
          <div className="environment-filters">
            {filters.map((item) => (
              <button key={item.value} type="button" className={filter === item.value ? 'is-active' : ''} onClick={() => setFilter(item.value)}>{item.label}</button>
            ))}
          </div>
        </div>

        {selected.length > 0 && (
          <div className="environment-selection-bar">
            <strong>已选择 {selected.length} 个环境</strong>
            <span>批量打开最多 4 个；被运行任务占用的 Profile 会由后端拒绝人工控制。</span>
            <div>
              <Button onClick={() => runBatch('probe')} disabled={batchBusy}>探测已打开</Button>
              <Button onClick={() => runBatch('open')} disabled={batchBusy}>打开所选</Button>
              <Button variant="danger" onClick={() => runBatch('close')} disabled={batchBusy}>关闭所选</Button>
            </div>
          </div>
        )}

        <div className="environment-table" role="table" aria-label="iXBrowser 环境">
          <div className="environment-row environment-row--head" role="row">
            <div><input type="checkbox" checked={allVisibleSelected} onChange={toggleVisible} aria-label="选择当前列表全部环境" /></div>
            <div>环境</div>
            <div>社交身份</div>
            <div>浏览器会话</div>
            <div>网络 / IP</div>
            <div>最后同步</div>
            <div>操作</div>
          </div>

          {visibleProfiles.length === 0 ? (
            <EmptyState title="没有匹配的浏览器环境" description="可以调整筛选条件，或先启动 iXBrowser 后同步环境。" />
          ) : visibleProfiles.map((profile) => {
            const session = sessionByProfile.get(profile.profile_id)
            const lock = lockByProfile.get(profile.profile_id)
            const profileChannels = channelsByProfile.get(profile.profile_id) ?? []
            const enabledChannels = profileChannels.filter((channel) => channel.enabled)
            const hasChannelIssue = enabledChannels.some((channel) => !channelHealthy(channel))
            const sessionTone = session?.alive ? 'success' : session && !session.alive ? 'danger' : 'neutral'
            const busy = busyProfile === profile.profile_id

            return (
              <div className="environment-row" role="row" key={profile.profile_id}>
                <div><input type="checkbox" checked={selectedSet.has(profile.profile_id)} onChange={() => toggleProfile(profile.profile_id)} aria-label={`选择 ${profile.name}`} /></div>
                <div className="environment-profile-cell">
                  <span className="environment-profile-icon"><BrowserIcon /></span>
                  <div>
                    <strong>{profile.name}</strong>
                    <span>iX #{profile.profile_id} · {profile.group_name || '未分组'}</span>
                  </div>
                </div>
                <div className="environment-identity-cell">
                  {enabledChannels.length === 0 ? (
                    <StatusChip tone="neutral">未配置 Channel</StatusChip>
                  ) : (
                    <>
                      <div className="environment-platforms">
                        {enabledChannels.slice(0, 2).map((channel) => (
                          <span key={channel.id}>{platformName(channel.platform)} · {channel.target_name}</span>
                        ))}
                        {enabledChannels.length > 2 && <span>+{enabledChannels.length - 2}</span>}
                      </div>
                      <StatusChip tone={hasChannelIssue ? 'warning' : 'success'}>{hasChannelIssue ? '身份需检查' : '身份已配置'}</StatusChip>
                    </>
                  )}
                </div>
                <div className="environment-session-cell">
                  <StatusChip tone={lock ? 'warning' : sessionTone}>{lock ? '任务占用' : session?.alive ? '已打开' : session ? '会话异常' : '未打开'}</StatusChip>
                  {session?.alive && <span>{session.title || session.current_url || `${session.window_count ?? 0} 个窗口`}</span>}
                  {lock && <span>锁定至 {formatDateTime(lock.expires_at)}</span>}
                </div>
                <div className="environment-network-cell">
                  <StatusChip tone="neutral">待接入</StatusChip>
                  <span>不读取或猜测 iX 原始 Proxy 凭据</span>
                </div>
                <div className="environment-date-cell">
                  <strong>{profile.is_available ? '可用' : '未发现'}</strong>
                  <span>{formatDateTime(profile.last_seen_at)}</span>
                </div>
                <div className="environment-actions">
                  {!session?.alive ? (
                    <Button variant="secondary" onClick={() => runProfileAction(profile.profile_id, 'open')} disabled={busy || Boolean(lock)}>打开</Button>
                  ) : (
                    <>
                      <Button variant="ghost" onClick={() => runProfileAction(profile.profile_id, 'probe')} disabled={busy || Boolean(lock)}>探测</Button>
                      <Button variant="secondary" onClick={() => runProfileAction(profile.profile_id, 'close')} disabled={busy || Boolean(lock)}>关闭</Button>
                    </>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </section>
    </main>
  )
}
