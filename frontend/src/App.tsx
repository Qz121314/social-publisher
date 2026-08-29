import React, { FormEvent, useEffect, useMemo, useState } from 'react'

import ContentComposer from './ContentComposer'

type IxStatus = {
  connected: boolean
  total_profiles?: number
  code?: number | string | null
  message?: string | null
}

type WorkerStats = {
  max_workers: number
  active_tasks: number
}

type AppStatus = {
  app: string
  ixbrowser: IxStatus
  browser_sessions?: number
  worker?: WorkerStats
}

type BrowserProfile = {
  profile_id: number
  name: string
  group_id?: number | null
  group_name?: string | null
  is_available: boolean
  last_seen_at: string
}

type BrowserSession = {
  profile_id: number
  attached: boolean
  alive: boolean
  opened_at: string
  current_url?: string | null
  title?: string | null
  window_count?: number
  already_open?: boolean
  error?: string
}

type ProfileLock = {
  profile_id: number
  owner_id: string
  task_id?: string | null
  acquired_at: string
  heartbeat_at: string
  expires_at: string
}

type WorkerTask = {
  id: string
  task_type: string
  profile_id: number
  status: string
  attempts: number
  result?: Record<string, unknown> | string | null
  error_message?: string | null
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
}

type Account = {
  id: number
  name: string
  platform: string
  ix_profile_id: number
  enabled: boolean
  status: string
  notes?: string | null
  browser_profile: BrowserProfile
}

const platforms = [
  'facebook',
  'instagram',
  'x',
  'tiktok',
  'threads',
  'linkedin',
  'youtube',
  'pinterest',
  'other',
]

const platformLabels: Record<string, string> = {
  facebook: 'Facebook',
  instagram: 'Instagram',
  x: 'X',
  tiktok: 'TikTok',
  threads: 'Threads',
  linkedin: 'LinkedIn',
  youtube: 'YouTube',
  pinterest: 'Pinterest',
  other: '其他',
}

const statusLabels: Record<string, string> = {
  unknown: '未知',
  draft: '草稿',
  queued: '排队中',
  running: '执行中',
  succeeded: '成功',
  failed: '失败',
  blocked: '已阻止',
  interrupted: '已中断',
  needs_review: '待人工确认',
  enabled: '已启用',
  disabled: '已停用',
}

const taskTypeLabels: Record<string, string> = {
  browser_probe: '浏览器测试',
  worker_test: '工作进程测试',
  publish: '发布任务',
}

function platformLabel(value: string) {
  return platformLabels[value] ?? value
}

function statusLabel(value: string) {
  return statusLabels[value] ?? value
}

function taskTypeLabel(value: string) {
  return taskTypeLabels[value] ?? value
}

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers ?? {}),
    },
  })

  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`
    try {
      const data = await response.json()
      message = data.detail ?? message
    } catch {
      // 保留 HTTP 状态作为兜底错误信息。
    }
    throw new Error(message)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

function shortId(value?: string | null) {
  return value ? value.slice(0, 8) : '—'
}

export default function App() {
  const [status, setStatus] = useState<AppStatus | null>(null)
  const [profiles, setProfiles] = useState<BrowserProfile[]>([])
  const [sessions, setSessions] = useState<BrowserSession[]>([])
  const [locks, setLocks] = useState<ProfileLock[]>([])
  const [workerTasks, setWorkerTasks] = useState<WorkerTask[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [browserBusy, setBrowserBusy] = useState<number | null>(null)
  const [workerBusy, setWorkerBusy] = useState<number | null>(null)
  const [filter, setFilter] = useState('all')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [platform, setPlatform] = useState('facebook')
  const [profileId, setProfileId] = useState('')
  const [notes, setNotes] = useState('')

  const loadStatus = async () => {
    try {
      setStatus(await api<AppStatus>('/api/status'))
    } catch (error) {
      setStatus({ app: 'offline', ixbrowser: { connected: false, message: String(error) } })
    }
  }

  const loadProfiles = async () => {
    setProfiles(await api<BrowserProfile[]>('/api/browser-profiles'))
  }

  const loadSessions = async () => {
    const result = await api<{ items: BrowserSession[]; count: number }>('/api/browser-sessions')
    setSessions(result.items)
  }

  const loadLocks = async () => {
    const result = await api<{ items: ProfileLock[]; count: number }>('/api/profile-locks')
    setLocks(result.items)
  }

  const loadWorkerTasks = async () => {
    const result = await api<{ items: WorkerTask[]; count: number }>('/api/worker/tasks?limit=20')
    setWorkerTasks(result.items)
  }

  const loadAccounts = async () => {
    setAccounts(await api<Account[]>('/api/accounts'))
  }

  const refresh = async () => {
    await Promise.all([
      loadStatus(),
      loadProfiles(),
      loadSessions(),
      loadLocks(),
      loadWorkerTasks(),
      loadAccounts(),
    ])
  }

  useEffect(() => {
    refresh().catch((error: Error) => setMessage(error.message))

    const timer = window.setInterval(() => {
      Promise.all([loadStatus(), loadSessions(), loadLocks(), loadWorkerTasks()]).catch(() => undefined)
    }, 2500)

    return () => window.clearInterval(timer)
  }, [])

  const filteredAccounts = useMemo(
    () => accounts.filter((account) => filter === 'all' || account.platform === filter),
    [accounts, filter],
  )

  const sessionByProfile = useMemo(
    () => new Map(sessions.map((session) => [session.profile_id, session])),
    [sessions],
  )

  const lockByProfile = useMemo(
    () => new Map(locks.map((lock) => [lock.profile_id, lock])),
    [locks],
  )

  const profileById = useMemo(
    () => new Map(profiles.map((profile) => [profile.profile_id, profile])),
    [profiles],
  )

  const resetForm = () => {
    setEditingId(null)
    setName('')
    setPlatform('facebook')
    setProfileId('')
    setNotes('')
  }

  const syncProfiles = async () => {
    setBusy(true)
    setMessage(null)
    try {
      const result = await api<{ fetched: number; created: number; updated: number }>(
        '/api/ixbrowser/sync',
        { method: 'POST' },
      )
      await Promise.all([loadProfiles(), loadStatus()])
      setMessage(`已同步 ${result.fetched} 个 iX 环境。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const openProfile = async (profile: BrowserProfile) => {
    setBrowserBusy(profile.profile_id)
    setMessage(null)
    try {
      const session = await api<BrowserSession>(`/api/browser-profiles/${profile.profile_id}/open`, {
        method: 'POST',
      })
      await Promise.all([loadSessions(), loadStatus()])
      setMessage(
        session.already_open
          ? `${profile.name} 已连接到 Selenium。`
          : `${profile.name} 已成功打开并连接 Selenium。`,
      )
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBrowserBusy(null)
    }
  }

  const probeProfile = async (profile: BrowserProfile) => {
    setBrowserBusy(profile.profile_id)
    setMessage(null)
    try {
      const session = await api<BrowserSession>(`/api/browser-profiles/${profile.profile_id}/probe`, {
        method: 'POST',
      })
      await loadSessions()
      const page = session.title || session.current_url || '浏览器会话'
      setMessage(`${profile.name}：Selenium 连接正常 · ${page}`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
      await loadSessions().catch(() => undefined)
    } finally {
      setBrowserBusy(null)
    }
  }

  const closeProfile = async (profile: BrowserProfile) => {
    setBrowserBusy(profile.profile_id)
    setMessage(null)
    try {
      await api<{ closed: boolean }>(`/api/browser-profiles/${profile.profile_id}/close`, {
        method: 'POST',
      })
      await Promise.all([loadSessions(), loadStatus()])
      setMessage(`${profile.name} 已关闭。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBrowserBusy(null)
    }
  }

  const runWorkerTest = async (profile: BrowserProfile) => {
    setWorkerBusy(profile.profile_id)
    setMessage(null)
    try {
      const task = await api<WorkerTask>(`/api/worker/test/${profile.profile_id}`, {
        method: 'POST',
      })
      await Promise.all([loadWorkerTasks(), loadLocks(), loadStatus()])
      setMessage(`${profile.name}：测试任务 ${shortId(task.id)} 已进入队列。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setWorkerBusy(null)
    }
  }

  const submitAccount = async (event: FormEvent) => {
    event.preventDefault()
    if (!profileId) {
      setMessage('请先选择一个 iX 环境。')
      return
    }

    setBusy(true)
    setMessage(null)
    const payload = {
      name,
      platform,
      ix_profile_id: Number(profileId),
      notes: notes || null,
    }

    try {
      if (editingId === null) {
        await api<Account>('/api/accounts', { method: 'POST', body: JSON.stringify(payload) })
        setMessage('账号已添加。')
      } else {
        await api<Account>(`/api/accounts/${editingId}`, {
          method: 'PATCH',
          body: JSON.stringify(payload),
        })
        setMessage('账号已更新。')
      }
      resetForm()
      await loadAccounts()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const editAccount = (account: Account) => {
    setEditingId(account.id)
    setName(account.name)
    setPlatform(account.platform)
    setProfileId(String(account.ix_profile_id))
    setNotes(account.notes ?? '')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const toggleAccount = async (account: Account) => {
    setBusy(true)
    try {
      await api<Account>(`/api/accounts/${account.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ enabled: !account.enabled }),
      })
      await loadAccounts()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const removeAccount = async (account: Account) => {
    if (!window.confirm(`确定删除账号“${account.name}”吗？`)) return
    setBusy(true)
    try {
      await api<void>(`/api/accounts/${account.id}`, { method: 'DELETE' })
      if (editingId === account.id) resetForm()
      await loadAccounts()
      setMessage('账号已删除。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">本地控制台</p>
          <h1>社媒矩阵发布系统</h1>
          <p className="subtitle">基于独立 iXBrowser 环境的多账号自动发布管理。</p>
        </div>
        <button className="primary" onClick={syncProfiles} disabled={busy}>
          {busy ? '处理中…' : '同步 iX 环境'}
        </button>
      </header>

      {message && <div className="notice">{message}</div>}

      <section className="stats">
        <article className="stat-card">
          <span>后端服务</span>
          <strong>{status?.app === 'ok' ? '已连接' : status ? '离线' : '检查中…'}</strong>
          <small>FastAPI · SQLite</small>
        </article>
        <article className="stat-card">
          <span>iXBrowser</span>
          <strong>{status?.ixbrowser.connected ? '已连接' : status ? '离线' : '检查中…'}</strong>
          <small>
            {status?.ixbrowser.connected
              ? `${status.ixbrowser.total_profiles ?? 0} 个环境 · ${sessions.length} 个 Selenium 会话`
              : status?.ixbrowser.message ?? '127.0.0.1:53200'}
          </small>
        </article>
        <article className="stat-card">
          <span>工作进程</span>
          <strong>{status?.worker ? `${status.worker.active_tasks}/${status.worker.max_workers}` : '—'}</strong>
          <small>{locks.length} 个环境锁正在使用</small>
        </article>
        <article className="stat-card">
          <span>账号</span>
          <strong>{accounts.length}</strong>
          <small>{accounts.filter((item) => item.enabled).length} 个已启用</small>
        </article>
      </section>

      <ContentComposer profiles={profiles} onMessage={setMessage} />

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">浏览器控制</p>
            <h2>iXBrowser 环境</h2>
          </div>
          <span className="section-meta">{sessions.length} 个 Selenium 会话 · {locks.length} 个已锁定</span>
        </div>

        {profiles.length === 0 ? (
          <div className="empty-state">
            <strong>暂无已同步环境</strong>
            <span>请先启动 iXBrowser，然后点击“同步 iX 环境”。</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="browser-table">
              <thead>
                <tr>
                  <th>环境</th>
                  <th>分组</th>
                  <th>锁定状态</th>
                  <th>Selenium</th>
                  <th>当前页面</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((profile) => {
                  const session = sessionByProfile.get(profile.profile_id)
                  const profileLock = lockByProfile.get(profile.profile_id)
                  const isBusy = browserBusy === profile.profile_id
                  const isWorkerBusy = workerBusy === profile.profile_id
                  return (
                    <tr key={profile.profile_id}>
                      <td>
                        <div className="profile-cell">
                          <strong>{profile.name}</strong>
                          <small>#{profile.profile_id}</small>
                        </div>
                      </td>
                      <td>{profile.group_name || '—'}</td>
                      <td>
                        {profileLock ? (
                          <span className="lock-badge" title={profileLock.owner_id}>
                            已锁定 · {shortId(profileLock.task_id)}
                          </span>
                        ) : (
                          <span className="idle-label">空闲</span>
                        )}
                      </td>
                      <td>
                        <span className={`status-dot ${session?.alive ? '' : 'neutral'}`}></span>
                        {session?.alive ? `已连接 · ${session.window_count ?? 0} 个窗口` : '未连接'}
                      </td>
                      <td className="url-cell" title={session?.current_url ?? ''}>
                        {session?.title || session?.current_url || '—'}
                      </td>
                      <td className="actions browser-actions">
                        <button
                          className="compact-button worker-button"
                          onClick={() => runWorkerTest(profile)}
                          disabled={isWorkerBusy || Boolean(profileLock)}
                        >
                          {isWorkerBusy ? '加入队列…' : '工作进程测试'}
                        </button>
                        <button
                          className="compact-button"
                          onClick={() => openProfile(profile)}
                          disabled={isBusy || Boolean(session?.alive) || Boolean(profileLock)}
                        >
                          {isBusy ? '处理中…' : '打开'}
                        </button>
                        <button
                          className="compact-button"
                          onClick={() => probeProfile(profile)}
                          disabled={isBusy || !session?.alive || Boolean(profileLock)}
                        >
                          检查
                        </button>
                        <button
                          className="compact-button danger-outline"
                          onClick={() => closeProfile(profile)}
                          disabled={isBusy || Boolean(profileLock)}
                        >
                          关闭
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">执行任务</p>
            <h2>最近的工作任务</h2>
          </div>
          <span className="section-meta">最大并发数 {status?.worker?.max_workers ?? 3}</span>
        </div>

        {workerTasks.length === 0 ? (
          <div className="empty-state compact-empty">
            <strong>暂无工作任务</strong>
            <span>可以在任意已同步的 iX 环境上运行“工作进程测试”。</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="worker-table">
              <thead>
                <tr>
                  <th>任务</th>
                  <th>环境</th>
                  <th>状态</th>
                  <th>尝试次数</th>
                  <th>结果</th>
                </tr>
              </thead>
              <tbody>
                {workerTasks.map((task) => {
                  const profile = profileById.get(task.profile_id)
                  const resultTitle =
                    typeof task.result === 'object' && task.result !== null
                      ? String(task.result.title ?? task.result.current_url ?? '已完成')
                      : task.error_message || (typeof task.result === 'string' ? task.result : '—')
                  return (
                    <tr key={task.id}>
                      <td>
                        <div className="profile-cell">
                          <strong>{shortId(task.id)}</strong>
                          <small>{taskTypeLabel(task.task_type)}</small>
                        </div>
                      </td>
                      <td>{profile?.name || `#${task.profile_id}`}</td>
                      <td><span className={`task-status task-${task.status}`}>{statusLabel(task.status)}</span></td>
                      <td>{task.attempts}</td>
                      <td className="result-cell" title={resultTitle}>{resultTitle}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel form-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">账号绑定</p>
            <h2>{editingId === null ? '添加账号' : '编辑账号'}</h2>
          </div>
          {editingId !== null && <button className="text-button" onClick={resetForm}>取消编辑</button>}
        </div>

        <form className="account-form" onSubmit={submitAccount}>
          <label>
            <span>显示名称</span>
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：Facebook 品牌账号 01" required />
          </label>
          <label>
            <span>平台</span>
            <select value={platform} onChange={(event) => setPlatform(event.target.value)}>
              {platforms.map((item) => <option key={item} value={item}>{platformLabel(item)}</option>)}
            </select>
          </label>
          <label>
            <span>iX 环境</span>
            <select value={profileId} onChange={(event) => setProfileId(event.target.value)} required>
              <option value="">请选择环境</option>
              {profiles.map((profile) => (
                <option key={profile.profile_id} value={profile.profile_id}>
                  {profile.name} · #{profile.profile_id}{profile.group_name ? ` · ${profile.group_name}` : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="notes-field">
            <span>备注</span>
            <input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="选填" />
          </label>
          <button className="primary submit-button" disabled={busy} type="submit">
            {editingId === null ? '添加账号' : '保存修改'}
          </button>
        </form>
      </section>

      <section className="panel">
        <div className="section-heading account-heading">
          <div>
            <p className="eyebrow">账号中心</p>
            <h2>账号管理</h2>
          </div>
          <select className="filter" value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="all">全部平台</option>
            {platforms.map((item) => <option key={item} value={item}>{platformLabel(item)}</option>)}
          </select>
        </div>

        {filteredAccounts.length === 0 ? (
          <div className="empty-state">
            <strong>暂无账号</strong>
            <span>先同步 iX 环境，再绑定第一个平台账号。</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>账号</th>
                  <th>平台</th>
                  <th>iX 环境</th>
                  <th>状态</th>
                  <th>启用</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredAccounts.map((account) => (
                  <tr key={account.id}>
                    <td><strong>{account.name}</strong></td>
                    <td><span className="platform-pill">{platformLabel(account.platform)}</span></td>
                    <td>
                      <div className="profile-cell">
                        <strong>{account.browser_profile.name}</strong>
                        <small>#{account.ix_profile_id}</small>
                      </div>
                    </td>
                    <td><span className={`status-dot ${account.status === 'unknown' ? 'neutral' : ''}`}></span>{statusLabel(account.status)}</td>
                    <td>
                      <button className={`switch ${account.enabled ? 'on' : ''}`} onClick={() => toggleAccount(account)} disabled={busy}>
                        <span></span>
                      </button>
                    </td>
                    <td className="actions">
                      <button className="text-button" onClick={() => editAccount(account)}>编辑</button>
                      <button className="text-button danger" onClick={() => removeAccount(account)}>删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  )
}
