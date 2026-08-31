import React, { FormEvent, useEffect, useMemo, useState } from 'react'

import { api, formatDateTime } from '../../app/api'
import { BrowserIcon, PlusIcon, SearchIcon } from '../../ui/icons'
import { Button, EmptyState, StatusChip, WorkspaceHeader } from '../../ui/components'
import PrepareNav from './PrepareNav'

type BrowserProfile = {
  profile_id: number
  name: string
  group_name?: string | null
  proxy_type?: string | null
  proxy_ip?: string | null
  proxy_port?: string | null
  real_ip?: string | null
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
type CreateProfileResponse = {
  status: 'created'
  profile_id?: number | null
  name: string
  site_url: string
  proxy_configured?: boolean
  synced: boolean
  opened: boolean
  sync_error?: string | null
  open_error?: string | null
}
type Filter = 'all' | 'open' | 'available' | 'attention'
type StartPage = 'facebook' | 'instagram' | 'blank'

const filters: Array<{ value: Filter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'open', label: '已打开' },
  { value: 'available', label: '可用' },
  { value: 'attention', label: '需要检查' },
]

const startPages: Array<{ value: StartPage; label: string; url: string; description: string }> = [
  { value: 'facebook', label: 'Facebook', url: 'https://www.facebook.com/', description: '创建后直接打开 Facebook' },
  { value: 'instagram', label: 'Instagram', url: 'https://www.instagram.com/', description: '创建后直接打开 Instagram' },
  { value: 'blank', label: '空白页', url: 'chrome://newtab', description: '仅创建基础浏览器环境' },
]

function platformName(value: string) {
  if (value === 'facebook') return 'Facebook'
  if (value === 'instagram') return 'Instagram'
  return value
}

function channelHealthy(channel: Channel) {
  return channel.enabled && ['healthy', 'ok', 'running'].includes(channel.health_status)
}

function hasSocks5(profile: BrowserProfile) {
  return profile.proxy_type?.toLowerCase() === 'socks5' && Boolean(profile.proxy_ip && profile.proxy_port)
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
  const [createOpen, setCreateOpen] = useState(false)
  const [createName, setCreateName] = useState('')
  const [startPage, setStartPage] = useState<StartPage>('facebook')
  const [openAfterCreate, setOpenAfterCreate] = useState(true)
  const [creating, setCreating] = useState(false)
  const [proxyEditor, setProxyEditor] = useState<BrowserProfile | null>(null)
  const [proxyBusy, setProxyBusy] = useState(false)

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
      const networkText = `${profile.proxy_type ?? ''} ${profile.proxy_ip ?? ''} ${profile.proxy_port ?? ''} ${profile.real_ip ?? ''}`
      return `${profile.name} ${profile.group_name ?? ''} ${profile.profile_id} ${channelText} ${networkText}`.toLowerCase().includes(keyword)
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

  const createProfile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const name = createName.trim()
    if (!name) return

    const form = new FormData(event.currentTarget)
    const proxyEnabled = form.get('proxy_enabled') === 'on'
    const proxyHost = String(form.get('proxy_host') ?? '').trim()
    const proxyPortValue = String(form.get('proxy_port') ?? '').trim()
    if (proxyEnabled && (!proxyHost || !proxyPortValue)) {
      setMessage('启用 SOCKS5 后必须填写 Host 和 Port。')
      return
    }

    const selectedStartPage = startPages.find((item) => item.value === startPage) ?? startPages[0]
    setCreating(true)
    setMessage(null)
    try {
      const result = await api<CreateProfileResponse>('/api/ixbrowser/profiles', {
        method: 'POST',
        body: JSON.stringify({
          name,
          site_url: selectedStartPage.url,
          proxy: {
            enabled: proxyEnabled,
            proxy_type: 'socks5',
            host: proxyHost || null,
            port: proxyPortValue ? Number(proxyPortValue) : null,
            username: String(form.get('proxy_username') ?? '').trim() || null,
            password: String(form.get('proxy_password') ?? '') || null,
          },
          open_after_create: openAfterCreate,
        }),
      })

      await load()
      setCreateOpen(false)
      setCreateName('')
      setStartPage('facebook')
      setOpenAfterCreate(true)

      const profileLabel = result.profile_id ? `iX #${result.profile_id}` : result.name
      if (!result.synced) {
        setMessage(`${profileLabel} 已在 iXBrowser 创建，但本地同步未完成。请点击“同步 iX 环境”重新同步。${result.sync_error ? ` ${result.sync_error}` : ''}`)
      } else if (result.open_error) {
        setMessage(`${profileLabel} 已创建，但自动打开失败。环境没有重复创建；可以在列表中再次点击“打开”。 ${result.open_error}`)
      } else if (result.opened) {
        setMessage(`${profileLabel} 已创建并打开${result.proxy_configured ? '，SOCKS5 已写入该 iX 环境' : ''}。`)
      } else {
        setMessage(`${profileLabel} 已创建${result.proxy_configured ? '，SOCKS5 已写入该 iX 环境' : ''}。`)
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setCreating(false)
    }
  }

  const saveProxy = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!proxyEditor || proxyBusy) return
    const form = new FormData(event.currentTarget)
    const enabled = String(form.get('network_mode') ?? 'socks5') === 'socks5'
    const host = String(form.get('proxy_host') ?? '').trim()
    const portValue = String(form.get('proxy_port') ?? '').trim()
    if (enabled && (!host || !portValue)) {
      setMessage('SOCKS5 需要同时填写 Host 和 Port。')
      return
    }

    setProxyBusy(true)
    setMessage(null)
    try {
      await api(`/api/browser-profiles/${proxyEditor.profile_id}/proxy`, {
        method: 'PUT',
        body: JSON.stringify({
          enabled,
          host: enabled ? host : null,
          port: enabled ? Number(portValue) : null,
          username: enabled ? String(form.get('proxy_username') ?? '').trim() || null : null,
          password: enabled ? String(form.get('proxy_password') ?? '') || null : null,
        }),
      })
      await load()
      setProxyEditor(null)
      setMessage(enabled
        ? `iX #${proxyEditor.profile_id} 的 SOCKS5 已更新。代理用户名和密码不会写入 Social Publisher SQLite。`
        : `iX #${proxyEditor.profile_id} 已切换为直连。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setProxyBusy(false)
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
  const socks5Count = profiles.filter(hasSocks5).length
  const lockedCount = locks.length

  return (
    <main className="prepare-workspace">
      <WorkspaceHeader
        title="浏览器环境"
        description="iXBrowser 提供真实环境；SOCKS5、出口 IP、会话与环境绑定在同一工作区管理。"
        actions={(
          <>
            <Button onClick={load}>刷新</Button>
            <Button onClick={syncProfiles} disabled={syncing}>{syncing ? '同步中…' : '同步 iX 环境'}</Button>
            <Button variant="primary" onClick={() => setCreateOpen(true)}><PlusIcon />新建环境</Button>
          </>
        )}
      />
      <PrepareNav />

      {message && <div className="prepare-message">{message}</div>}

      <div className="environment-summary-strip">
        <div><span>已同步</span><strong>{profiles.length}</strong><small>iX Profiles</small></div>
        <div><span>SOCKS5</span><strong>{socks5Count}</strong><small>已配置网络环境</small></div>
        <div><span>已打开</span><strong>{openedCount}</strong><small>Runtime Sessions</small></div>
        <div><span>任务占用</span><strong>{lockedCount}</strong><small>Profile Locks</small></div>
      </div>

      <section className="environment-table-shell">
        <div className="environment-toolbar">
          <div className="environment-search">
            <SearchIcon />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索环境、SOCKS5、出口 IP 或账号…" />
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
            <EmptyState title="没有匹配的浏览器环境" description="可以新建环境并直接配置 SOCKS5，或同步 iXBrowser 中已有环境。" />
          ) : visibleProfiles.map((profile) => {
            const session = sessionByProfile.get(profile.profile_id)
            const lock = lockByProfile.get(profile.profile_id)
            const profileChannels = channelsByProfile.get(profile.profile_id) ?? []
            const enabledChannels = profileChannels.filter((channel) => channel.enabled)
            const hasChannelIssue = enabledChannels.some((channel) => !channelHealthy(channel))
            const sessionTone = session?.alive ? 'success' : session && !session.alive ? 'danger' : 'neutral'
            const busy = busyProfile === profile.profile_id
            const socks5 = hasSocks5(profile)

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
                  <StatusChip tone={socks5 ? 'success' : 'neutral'}>{socks5 ? 'SOCKS5' : '直连'}</StatusChip>
                  {socks5 && <strong>{profile.proxy_ip}:{profile.proxy_port}</strong>}
                  <span>{profile.real_ip ? `出口 IP ${profile.real_ip}` : '出口 IP 尚未检测'}</span>
                </div>
                <div className="environment-date-cell">
                  <strong>{profile.is_available ? '可用' : '未发现'}</strong>
                  <span>{formatDateTime(profile.last_seen_at)}</span>
                </div>
                <div className="environment-actions">
                  <Button variant="ghost" onClick={() => setProxyEditor(profile)} disabled={busy || Boolean(lock) || Boolean(session?.alive)} title={session?.alive ? '先关闭环境再修改 SOCKS5' : '修改 SOCKS5'}>网络</Button>
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

      {createOpen && (
        <div className="environment-create-backdrop" onMouseDown={() => !creating && setCreateOpen(false)}>
          <aside className="environment-create-drawer" role="dialog" aria-modal="true" aria-labelledby="create-environment-title" onMouseDown={(event) => event.stopPropagation()}>
            <form onSubmit={createProfile}>
              <header className="environment-create-header">
                <div>
                  <h2 id="create-environment-title">新建浏览器环境</h2>
                  <p>直接调用 iXBrowser Local API 创建真实 Profile，并可同时写入 SOCKS5。</p>
                </div>
                <button type="button" className="environment-create-close" onClick={() => setCreateOpen(false)} disabled={creating} aria-label="关闭">×</button>
              </header>

              <div className="environment-create-body">
                <label className="environment-field">
                  <span>环境名称</span>
                  <input autoFocus value={createName} onChange={(event) => setCreateName(event.target.value)} placeholder="例如 Store-A-017" maxLength={255} required />
                  <small>用于工作台和 iXBrowser 中识别该环境。创建后保持长期复用。</small>
                </label>

                <fieldset className="environment-start-page">
                  <legend>启动页面</legend>
                  {startPages.map((item) => (
                    <label key={item.value} className={startPage === item.value ? 'is-selected' : ''}>
                      <input type="radio" name="start-page" value={item.value} checked={startPage === item.value} onChange={() => setStartPage(item.value)} />
                      <span><strong>{item.label}</strong><small>{item.description}</small></span>
                    </label>
                  ))}
                </fieldset>

                <section className="environment-proxy-section">
                  <label className="environment-create-toggle environment-proxy-toggle">
                    <input type="checkbox" name="proxy_enabled" />
                    <span><strong>使用 SOCKS5</strong><small>网络配置直接写入该 iX Profile，不另建“网络中心”。</small></span>
                  </label>
                  <div className="environment-proxy-grid">
                    <label className="environment-field"><span>Host</span><input name="proxy_host" placeholder="127.0.0.1 或代理主机" /></label>
                    <label className="environment-field"><span>Port</span><input name="proxy_port" type="number" min="1" max="65535" placeholder="1080" /></label>
                    <label className="environment-field"><span>Username</span><input name="proxy_username" autoComplete="off" placeholder="可选" /></label>
                    <label className="environment-field"><span>Password</span><input name="proxy_password" type="password" autoComplete="new-password" placeholder="可选" /></label>
                  </div>
                  <p className="environment-proxy-security">Social Publisher 只镜像代理类型、Host、Port 和出口 IP；代理用户名与密码不会写入普通 SQLite。</p>
                </section>

                <div className="environment-create-note">
                  <strong>浏览器指纹</strong>
                  <span>继续使用 iXBrowser 自己的 Profile 配置与默认值。工作台不生成、伪造或修改用于规避平台检测的指纹参数。</span>
                </div>

                <label className="environment-create-toggle">
                  <input type="checkbox" checked={openAfterCreate} onChange={(event) => setOpenAfterCreate(event.target.checked)} />
                  <span><strong>创建后立即打开</strong><small>由 iXBrowser 打开真实 Profile 窗口，并附加到本地 Runtime。</small></span>
                </label>
              </div>

              <footer className="environment-create-footer">
                <Button type="button" onClick={() => setCreateOpen(false)} disabled={creating}>取消</Button>
                <Button variant="primary" type="submit" disabled={creating || !createName.trim()}>{creating ? '创建中…' : openAfterCreate ? '创建并打开' : '创建环境'}</Button>
              </footer>
            </form>
          </aside>
        </div>
      )}

      {proxyEditor && (
        <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !proxyBusy && setProxyEditor(null)}>
          <div className="sp-form-dialog environment-network-dialog" role="dialog" aria-modal="true" aria-label="环境网络设置" onMouseDown={(event) => event.stopPropagation()}>
            <form onSubmit={saveProxy}>
              <header><div><span>iXBrowser 网络</span><h2>{proxyEditor.name}</h2></div><button type="button" onClick={() => setProxyEditor(null)} disabled={proxyBusy} aria-label="关闭">×</button></header>
              <div className="account-dialog-body">
                <label><span>网络模式</span><select name="network_mode" defaultValue={hasSocks5(proxyEditor) ? 'socks5' : 'direct'}><option value="socks5">SOCKS5</option><option value="direct">直连</option></select></label>
                <div className="environment-proxy-grid">
                  <label><span>Host</span><input name="proxy_host" defaultValue={proxyEditor.proxy_ip ?? ''} placeholder="代理主机" /></label>
                  <label><span>Port</span><input name="proxy_port" type="number" min="1" max="65535" defaultValue={proxyEditor.proxy_port ?? ''} placeholder="1080" /></label>
                  <label><span>Username</span><input name="proxy_username" autoComplete="off" placeholder="需要时重新填写" /></label>
                  <label><span>Password</span><input name="proxy_password" type="password" autoComplete="new-password" placeholder="需要时重新填写" /></label>
                </div>
                <div className="account-dialog-hint">当前出口 IP：{proxyEditor.real_ip || '尚未检测'}。修改网络前必须先关闭该真实 iXBrowser 环境。工作台不会读取或回显已有代理密码。</div>
              </div>
              <footer><Button type="button" onClick={() => setProxyEditor(null)} disabled={proxyBusy}>取消</Button><Button type="submit" variant="primary" disabled={proxyBusy}>{proxyBusy ? '保存中…' : '保存网络设置'}</Button></footer>
            </form>
          </div>
        </div>
      )}
    </main>
  )
}
