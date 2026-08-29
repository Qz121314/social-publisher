import React, { FormEvent, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

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

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers ?? {}),
    },
  })

  if (!response.ok) {
    let message = `HTTP ${response.status}`
    try {
      const data = await response.json()
      message = data.detail ?? message
    } catch {
      // Keep the HTTP fallback.
    }
    throw new Error(message)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

function shortId(value?: string | null) {
  return value ? value.slice(0, 8) : '—'
}

function App() {
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
      setMessage(`Synced ${result.fetched} iX profiles.`)
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
          ? `${profile.name} is already attached to Selenium.`
          : `${profile.name} opened and Selenium attached successfully.`,
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
      const page = session.title || session.current_url || 'browser session'
      setMessage(`${profile.name}: Selenium connection is healthy · ${page}`)
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
      setMessage(`${profile.name} closed.`)
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
      setMessage(`${profile.name}: worker task ${shortId(task.id)} queued.`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setWorkerBusy(null)
    }
  }

  const submitAccount = async (event: FormEvent) => {
    event.preventDefault()
    if (!profileId) {
      setMessage('Select an iX profile first.')
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
        setMessage('Account added.')
      } else {
        await api<Account>(`/api/accounts/${editingId}`, {
          method: 'PATCH',
          body: JSON.stringify(payload),
        })
        setMessage('Account updated.')
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
    if (!window.confirm(`Delete ${account.name}?`)) return
    setBusy(true)
    try {
      await api<void>(`/api/accounts/${account.id}`, { method: 'DELETE' })
      if (editingId === account.id) resetForm()
      await loadAccounts()
      setMessage('Account deleted.')
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
          <p className="eyebrow">LOCAL CONTROL PLANE</p>
          <h1>Social Publisher</h1>
          <p className="subtitle">Multi-account publishing powered by isolated iXBrowser profiles.</p>
        </div>
        <button className="primary" onClick={syncProfiles} disabled={busy}>
          {busy ? 'Working…' : 'Sync iX Profiles'}
        </button>
      </header>

      {message && <div className="notice">{message}</div>}

      <section className="stats">
        <article className="stat-card">
          <span>Backend</span>
          <strong>{status?.app === 'ok' ? 'Connected' : status ? 'Offline' : 'Checking…'}</strong>
          <small>FastAPI · SQLite</small>
        </article>
        <article className="stat-card">
          <span>iXBrowser</span>
          <strong>{status?.ixbrowser.connected ? 'Connected' : status ? 'Offline' : 'Checking…'}</strong>
          <small>
            {status?.ixbrowser.connected
              ? `${status.ixbrowser.total_profiles ?? 0} profiles · ${sessions.length} Selenium attached`
              : status?.ixbrowser.message ?? '127.0.0.1:53200'}
          </small>
        </article>
        <article className="stat-card">
          <span>Worker Pool</span>
          <strong>{status?.worker ? `${status.worker.active_tasks}/${status.worker.max_workers}` : '—'}</strong>
          <small>{locks.length} profile lock(s) active</small>
        </article>
        <article className="stat-card">
          <span>Accounts</span>
          <strong>{accounts.length}</strong>
          <small>{accounts.filter((item) => item.enabled).length} enabled</small>
        </article>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">BROWSER CONTROL</p>
            <h2>iXBrowser profiles</h2>
          </div>
          <span className="section-meta">{sessions.length} Selenium sessions · {locks.length} locked</span>
        </div>

        {profiles.length === 0 ? (
          <div className="empty-state">
            <strong>No synced profiles</strong>
            <span>Start iXBrowser and sync profiles first.</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="browser-table">
              <thead>
                <tr>
                  <th>Profile</th>
                  <th>Group</th>
                  <th>Lock</th>
                  <th>Selenium</th>
                  <th>Current page</th>
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
                            Locked · {shortId(profileLock.task_id)}
                          </span>
                        ) : (
                          <span className="idle-label">Idle</span>
                        )}
                      </td>
                      <td>
                        <span className={`status-dot ${session?.alive ? '' : 'neutral'}`}></span>
                        {session?.alive ? `Attached · ${session.window_count ?? 0} window(s)` : 'Not attached'}
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
                          {isWorkerBusy ? 'Queueing…' : 'Worker Test'}
                        </button>
                        <button
                          className="compact-button"
                          onClick={() => openProfile(profile)}
                          disabled={isBusy || Boolean(session?.alive) || Boolean(profileLock)}
                        >
                          {isBusy ? 'Working…' : 'Open'}
                        </button>
                        <button
                          className="compact-button"
                          onClick={() => probeProfile(profile)}
                          disabled={isBusy || !session?.alive || Boolean(profileLock)}
                        >
                          Check
                        </button>
                        <button
                          className="compact-button danger-outline"
                          onClick={() => closeProfile(profile)}
                          disabled={isBusy || Boolean(profileLock)}
                        >
                          Close
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
            <p className="eyebrow">EXECUTION</p>
            <h2>Recent worker tasks</h2>
          </div>
          <span className="section-meta">Max concurrency {status?.worker?.max_workers ?? 3}</span>
        </div>

        {workerTasks.length === 0 ? (
          <div className="empty-state compact-empty">
            <strong>No worker tasks yet</strong>
            <span>Run a Worker Test on any synced iX profile.</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="worker-table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Profile</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {workerTasks.map((task) => {
                  const profile = profileById.get(task.profile_id)
                  const resultTitle =
                    typeof task.result === 'object' && task.result !== null
                      ? String(task.result.title ?? task.result.current_url ?? 'Completed')
                      : task.error_message || (typeof task.result === 'string' ? task.result : '—')
                  return (
                    <tr key={task.id}>
                      <td>
                        <div className="profile-cell">
                          <strong>{shortId(task.id)}</strong>
                          <small>{task.task_type}</small>
                        </div>
                      </td>
                      <td>{profile?.name || `#${task.profile_id}`}</td>
                      <td><span className={`task-status task-${task.status}`}>{task.status}</span></td>
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
            <p className="eyebrow">ACCOUNT BINDING</p>
            <h2>{editingId === null ? 'Add account' : 'Edit account'}</h2>
          </div>
          {editingId !== null && <button className="text-button" onClick={resetForm}>Cancel edit</button>}
        </div>

        <form className="account-form" onSubmit={submitAccount}>
          <label>
            <span>Display name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="FB Brand 01" required />
          </label>
          <label>
            <span>Platform</span>
            <select value={platform} onChange={(event) => setPlatform(event.target.value)}>
              {platforms.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label>
            <span>iX Profile</span>
            <select value={profileId} onChange={(event) => setProfileId(event.target.value)} required>
              <option value="">Select profile</option>
              {profiles.map((profile) => (
                <option key={profile.profile_id} value={profile.profile_id}>
                  {profile.name} · #{profile.profile_id}{profile.group_name ? ` · ${profile.group_name}` : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="notes-field">
            <span>Notes</span>
            <input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Optional" />
          </label>
          <button className="primary submit-button" disabled={busy} type="submit">
            {editingId === null ? 'Add account' : 'Save changes'}
          </button>
        </form>
      </section>

      <section className="panel">
        <div className="section-heading account-heading">
          <div>
            <p className="eyebrow">ACCOUNT CENTER</p>
            <h2>Accounts</h2>
          </div>
          <select className="filter" value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="all">All platforms</option>
            {platforms.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>

        {filteredAccounts.length === 0 ? (
          <div className="empty-state">
            <strong>No accounts yet</strong>
            <span>Sync iX profiles, then bind your first platform account.</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Platform</th>
                  <th>iX Profile</th>
                  <th>Status</th>
                  <th>Enabled</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredAccounts.map((account) => (
                  <tr key={account.id}>
                    <td><strong>{account.name}</strong></td>
                    <td><span className="platform-pill">{account.platform}</span></td>
                    <td>
                      <div className="profile-cell">
                        <strong>{account.browser_profile.name}</strong>
                        <small>#{account.ix_profile_id}</small>
                      </div>
                    </td>
                    <td><span className={`status-dot ${account.status === 'unknown' ? 'neutral' : ''}`}></span>{account.status}</td>
                    <td>
                      <button className={`switch ${account.enabled ? 'on' : ''}`} onClick={() => toggleAccount(account)} disabled={busy}>
                        <span></span>
                      </button>
                    </td>
                    <td className="actions">
                      <button className="text-button" onClick={() => editAccount(account)}>Edit</button>
                      <button className="text-button danger" onClick={() => removeAccount(account)}>Delete</button>
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

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
