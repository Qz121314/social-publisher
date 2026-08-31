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

type BrowserProfile = {
  profile_id: number
  name: string
  is_available: boolean
}

type ProxyEndpoint = {
  id: number
  host: string
  port: number
  status: string
  enabled: boolean
}

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

type Channel = {
  id: string
  profile_id: number
  platform: string
  target_name: string
  enabled: boolean
  health_status: string
}

type Scope = 'all' | 'ungrouped' | number

type GroupEditor = {
  mode: 'create' | 'edit'
  group?: AccountGroup
} | null

type ImportResult = {
  received: number
  created: number
  skipped: number
}

const attentionStates = new Set(['needs_2fa', 'checkpoint', 'needs_review', 'error', 'failed'])
const loggedInStates = new Set(['logged_in', 'healthy', 'ok', 'ready'])

function platformLabel(platform: string) {
  if (platform === 'facebook') return 'Facebook'
  if (platform === 'instagram') return 'Instagram'
  return platform
}

export default function AccountPoolPage() {
  const [groups, setGroups] = useState<AccountGroup[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [channels, setChannels] = useState<Channel[]>([])
  const [scope, setScope] = useState<Scope>('all')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<number[]>([])
  const [groupEditor, setGroupEditor] = useState<GroupEditor>(null)
  const [moveOpen, setMoveOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importText, setImportText] = useState('')
  const [authAccount, setAuthAccount] = useState<Account | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = async () => {
    try {
      const [nextGroups, nextAccounts, nextChannels] = await Promise.all([
        api<AccountGroup[]>('/api/accounts/groups'),
        api<Account[]>('/api/accounts'),
        api<Channel[]>('/api/channels'),
      ])
      setGroups(nextGroups)
      setAccounts(nextAccounts)
      setChannels(nextChannels)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    }
  }

  useEffect(() => { load() }, [])

  const groupById = useMemo(() => new Map(groups.map((group) => [group.id, group])), [groups])
  const channelsByProfile = useMemo(() => {
    const map = new Map<number, Channel[]>()
    channels.forEach((channel) => {
      const list = map.get(channel.profile_id) ?? []
      list.push(channel)
      map.set(channel.profile_id, list)
    })
    return map
  }, [channels])

  const currentGroup = typeof scope === 'number' ? groupById.get(scope) : undefined
  const ungroupedCount = accounts.filter((account) => account.group_id == null).length
  const visibleAccounts = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    return accounts.filter((account) => {
      if (scope === 'ungrouped' && account.group_id != null) return false
      if (typeof scope === 'number' && account.group_id !== scope) return false
      if (!keyword) return true
      const profileName = account.browser_profile?.name ?? ''
      const proxyText = account.proxy_endpoint ? `${account.proxy_endpoint.host}:${account.proxy_endpoint.port}` : ''
      return `${account.name} ${account.platform} ${profileName} ${proxyText}`.toLowerCase().includes(keyword)
    })
  }, [accounts, scope, search])

  const selectedSet = useMemo(() => new Set(selected), [selected])
  const allVisibleSelected = visibleAccounts.length > 0 && visibleAccounts.every((account) => selectedSet.has(account.id))
  const scopeTitle = scope === 'all' ? '全部账号' : scope === 'ungrouped' ? '未分组' : currentGroup?.name ?? '账号分组'

  const setCurrentScope = (next: Scope) => {
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
    } finally {
      setBusy(false)
    }
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
    } finally {
      setBusy(false)
    }
  }

  const importAccounts = async (event: FormEvent) => {
    event.preventDefault()
    if (!importText.trim()) return
    setBusy(true)
    setMessage(null)
    try {
      const result = await api<ImportResult>('/api/account-pool/import', {
        method: 'POST',
        body: JSON.stringify({ text: importText }),
      })
      await load()
      setImportOpen(false)
      setImportText('')
      setMessage(`账号池导入完成：新增 ${result.created}，跳过重复 ${result.skipped}。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const moveSelected = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const groupValue = String(form.get('group_id') ?? '')
    setBusy(true)
    try {
      await api('/api/accounts/batch/group', {
        method: 'POST',
        body: JSON.stringify({ account_ids: selected, group_id: groupValue ? Number(groupValue) : null }),
      })
      setSelected([])
      setMoveOpen(false)
      await load()
      setMessage('账号分组已批量更新。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const assignProxy = async () => {
    if (selected.length === 0) return
    setBusy(true)
    try {
      const result = await api<{ assigned: number; unchanged: number }>('/api/account-pool/batch/assign-proxy', {
        method: 'POST',
        body: JSON.stringify({ account_ids: selected, replace_existing: false }),
      })
      await load()
      setMessage(`IP 自动分配完成：新分配 ${result.assigned}，保持原分配 ${result.unchanged}。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const readImportFile = async (file?: File) => {
    if (!file) return
    setImportText(await file.text())
  }

  const loggedInCount = visibleAccounts.filter((item) => loggedInStates.has(item.status)).length
  const attentionCount = visibleAccounts.filter((item) => attentionStates.has(item.status)).length
  const noProxyCount = visibleAccounts.filter((item) => !item.proxy_id).length
  const noRuntimeCount = visibleAccounts.filter((item) => !item.ix_profile_id).length

  return (
    <main className="prepare-workspace social-account-workspace">
      <WorkspaceHeader
        title="账号池"
        description="先批量准备账号、Cookie、2FA、分组和固定 IP；iX 环境在批量登录时按需创建并长期绑定。"
        actions={(
          <>
            <Button onClick={() => setGroupEditor({ mode: 'create' })}><PlusIcon />新建分组</Button>
            <Button variant="primary" onClick={() => setImportOpen(true)}>批量导入账号</Button>
          </>
        )}
      />
      <PrepareNav />

      {message && <div className="prepare-message">{message}</div>}

      <section className="social-account-shell">
        <aside className="account-group-rail">
          <div className="account-group-rail-title"><span>分组</span><small>{accounts.length}</small></div>
          <button type="button" className={scope === 'all' ? 'is-active' : ''} onClick={() => setCurrentScope('all')}><span>全部账号</span><strong>{accounts.length}</strong></button>
          <button type="button" className={scope === 'ungrouped' ? 'is-active' : ''} onClick={() => setCurrentScope('ungrouped')}><span>未分组</span><strong>{ungroupedCount}</strong></button>
          <div className="account-group-divider" />
          {groups.map((group) => <button key={group.id} type="button" className={scope === group.id ? 'is-active' : ''} onClick={() => setCurrentScope(group.id)}><span>{group.name}</span><strong>{group.member_count}</strong></button>)}
          <button type="button" className="account-group-add" onClick={() => setGroupEditor({ mode: 'create' })}><PlusIcon />新建分组</button>
        </aside>

        <div className="account-list-pane">
          <header className="account-scope-header">
            <div><div className="account-scope-title-row"><h2>{scopeTitle}</h2><StatusChip tone="neutral">{visibleAccounts.length} 个账号</StatusChip></div><p>{currentGroup?.description || '选择分组后，批量登录、账号维护和发帖任务都直接以该分组为目标。'}</p></div>
            {currentGroup && <Button variant="ghost" onClick={() => setGroupEditor({ mode: 'edit', group: currentGroup })}>管理分组</Button>}
          </header>

          <div className="account-status-strip account-pool-status-strip">
            <div><span>已登录</span><strong>{loggedInCount}</strong></div>
            <div><span>需要处理</span><strong>{attentionCount}</strong></div>
            <div><span>未分配 IP</span><strong>{noProxyCount}</strong></div>
            <div><span>待创建 iX 环境</span><strong>{noRuntimeCount}</strong></div>
          </div>

          <div className="account-toolbar">
            <div className="environment-search account-search"><SearchIcon /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索账号、IP或环境…" /></div>
            <span className="account-toolbar-note">资源准备完成后，下一步直接按分组创建批量登录任务。</span>
          </div>

          {selected.length > 0 && (
            <div className="environment-selection-bar account-selection-bar">
              <strong>已选择 {selected.length} 个账号</strong>
              <span>批量操作直接作用于当前选择，不需要再进入目标选择页。</span>
              <div><Button onClick={() => setMoveOpen(true)}>移动分组</Button><Button onClick={assignProxy} disabled={busy}>自动分配 IP</Button></div>
            </div>
          )}

          <div className="account-table account-pool-table" role="table" aria-label="账号池">
            <div className="account-row account-row--head" role="row">
              <div><input type="checkbox" checked={allVisibleSelected} onChange={toggleVisible} aria-label="选择当前列表全部账号" /></div>
              <div>账号</div><div>分组</div><div>固定 IP</div><div>iX 环境</div><div>发布身份</div><div>登录</div>
            </div>
            {visibleAccounts.length === 0 ? <EmptyState title="账号池为空" description="先批量导入账号 CSV；导入阶段不要求预先创建 iX 环境。" /> : visibleAccounts.map((account) => {
              const accountChannels = account.ix_profile_id ? (channelsByProfile.get(account.ix_profile_id) ?? []).filter((channel) => channel.platform === account.platform && channel.enabled) : []
              return (
                <div className="account-row" role="row" key={account.id}>
                  <div><input type="checkbox" checked={selectedSet.has(account.id)} onChange={() => setSelected((current) => current.includes(account.id) ? current.filter((id) => id !== account.id) : [...current, account.id])} aria-label={`选择 ${account.name}`} /></div>
                  <div className="account-primary-cell"><span className="account-avatar"><AccountIcon /></span><div><strong>{account.name}</strong><span>{platformLabel(account.platform)} · 账号 #{account.id}</span></div></div>
                  <div><span className="account-group-name">{account.group?.name || '未分组'}</span></div>
                  <div className="account-env-cell">{account.proxy_endpoint ? <><strong>{account.proxy_endpoint.host}:{account.proxy_endpoint.port}</strong><span>IP #{account.proxy_endpoint.id}</span></> : <StatusChip tone="warning">未分配</StatusChip>}</div>
                  <div className="account-env-cell">{account.browser_profile && account.ix_profile_id ? <><strong>{account.browser_profile.name}</strong><span>iX #{account.ix_profile_id}</span></> : <StatusChip tone="neutral">批量登录时创建</StatusChip>}</div>
                  <div className="account-identity-cell">{accountChannels.length === 0 ? <span>未配置</span> : accountChannels.slice(0, 2).map((channel) => <span key={channel.id}>{channel.target_name}</span>)}</div>
                  <AccountLoginControl account={account} onChanged={load} onMessage={setMessage} onOpenSettings={() => setAuthAccount(account)} />
                </div>
              )
            })}
          </div>
        </div>
      </section>

      <details className="account-advanced-tools"><summary>高级：浏览器环境 / 发布身份工具</summary><p>iX 环境属于运行资源，不再作为账号批量导入的前置步骤。这里仅保留人工排查和身份发现工具。</p><InstagramChannelPanel /><FacebookTargetPanel /></details>

      {groupEditor && <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setGroupEditor(null)}><div className="sp-form-dialog account-dialog" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><form onSubmit={saveGroup}><header><div><span>账号分组</span><h2>{groupEditor.mode === 'create' ? '新建分组' : '管理分组'}</h2></div><button type="button" onClick={() => setGroupEditor(null)} aria-label="关闭">×</button></header><div className="account-dialog-body"><label><span>分组名称</span><input name="name" defaultValue={groupEditor.group?.name ?? ''} maxLength={120} autoFocus required /></label><label><span>备注</span><textarea name="description" defaultValue={groupEditor.group?.description ?? ''} rows={3} /></label>{groupEditor.mode === 'edit' && groupEditor.group && <div className="account-group-delete-zone"><div><strong>删除分组</strong><span>{groupEditor.group.member_count > 0 ? `还有 ${groupEditor.group.member_count} 个账号，必须先移出。` : '只允许删除空分组。'}</span></div><Button type="button" variant="danger" onClick={deleteCurrentGroup} disabled={busy || groupEditor.group.member_count > 0}>删除</Button></div>}</div><footer><Button type="button" onClick={() => setGroupEditor(null)}>取消</Button><Button type="submit" variant="primary" disabled={busy}>{busy ? '保存中…' : '保存'}</Button></footer></form></div></div>}

      {moveOpen && <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setMoveOpen(false)}><div className="sp-form-dialog account-dialog account-dialog--small" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><form onSubmit={moveSelected}><header><div><span>批量操作</span><h2>移动 {selected.length} 个账号</h2></div><button type="button" onClick={() => setMoveOpen(false)} aria-label="关闭">×</button></header><div className="account-dialog-body"><label><span>目标分组</span><select name="group_id" defaultValue=""><option value="">未分组</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label></div><footer><Button type="button" onClick={() => setMoveOpen(false)}>取消</Button><Button type="submit" variant="primary" disabled={busy}>确认移动</Button></footer></form></div></div>}

      {importOpen && <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setImportOpen(false)}><div className="sp-form-dialog resource-import-dialog account-import-dialog" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><form onSubmit={importAccounts}><header><div><span>账号池</span><h2>批量导入账号</h2></div><button type="button" onClick={() => setImportOpen(false)} aria-label="关闭">×</button></header><div className="resource-import-body"><label className="resource-file-picker"><span>读取 CSV</span><input type="file" accept=".csv,text/csv" onChange={(event) => readImportFile(event.target.files?.[0])} /></label><div className="account-import-columns"><strong>CSV 表头</strong><code>账号名称,平台,分组,登录账号,密码,2fa,cookie,proxy,备注</code><span>proxy 可填写 IP池 ID 或 host:port。分组不存在时自动创建。</span></div><label><span>CSV 内容</span><textarea value={importText} onChange={(event) => setImportText(event.target.value)} rows={14} placeholder={'账号名称,平台,分组,登录账号,密码,2fa,cookie,proxy,备注\nFB-001,facebook,Store A,user@example.com,password,TOTPSECRET,"[{...}]",12,主账号'} /></label><div className="account-dialog-hint">Cookie / 密码 / TOTP 直接进入 Windows DPAPI 安全存储；普通 SQLite 只保存配置状态。导入不会启动 iXBrowser。</div></div><footer><Button type="button" onClick={() => setImportOpen(false)}>取消</Button><Button type="submit" variant="primary" disabled={busy || !importText.trim()}>{busy ? '导入中…' : '开始导入'}</Button></footer></form></div></div>}

      {authAccount && <AccountAuthDrawer account={authAccount} onClose={() => setAuthAccount(null)} onSaved={setMessage} />}
    </main>
  )
}
