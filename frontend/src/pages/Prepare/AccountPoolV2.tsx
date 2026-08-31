import React, { FormEvent, useEffect, useMemo, useState } from 'react'

import FacebookTargetPanel from '../../FacebookTargetPanel'
import InstagramChannelPanel from '../../InstagramChannelPanel'
import { api } from '../../app/api'
import { AccountIcon, PlusIcon, SearchIcon } from '../../ui/icons'
import { Button, EmptyState, StatusChip, WorkspaceHeader } from '../../ui/components'
import AccountAuthDrawer from './AccountAuthDrawer'
import AccountLoginControl from './AccountLoginControl'
import PrepareNav from './PrepareNav'

type AccountGroup = {
  id: number
  name: string
  description?: string | null
  sort_order: number
  enabled: boolean
  member_count: number
}

type BrowserProfile = { profile_id: number; name: string; is_available: boolean }
type ProxyEndpoint = { id: number; host: string; port: number; status: string; enabled: boolean; assigned_count?: number }
type Account = {
  id: number
  name: string
  platform: string
  ix_profile_id?: number | null
  group_id?: number | null
  proxy_id?: number | null
  enabled: boolean
  status: string
  notes?: string | null
  browser_profile?: BrowserProfile | null
  proxy_endpoint?: ProxyEndpoint | null
  group?: AccountGroup | null
}

type TaskJob = {
  id: string
  account_id?: number | null
  status: string
  stage: string
  profile_id?: number | null
  account_snapshot_json: string
  error_message?: string | null
}

type BatchTask = {
  id: string
  status: string
  total_jobs: number
  succeeded_jobs: number
  attention_jobs: number
  failed_jobs: number
  jobs: TaskJob[]
}

type Scope = 'all' | 'ungrouped' | number
type GroupEditor = { mode: 'create' | 'edit'; group?: AccountGroup } | null
type ImportResult = { received: number; created: number; skipped: number }

const attentionStates = new Set(['needs_2fa', 'checkpoint', 'needs_review', 'error', 'failed'])
const loggedInStates = new Set(['logged_in', 'healthy', 'ok', 'ready'])

function platformLabel(platform: string) {
  if (platform === 'facebook') return 'Facebook'
  if (platform === 'instagram') return 'Instagram'
  return platform
}

function batchStatus(status: string) {
  if (status === 'succeeded') return { label: '已完成', tone: 'success' as const }
  if (status === 'running') return { label: '执行中', tone: 'info' as const }
  if (status === 'queued') return { label: '等待执行', tone: 'neutral' as const }
  if (status === 'needs_attention') return { label: '需要处理', tone: 'warning' as const }
  if (status === 'partial') return { label: '部分完成', tone: 'warning' as const }
  if (status === 'failed') return { label: '失败', tone: 'danger' as const }
  return { label: status, tone: 'neutral' as const }
}

function jobStageLabel(stage: string) {
  const labels: Record<string, string> = {
    queued: '等待执行',
    preparing_runtime: '准备 iX 环境',
    recovering_login: '恢复登录',
    completed: '已完成',
    preflight: '准备条件不足',
    needs_attention: '需要处理',
    blocked: '暂时被占用',
    unsupported: '暂未支持',
    interrupted: '执行中断',
    failed: '失败',
  }
  return labels[stage] ?? stage
}

function snapshotName(raw: string) {
  try {
    return (JSON.parse(raw) as { name?: string }).name || '账号'
  } catch {
    return '账号'
  }
}

export default function AccountPoolV2Page() {
  const [groups, setGroups] = useState<AccountGroup[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [proxies, setProxies] = useState<ProxyEndpoint[]>([])
  const [scope, setScope] = useState<Scope>('all')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<number[]>([])
  const [groupEditor, setGroupEditor] = useState<GroupEditor>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [moveOpen, setMoveOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importText, setImportText] = useState('')
  const [authAccount, setAuthAccount] = useState<Account | null>(null)
  const [activeBatch, setActiveBatch] = useState<BatchTask | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = async () => {
    try {
      const [nextGroups, nextAccounts, nextProxies] = await Promise.all([
        api<AccountGroup[]>('/api/accounts/groups'),
        api<Account[]>('/api/accounts'),
        api<ProxyEndpoint[]>('/api/proxy-pool'),
      ])
      setGroups(nextGroups)
      setAccounts(nextAccounts)
      setProxies(nextProxies)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    }
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    if (!activeBatch || !['queued', 'running'].includes(activeBatch.status)) return
    const timer = window.setInterval(async () => {
      try {
        setActiveBatch(await api<BatchTask>(`/api/batch-tasks/${activeBatch.id}`))
        await load()
      } catch (error) {
        setMessage(error instanceof Error ? error.message : String(error))
      }
    }, 1500)
    return () => window.clearInterval(timer)
  }, [activeBatch?.id, activeBatch?.status])

  const groupById = useMemo(() => new Map(groups.map((group) => [group.id, group])), [groups])
  const currentGroup = typeof scope === 'number' ? groupById.get(scope) : undefined
  const ungroupedCount = accounts.filter((account) => account.group_id == null).length
  const visibleAccounts = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    return accounts.filter((account) => {
      if (scope === 'ungrouped' && account.group_id != null) return false
      if (typeof scope === 'number' && account.group_id !== scope) return false
      if (!keyword) return true
      const profile = account.browser_profile?.name ?? ''
      const proxy = account.proxy_endpoint ? `${account.proxy_endpoint.host}:${account.proxy_endpoint.port}` : ''
      return `${account.name} ${account.platform} ${profile} ${proxy}`.toLowerCase().includes(keyword)
    })
  }, [accounts, scope, search])

  const selectedSet = useMemo(() => new Set(selected), [selected])
  const allVisibleSelected = visibleAccounts.length > 0 && visibleAccounts.every((item) => selectedSet.has(item.id))
  const scopeTitle = scope === 'all' ? '全部账号' : scope === 'ungrouped' ? '未分组' : currentGroup?.name ?? '账号分组'

  const changeScope = (next: Scope) => {
    setScope(next)
    setSelected([])
  }

  const toggleVisible = () => {
    if (allVisibleSelected) {
      const ids = new Set(visibleAccounts.map((item) => item.id))
      setSelected((current) => current.filter((id) => !ids.has(id)))
    } else {
      setSelected((current) => Array.from(new Set([...current, ...visibleAccounts.map((item) => item.id)])))
    }
  }

  const startBatchLogin = async (mode: 'group' | 'selection') => {
    if (busy) return
    const body = mode === 'group' && currentGroup
      ? { group_id: currentGroup.id }
      : selected.length > 0
        ? { account_ids: selected }
        : null
    if (!body) return
    setBusy(true)
    setMessage(null)
    try {
      const task = await api<BatchTask>('/api/batch-tasks/login', { method: 'POST', body: JSON.stringify(body) })
      setActiveBatch(task)
      setSelected([])
      setMessage(`批量登录已开始：${task.total_jobs} 个账号进入执行队列。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally { setBusy(false) }
  }

  const createAccount = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (busy) return
    const form = new FormData(event.currentTarget)
    const groupValue = String(form.get('group_id') ?? '')
    const proxyValue = String(form.get('proxy_id') ?? '')
    setBusy(true)
    setMessage(null)
    try {
      const created = await api<Account>('/api/account-pool', {
        method: 'POST',
        body: JSON.stringify({
          name: String(form.get('name') ?? '').trim(),
          platform: String(form.get('platform') ?? 'facebook'),
          group_id: groupValue ? Number(groupValue) : null,
          proxy_id: proxyValue ? Number(proxyValue) : null,
          login_identifier: String(form.get('login_identifier') ?? '').trim() || null,
          password: String(form.get('password') ?? '') || null,
          totp_secret: String(form.get('totp_secret') ?? '').trim() || null,
          cookie_json: String(form.get('cookie_json') ?? '').trim() || null,
          notes: String(form.get('notes') ?? '').trim() || null,
        }),
      })
      await load()
      setCreateOpen(false)
      setMessage(`账号“${created.name}”已加入账号池。首次登录时再创建固定 iX 环境。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally { setBusy(false) }
  }

  const saveGroup = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!groupEditor) return
    const form = new FormData(event.currentTarget)
    const name = String(form.get('name') ?? '').trim()
    const description = String(form.get('description') ?? '').trim()
    if (!name) return
    setBusy(true)
    try {
      if (groupEditor.mode === 'create') {
        await api('/api/accounts/groups', { method: 'POST', body: JSON.stringify({ name, description: description || null }) })
      } else if (groupEditor.group) {
        await api(`/api/accounts/groups/${groupEditor.group.id}`, { method: 'PATCH', body: JSON.stringify({ name, description: description || null }) })
      }
      await load()
      setGroupEditor(null)
      setMessage(groupEditor.mode === 'create' ? `分组“${name}”已创建。` : '分组已更新。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally { setBusy(false) }
  }

  const deleteCurrentGroup = async () => {
    if (!groupEditor?.group || groupEditor.group.member_count > 0) return
    setBusy(true)
    try {
      await api(`/api/accounts/groups/${groupEditor.group.id}`, { method: 'DELETE' })
      if (scope === groupEditor.group.id) setScope('all')
      await load()
      setGroupEditor(null)
      setMessage('空分组已删除。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally { setBusy(false) }
  }

  const importAccounts = async (event: FormEvent) => {
    event.preventDefault()
    if (!importText.trim()) return
    setBusy(true)
    try {
      const result = await api<ImportResult>('/api/account-pool/import', { method: 'POST', body: JSON.stringify({ text: importText }) })
      await load()
      setImportOpen(false)
      setImportText('')
      setMessage(`账号池导入完成：新增 ${result.created}，跳过重复 ${result.skipped}。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally { setBusy(false) }
  }

  const moveSelected = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const groupValue = String(new FormData(event.currentTarget).get('group_id') ?? '')
    setBusy(true)
    try {
      await api('/api/accounts/batch/group', { method: 'POST', body: JSON.stringify({ account_ids: selected, group_id: groupValue ? Number(groupValue) : null }) })
      setSelected([])
      setMoveOpen(false)
      await load()
      setMessage('账号分组已批量更新。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally { setBusy(false) }
  }

  const assignProxy = async () => {
    if (selected.length === 0 || busy) return
    setBusy(true)
    try {
      const result = await api<{ assigned: number; unchanged: number }>('/api/account-pool/batch/assign-proxy', { method: 'POST', body: JSON.stringify({ account_ids: selected, replace_existing: false }) })
      await load()
      setMessage(`IP 自动分配完成：新分配 ${result.assigned}，保持原分配 ${result.unchanged}。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally { setBusy(false) }
  }

  const loggedInCount = visibleAccounts.filter((item) => loggedInStates.has(item.status)).length
  const attentionCount = visibleAccounts.filter((item) => attentionStates.has(item.status)).length
  const noProxyCount = visibleAccounts.filter((item) => !item.proxy_id).length
  const noRuntimeCount = visibleAccounts.filter((item) => !item.ix_profile_id).length
  const batchView = activeBatch ? batchStatus(activeBatch.status) : null
  const batchDone = activeBatch ? activeBatch.succeeded_jobs + activeBatch.attention_jobs + activeBatch.failed_jobs : 0

  return (
    <main className="prepare-workspace social-account-workspace">
      <WorkspaceHeader
        title="账号池"
        description="账号可以单个添加，也可以 CSV 批量导入。Cookie、密码、2FA、分组和固定 IP 都在这里准备；iX 环境在首次任务执行时按需创建。"
        actions={<><Button onClick={() => setCreateOpen(true)}><PlusIcon />添加账号</Button><Button variant="primary" onClick={() => setImportOpen(true)}>批量导入</Button></>}
      />
      <PrepareNav />
      {message && <div className="prepare-message">{message}</div>}

      {activeBatch && batchView && (
        <section className="resource-pool-shell batch-login-progress">
          <div className="resource-pool-toolbar"><div><strong>批量登录</strong><span>任务 #{activeBatch.id.slice(0, 8)}</span></div><div><StatusChip tone={batchView.tone}>{batchView.label}</StatusChip><Button variant="ghost" onClick={() => setActiveBatch(null)}>收起</Button></div></div>
          <div className="resource-pool-summary"><div><span>进度</span><strong>{batchDone} / {activeBatch.total_jobs}</strong></div><div><span>已完成</span><strong>{activeBatch.succeeded_jobs}</strong></div><div><span>需要处理</span><strong>{activeBatch.attention_jobs}</strong></div><div><span>失败</span><strong>{activeBatch.failed_jobs}</strong></div></div>
          {activeBatch.jobs.some((job) => job.status !== 'succeeded') && <div className="batch-login-job-list">{activeBatch.jobs.filter((job) => job.status !== 'succeeded').slice(0, 12).map((job) => <div key={job.id}><strong>{snapshotName(job.account_snapshot_json)}</strong><span>{jobStageLabel(job.stage)}</span><small>{job.error_message || (job.status === 'queued' ? '等待可用执行槽位' : '处理中')}</small></div>)}</div>}
        </section>
      )}

      <section className="social-account-shell">
        <aside className="account-group-rail">
          <div className="account-group-rail-title"><span>分组</span><small>{accounts.length}</small></div>
          <button type="button" className={scope === 'all' ? 'is-active' : ''} onClick={() => changeScope('all')}><span>全部账号</span><strong>{accounts.length}</strong></button>
          <button type="button" className={scope === 'ungrouped' ? 'is-active' : ''} onClick={() => changeScope('ungrouped')}><span>未分组</span><strong>{ungroupedCount}</strong></button>
          <div className="account-group-divider" />
          {groups.map((group) => <button key={group.id} type="button" className={scope === group.id ? 'is-active' : ''} onClick={() => changeScope(group.id)}><span>{group.name}</span><strong>{group.member_count}</strong></button>)}
          <button type="button" className="account-group-add" onClick={() => setGroupEditor({ mode: 'create' })}><PlusIcon />新建分组</button>
        </aside>

        <div className="account-list-pane">
          <header className="account-scope-header">
            <div><div className="account-scope-title-row"><h2>{scopeTitle}</h2><StatusChip tone="neutral">{visibleAccounts.length} 个账号</StatusChip></div><p>{currentGroup?.description || '单个、当前选择和整个分组最终都进入同一套任务引擎。'}</p></div>
            <div className="account-scope-actions">{currentGroup && <Button variant="primary" onClick={() => startBatchLogin('group')} disabled={busy || visibleAccounts.length === 0}>批量登录</Button>}{currentGroup && <Button variant="ghost" onClick={() => setGroupEditor({ mode: 'edit', group: currentGroup })}>管理分组</Button>}</div>
          </header>

          <div className="account-status-strip account-pool-status-strip"><div><span>已登录</span><strong>{loggedInCount}</strong></div><div><span>需要处理</span><strong>{attentionCount}</strong></div><div><span>未分配 IP</span><strong>{noProxyCount}</strong></div><div><span>待创建 iX 环境</span><strong>{noRuntimeCount}</strong></div></div>
          <div className="account-toolbar"><div className="environment-search account-search"><SearchIcon /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索账号、IP或环境…" /></div><span className="account-toolbar-note">单个添加和批量导入使用同一个账号池。</span></div>

          {selected.length > 0 && <div className="environment-selection-bar account-selection-bar"><strong>已选择 {selected.length} 个账号</strong><span>当前选择可直接创建任务或批量整理资源。</span><div><Button variant="primary" onClick={() => startBatchLogin('selection')} disabled={busy}>批量登录</Button><Button onClick={() => setMoveOpen(true)}>移动分组</Button><Button onClick={assignProxy} disabled={busy}>自动分配 IP</Button></div></div>}

          <div className="account-table account-pool-table" role="table" aria-label="账号池">
            <div className="account-row account-row--head" role="row"><div><input type="checkbox" checked={allVisibleSelected} onChange={toggleVisible} aria-label="选择当前列表全部账号" /></div><div>账号</div><div>分组</div><div>固定 IP</div><div>iX 环境</div><div>登录状态</div></div>
            {visibleAccounts.length === 0 ? <EmptyState title="账号池为空" description="可以添加单个账号，也可以批量导入 CSV。" /> : visibleAccounts.map((account) => (
              <div className="account-row account-pool-v2-row" role="row" key={account.id}>
                <div><input type="checkbox" checked={selectedSet.has(account.id)} onChange={() => setSelected((current) => current.includes(account.id) ? current.filter((id) => id !== account.id) : [...current, account.id])} aria-label={`选择 ${account.name}`} /></div>
                <div className="account-primary-cell"><span className="account-avatar"><AccountIcon /></span><div><strong>{account.name}</strong><span>{platformLabel(account.platform)} · 账号 #{account.id}</span></div></div>
                <div><span className="account-group-name">{account.group?.name || '未分组'}</span></div>
                <div className="account-env-cell">{account.proxy_endpoint ? <><strong>{account.proxy_endpoint.host}:{account.proxy_endpoint.port}</strong><span>IP #{account.proxy_endpoint.id}</span></> : <StatusChip tone="warning">未分配</StatusChip>}</div>
                <div className="account-env-cell">{account.browser_profile && account.ix_profile_id ? <><strong>{account.browser_profile.name}</strong><span>iX #{account.ix_profile_id}</span></> : <StatusChip tone="neutral">首次任务时创建</StatusChip>}</div>
                <AccountLoginControl account={account} onChanged={load} onMessage={setMessage} onOpenSettings={() => setAuthAccount(account)} />
              </div>
            ))}
          </div>
        </div>
      </section>

      <details className="account-advanced-tools"><summary>高级渠道工具</summary><div><FacebookTargetPanel /><InstagramChannelPanel /></div></details>

      {createOpen && <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setCreateOpen(false)}><div className="sp-form-dialog resource-import-dialog" role="dialog" aria-modal="true" aria-label="添加账号" onMouseDown={(event) => event.stopPropagation()}><form onSubmit={createAccount}><header><div><span>账号池</span><h2>添加账号</h2></div><button type="button" onClick={() => setCreateOpen(false)} disabled={busy}>×</button></header><div className="resource-import-body"><div className="resource-entry-grid"><label><span>账号名称</span><input name="name" placeholder="FB-001" required /></label><label><span>平台</span><select name="platform" defaultValue="facebook"><option value="facebook">Facebook</option><option value="instagram">Instagram</option></select></label></div><div className="resource-entry-grid"><label><span>分组</span><select name="group_id" defaultValue={typeof scope === 'number' ? String(scope) : ''}><option value="">未分组</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label><label><span>固定 IP</span><select name="proxy_id" defaultValue=""><option value="">稍后分配</option>{proxies.filter((proxy) => proxy.enabled && proxy.status !== 'error').map((proxy) => <option key={proxy.id} value={proxy.id}>#{proxy.id} · {proxy.host}:{proxy.port}</option>)}</select></label></div><label><span>登录账号（可选）</span><input name="login_identifier" placeholder="邮箱 / 手机号 / 用户名" /></label><div className="resource-entry-grid"><label><span>密码（可选）</span><input name="password" type="password" /></label><label><span>TOTP / 2FA Secret（可选）</span><input name="totp_secret" /></label></div><label><span>Cookie（可选）</span><textarea name="cookie_json" rows={6} placeholder='[{"name":"c_user","value":"...","domain":".facebook.com"}]' /></label><label><span>备注（可选）</span><textarea name="notes" rows={2} /></label><div className="account-dialog-hint">保存账号不会立即创建 iX 环境。密码、Cookie、TOTP 使用 Windows DPAPI 加密保存。</div></div><footer><Button type="button" onClick={() => setCreateOpen(false)} disabled={busy}>取消</Button><Button type="submit" variant="primary" disabled={busy}>{busy ? '保存中…' : '保存账号'}</Button></footer></form></div></div>}

      {groupEditor && <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setGroupEditor(null)}><div className="sp-form-dialog account-dialog" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><form onSubmit={saveGroup}><header><div><span>账号池</span><h2>{groupEditor.mode === 'create' ? '新建分组' : '管理分组'}</h2></div><button type="button" onClick={() => setGroupEditor(null)} disabled={busy}>×</button></header><div className="account-dialog-body"><label><span>分组名称</span><input name="name" defaultValue={groupEditor.group?.name || ''} required /></label><label><span>说明</span><textarea name="description" rows={3} defaultValue={groupEditor.group?.description || ''} /></label></div><footer>{groupEditor.mode === 'edit' && groupEditor.group?.member_count === 0 && <Button type="button" variant="danger" onClick={deleteCurrentGroup} disabled={busy}>删除空分组</Button>}<Button type="button" onClick={() => setGroupEditor(null)} disabled={busy}>取消</Button><Button type="submit" variant="primary" disabled={busy}>保存</Button></footer></form></div></div>}

      {moveOpen && <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setMoveOpen(false)}><div className="sp-form-dialog account-dialog" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><form onSubmit={moveSelected}><header><div><span>批量操作</span><h2>移动 {selected.length} 个账号</h2></div><button type="button" onClick={() => setMoveOpen(false)} disabled={busy}>×</button></header><div className="account-dialog-body"><label><span>目标分组</span><select name="group_id" defaultValue=""><option value="">未分组</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label></div><footer><Button type="button" onClick={() => setMoveOpen(false)} disabled={busy}>取消</Button><Button type="submit" variant="primary" disabled={busy}>移动</Button></footer></form></div></div>}

      {importOpen && <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setImportOpen(false)}><div className="sp-form-dialog resource-import-dialog" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><form onSubmit={importAccounts}><header><div><span>账号池</span><h2>批量导入账号</h2></div><button type="button" onClick={() => setImportOpen(false)} disabled={busy}>×</button></header><div className="resource-import-body"><label className="resource-file-picker"><span>读取 CSV</span><input type="file" accept=".csv,text/csv" onChange={async (event) => { const file = event.target.files?.[0]; if (file) setImportText(await file.text()) }} /></label><label><span>CSV 内容</span><textarea rows={14} value={importText} onChange={(event) => setImportText(event.target.value)} placeholder={'账号名称,平台,分组,登录账号,密码,2fa,cookie,proxy,备注\nFB-001,facebook,Store A,user@example.com,password,TOTP,"[{...}]",12,主账号'} /></label><div className="account-dialog-hint">单个添加和批量导入写入同一个账号池；批量导入不会预先创建 iX 环境。</div></div><footer><Button type="button" onClick={() => setImportOpen(false)} disabled={busy}>取消</Button><Button type="submit" variant="primary" disabled={busy || !importText.trim()}>{busy ? '导入中…' : '开始导入'}</Button></footer></form></div></div>}

      {authAccount && <AccountAuthDrawer account={authAccount} onClose={() => setAuthAccount(null)} onSaved={(text) => { setMessage(text); load() }} />}
    </main>
  )
}
