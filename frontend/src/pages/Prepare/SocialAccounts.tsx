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
  group_name?: string | null
  is_available: boolean
}

type Account = {
  id: number
  name: string
  platform: string
  ix_profile_id: number
  group_id?: number | null
  enabled: boolean
  status: string
  notes?: string | null
  updated_at: string
  browser_profile: BrowserProfile
  group?: AccountGroup | null
}

type Channel = {
  id: string
  profile_id: number
  platform: string
  target_name: string
  target_type: string
  enabled: boolean
  health_status: string
}

type Scope = 'all' | 'ungrouped' | number

type GroupEditor = {
  mode: 'create' | 'edit'
  group?: AccountGroup
} | null

const attentionStates = new Set(['needs_2fa', 'checkpoint', 'needs_review', 'error', 'failed', 'needs_login'])
const healthyStates = new Set(['logged_in', 'healthy', 'ok', 'ready'])

function platformLabel(platform: string) {
  if (platform === 'facebook') return 'Facebook'
  if (platform === 'instagram') return 'Instagram'
  return platform
}

export default function SocialAccountsPage() {
  const [groups, setGroups] = useState<AccountGroup[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [profiles, setProfiles] = useState<BrowserProfile[]>([])
  const [channels, setChannels] = useState<Channel[]>([])
  const [scope, setScope] = useState<Scope>('all')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<number[]>([])
  const [groupEditor, setGroupEditor] = useState<GroupEditor>(null)
  const [accountEditorOpen, setAccountEditorOpen] = useState(false)
  const [authAccount, setAuthAccount] = useState<Account | null>(null)
  const [moveOpen, setMoveOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = async () => {
    try {
      const [nextGroups, nextAccounts, nextProfiles, nextChannels] = await Promise.all([
        api<AccountGroup[]>('/api/accounts/groups'),
        api<Account[]>('/api/accounts'),
        api<BrowserProfile[]>('/api/browser-profiles'),
        api<Channel[]>('/api/channels'),
      ])
      setGroups(nextGroups)
      setAccounts(nextAccounts)
      setProfiles(nextProfiles)
      setChannels(nextChannels)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    }
  }

  useEffect(() => {
    load()
  }, [])

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

  const ungroupedCount = accounts.filter((account) => account.group_id == null).length
  const currentGroup = typeof scope === 'number' ? groupById.get(scope) : undefined

  const visibleAccounts = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    return accounts.filter((account) => {
      if (scope === 'ungrouped' && account.group_id != null) return false
      if (typeof scope === 'number' && account.group_id !== scope) return false
      if (!keyword) return true
      const identities = (channelsByProfile.get(account.ix_profile_id) ?? [])
        .map((channel) => channel.target_name)
        .join(' ')
      return `${account.name} ${account.platform} ${account.browser_profile.name} ${identities}`
        .toLowerCase()
        .includes(keyword)
    })
  }, [accounts, channelsByProfile, scope, search])

  const selectedSet = useMemo(() => new Set(selected), [selected])
  const allVisibleSelected = visibleAccounts.length > 0 && visibleAccounts.every((account) => selectedSet.has(account.id))

  const setCurrentScope = (next: Scope) => {
    setScope(next)
    setSelected([])
  }

  const toggleAccount = (accountId: number) => {
    setSelected((current) => current.includes(accountId)
      ? current.filter((id) => id !== accountId)
      : [...current, accountId])
  }

  const toggleVisible = () => {
    if (allVisibleSelected) {
      const visibleIds = new Set(visibleAccounts.map((account) => account.id))
      setSelected((current) => current.filter((id) => !visibleIds.has(id)))
      return
    }
    setSelected((current) => Array.from(new Set([...current, ...visibleAccounts.map((account) => account.id)])))
  }

  const saveGroup = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!groupEditor) return
    const form = new FormData(event.currentTarget)
    const name = String(form.get('name') ?? '').trim()
    const description = String(form.get('description') ?? '').trim()
    if (!name) return
    setBusy(true)
    setMessage(null)
    try {
      if (groupEditor.mode === 'create') {
        await api('/api/accounts/groups', {
          method: 'POST',
          body: JSON.stringify({ name, description: description || null }),
        })
      } else if (groupEditor.group) {
        await api(`/api/accounts/groups/${groupEditor.group.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ name, description: description || null }),
        })
      }
      await load()
      setGroupEditor(null)
      setMessage(groupEditor.mode === 'create' ? `分组“${name}”已创建。` : `分组已更新为“${name}”。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const deleteCurrentGroup = async () => {
    if (!groupEditor?.group || groupEditor.group.member_count > 0) return
    setBusy(true)
    setMessage(null)
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

  const createAccount = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const name = String(form.get('name') ?? '').trim()
    const platform = String(form.get('platform') ?? 'facebook')
    const profileId = Number(form.get('ix_profile_id'))
    const groupValue = String(form.get('group_id') ?? '')
    if (!name || !Number.isFinite(profileId)) return

    setBusy(true)
    setMessage(null)
    try {
      await api('/api/accounts', {
        method: 'POST',
        body: JSON.stringify({
          name,
          platform,
          ix_profile_id: profileId,
          group_id: groupValue ? Number(groupValue) : null,
        }),
      })
      await load()
      setAccountEditorOpen(false)
      setMessage(`账号“${name}”已加入工作台。`)
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
    setMessage(null)
    try {
      await api('/api/accounts/batch/group', {
        method: 'POST',
        body: JSON.stringify({
          account_ids: selected,
          group_id: groupValue ? Number(groupValue) : null,
        }),
      })
      await load()
      setSelected([])
      setMoveOpen(false)
      setMessage(`已移动 ${selected.length} 个账号。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const healthyCount = visibleAccounts.filter((account) => healthyStates.has(account.status)).length
  const attentionCount = visibleAccounts.filter((account) => attentionStates.has(account.status)).length
  const unknownCount = visibleAccounts.length - healthyCount - attentionCount
  const scopeTitle = scope === 'all' ? '全部账号' : scope === 'ungrouped' ? '未分组' : currentGroup?.name ?? '账号分组'

  return (
    <main className="prepare-workspace social-account-workspace">
      <WorkspaceHeader
        title="社交账号"
        description="用业务分组组织账号。分组将直接成为批量登录、检查和发布任务的选择单位。"
        actions={(
          <>
            <Button onClick={() => setGroupEditor({ mode: 'create' })}><PlusIcon />新建分组</Button>
            <Button variant="primary" onClick={() => setAccountEditorOpen(true)}><PlusIcon />添加账号</Button>
          </>
        )}
      />
      <PrepareNav />

      {message && <div className="prepare-message">{message}</div>}

      <section className="social-account-shell">
        <aside className="account-group-rail">
          <div className="account-group-rail-title"><span>分组</span><small>{accounts.length}</small></div>
          <button type="button" className={scope === 'all' ? 'is-active' : ''} onClick={() => setCurrentScope('all')}>
            <span>全部账号</span><strong>{accounts.length}</strong>
          </button>
          <button type="button" className={scope === 'ungrouped' ? 'is-active' : ''} onClick={() => setCurrentScope('ungrouped')}>
            <span>未分组</span><strong>{ungroupedCount}</strong>
          </button>
          <div className="account-group-divider" />
          {groups.map((group) => (
            <button key={group.id} type="button" className={scope === group.id ? 'is-active' : ''} onClick={() => setCurrentScope(group.id)}>
              <span>{group.name}</span><strong>{group.member_count}</strong>
            </button>
          ))}
          <button type="button" className="account-group-add" onClick={() => setGroupEditor({ mode: 'create' })}><PlusIcon />新建分组</button>
        </aside>

        <div className="account-list-pane">
          <header className="account-scope-header">
            <div>
              <div className="account-scope-title-row">
                <h2>{scopeTitle}</h2>
                <StatusChip tone="neutral">{visibleAccounts.length} 个账号</StatusChip>
              </div>
              <p>{currentGroup?.description || '选择分组后，后续批量任务将直接以当前分组作为目标。'}</p>
            </div>
            {currentGroup && (
              <Button variant="ghost" onClick={() => setGroupEditor({ mode: 'edit', group: currentGroup })}>管理分组</Button>
            )}
          </header>

          <div className="account-status-strip">
            <div><span>已登录</span><strong>{healthyCount}</strong></div>
            <div><span>需要处理</span><strong>{attentionCount}</strong></div>
            <div><span>未检查</span><strong>{unknownCount}</strong></div>
          </div>

          <div className="account-toolbar">
            <div className="environment-search account-search">
              <SearchIcon />
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索账号、环境或发布身份…" />
            </div>
            <span className="account-toolbar-note">Facebook 单账号恢复登录已接入真实 iX 环境；批量执行将在单账号闭环验证后复用同一引擎。</span>
          </div>

          {selected.length > 0 && (
            <div className="environment-selection-bar account-selection-bar">
              <strong>已选择 {selected.length} 个账号</strong>
              <span>当前可直接执行账号组织操作；登录、检查和发布将复用同一选择状态。</span>
              <div>
                <Button onClick={() => setMoveOpen(true)}>移动分组</Button>
              </div>
            </div>
          )}

          <div className="account-table" role="table" aria-label="社交账号">
            <div className="account-row account-row--head" role="row">
              <div><input type="checkbox" checked={allVisibleSelected} onChange={toggleVisible} aria-label="选择当前列表全部账号" /></div>
              <div>账号</div>
              <div>分组</div>
              <div>浏览器环境</div>
              <div>发布身份</div>
              <div>登录</div>
            </div>

            {visibleAccounts.length === 0 ? (
              <EmptyState title="当前没有账号" description="可以添加账号并绑定已有 iX 浏览器环境，或切换到其他分组。" />
            ) : visibleAccounts.map((account) => {
              const accountChannels = (channelsByProfile.get(account.ix_profile_id) ?? []).filter((channel) => channel.platform === account.platform && channel.enabled)
              return (
                <div className="account-row" role="row" key={account.id}>
                  <div><input type="checkbox" checked={selectedSet.has(account.id)} onChange={() => toggleAccount(account.id)} aria-label={`选择 ${account.name}`} /></div>
                  <div className="account-primary-cell">
                    <span className="account-avatar"><AccountIcon /></span>
                    <div><strong>{account.name}</strong><span>{platformLabel(account.platform)} · 账号 #{account.id}</span></div>
                  </div>
                  <div><span className="account-group-name">{account.group?.name || '未分组'}</span></div>
                  <div className="account-env-cell"><strong>{account.browser_profile.name}</strong><span>iX #{account.ix_profile_id}</span></div>
                  <div className="account-identity-cell">
                    {accountChannels.length === 0 ? <span>未配置</span> : accountChannels.slice(0, 2).map((channel) => <span key={channel.id}>{channel.target_name}</span>)}
                    {accountChannels.length > 2 && <small>+{accountChannels.length - 2}</small>}
                  </div>
                  <AccountLoginControl
                    account={account}
                    onChanged={load}
                    onMessage={setMessage}
                    onOpenSettings={() => setAuthAccount(account)}
                  />
                </div>
              )
            })}
          </div>
        </div>
      </section>

      <details className="account-advanced-tools">
        <summary>高级：平台身份 / 发布身份识别工具</summary>
        <p>这些工具保留用于发现和确认真实发布身份，不参与日常账号分组操作。</p>
        <InstagramChannelPanel />
        <FacebookTargetPanel />
      </details>

      {groupEditor && (
        <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setGroupEditor(null)}>
          <div className="sp-form-dialog account-dialog" role="dialog" aria-modal="true" aria-label={groupEditor.mode === 'create' ? '新建账号分组' : '管理账号分组'} onMouseDown={(event) => event.stopPropagation()}>
            <form onSubmit={saveGroup}>
              <header><div><span>账号分组</span><h2>{groupEditor.mode === 'create' ? '新建分组' : '管理分组'}</h2></div><button type="button" onClick={() => setGroupEditor(null)} aria-label="关闭">×</button></header>
              <div className="account-dialog-body">
                <label><span>分组名称</span><input name="name" defaultValue={groupEditor.group?.name ?? ''} maxLength={120} autoFocus required /></label>
                <label><span>备注</span><textarea name="description" defaultValue={groupEditor.group?.description ?? ''} rows={3} placeholder="可选，例如 Store A / US Facebook" /></label>
                {groupEditor.mode === 'edit' && groupEditor.group && (
                  <div className="account-group-delete-zone">
                    <div><strong>删除分组</strong><span>{groupEditor.group.member_count > 0 ? `还有 ${groupEditor.group.member_count} 个账号，必须先移出。` : '只允许删除空分组，账号不会被级联删除。'}</span></div>
                    <Button type="button" variant="danger" onClick={deleteCurrentGroup} disabled={busy || groupEditor.group.member_count > 0}>删除</Button>
                  </div>
                )}
              </div>
              <footer><Button type="button" onClick={() => setGroupEditor(null)} disabled={busy}>取消</Button><Button type="submit" variant="primary" disabled={busy}>{busy ? '保存中…' : '保存'}</Button></footer>
            </form>
          </div>
        </div>
      )}

      {accountEditorOpen && (
        <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setAccountEditorOpen(false)}>
          <div className="sp-form-dialog account-dialog" role="dialog" aria-modal="true" aria-label="添加社交账号" onMouseDown={(event) => event.stopPropagation()}>
            <form onSubmit={createAccount}>
              <header><div><span>社交账号</span><h2>添加账号</h2></div><button type="button" onClick={() => setAccountEditorOpen(false)} aria-label="关闭">×</button></header>
              <div className="account-dialog-body">
                <label><span>账号名称</span><input name="name" placeholder="例如 John / Store A" maxLength={255} autoFocus required /></label>
                <label><span>平台</span><select name="platform" defaultValue="facebook"><option value="facebook">Facebook</option><option value="instagram">Instagram</option></select></label>
                <label><span>浏览器环境</span><select name="ix_profile_id" defaultValue="" required><option value="" disabled>选择固定 iX 环境</option>{profiles.map((profile) => <option key={profile.profile_id} value={profile.profile_id}>{profile.name} · iX #{profile.profile_id}</option>)}</select></label>
                <label><span>账号分组</span><select name="group_id" defaultValue={typeof scope === 'number' ? String(scope) : ''}><option value="">未分组</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label>
                <div className="account-dialog-hint">这里只建立账号与 iX 环境的稳定绑定。Cookie、密码和 TOTP 动态验证码密钥不会写入普通 SQLite。</div>
              </div>
              <footer><Button type="button" onClick={() => setAccountEditorOpen(false)} disabled={busy}>取消</Button><Button type="submit" variant="primary" disabled={busy || profiles.length === 0}>{busy ? '创建中…' : '添加账号'}</Button></footer>
            </form>
          </div>
        </div>
      )}

      {moveOpen && (
        <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setMoveOpen(false)}>
          <div className="sp-form-dialog account-dialog account-dialog--small" role="dialog" aria-modal="true" aria-label="移动账号分组" onMouseDown={(event) => event.stopPropagation()}>
            <form onSubmit={moveSelected}>
              <header><div><span>批量操作</span><h2>移动 {selected.length} 个账号</h2></div><button type="button" onClick={() => setMoveOpen(false)} aria-label="关闭">×</button></header>
              <div className="account-dialog-body"><label><span>目标分组</span><select name="group_id" defaultValue=""><option value="">未分组</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label></div>
              <footer><Button type="button" onClick={() => setMoveOpen(false)} disabled={busy}>取消</Button><Button type="submit" variant="primary" disabled={busy}>{busy ? '移动中…' : '确认移动'}</Button></footer>
            </form>
          </div>
        </div>
      )}

      {authAccount && (
        <AccountAuthDrawer
          account={authAccount}
          onClose={() => setAuthAccount(null)}
          onSaved={setMessage}
        />
      )}
    </main>
  )
}
