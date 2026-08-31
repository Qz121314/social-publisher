import React, { FormEvent, useEffect, useMemo, useState } from 'react'

import { api } from '../../app/api'
import { Button, EmptyState, StatusChip, WorkspaceHeader } from '../../ui/components'
import PrepareNav from './PrepareNav'

type ProxyEndpoint = {
  id: number
  protocol: string
  host: string
  port: number
  label?: string | null
  username_configured: boolean
  password_configured: boolean
  enabled: boolean
  status: string
  exit_ip?: string | null
  country?: string | null
  region?: string | null
  latency_ms?: number | null
  assigned_count: number
}

type ImportResult = {
  received: number
  created: number
  skipped: number
}

function statusView(status: string) {
  if (['healthy', 'ok'].includes(status)) return { label: '正常', tone: 'success' as const }
  if (status === 'error') return { label: '异常', tone: 'danger' as const }
  if (status === 'checking') return { label: '检测中', tone: 'info' as const }
  return { label: '待检测', tone: 'neutral' as const }
}

export default function ProxyPoolPage() {
  const [items, setItems] = useState<ProxyEndpoint[]>([])
  const [selected, setSelected] = useState<number[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importText, setImportText] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = async () => {
    try {
      const result = await api<ProxyEndpoint[]>('/api/proxy-pool')
      setItems(result)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    }
  }

  useEffect(() => { load() }, [])

  const visible = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) return items
    return items.filter((item) => `${item.id} ${item.host} ${item.port} ${item.label ?? ''} ${item.exit_ip ?? ''}`.toLowerCase().includes(keyword))
  }, [items, search])

  const selectedSet = useMemo(() => new Set(selected), [selected])
  const allSelected = visible.length > 0 && visible.every((item) => selectedSet.has(item.id))
  const assignedCount = items.filter((item) => item.assigned_count > 0).length
  const errorCount = items.filter((item) => item.status === 'error').length

  const toggleAll = () => {
    if (allSelected) {
      const ids = new Set(visible.map((item) => item.id))
      setSelected((current) => current.filter((id) => !ids.has(id)))
    } else {
      setSelected((current) => Array.from(new Set([...current, ...visible.map((item) => item.id)])))
    }
  }

  const createProxy = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (busy) return
    const form = new FormData(event.currentTarget)
    setBusy(true)
    setMessage(null)
    try {
      const created = await api<ProxyEndpoint>('/api/proxy-pool', {
        method: 'POST',
        body: JSON.stringify({
          host: String(form.get('host') ?? '').trim(),
          port: Number(form.get('port')),
          username: String(form.get('username') ?? '').trim() || null,
          password: String(form.get('password') ?? '') || null,
          label: String(form.get('label') ?? '').trim() || null,
        }),
      })
      await load()
      setCreateOpen(false)
      setMessage(`SOCKS5 已加入 IP池：${created.host}:${created.port}`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const importPool = async (event: FormEvent) => {
    event.preventDefault()
    if (!importText.trim()) return
    setBusy(true)
    setMessage(null)
    try {
      const result = await api<ImportResult>('/api/proxy-pool/import', {
        method: 'POST',
        body: JSON.stringify({ text: importText }),
      })
      await load()
      setImportOpen(false)
      setImportText('')
      setMessage(`IP池导入完成：新增 ${result.created}，跳过重复 ${result.skipped}。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const deleteSelected = async () => {
    if (selected.length === 0 || busy) return
    setBusy(true)
    setMessage(null)
    try {
      const result = await api<{ deleted: number }>('/api/proxy-pool/batch/delete', {
        method: 'POST',
        body: JSON.stringify({ proxy_ids: selected }),
      })
      setSelected([])
      await load()
      setMessage(`已删除 ${result.deleted} 条未分配 IP。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const readFile = async (file?: File) => {
    if (!file) return
    setImportText(await file.text())
  }

  return (
    <main className="prepare-workspace resource-pool-workspace">
      <WorkspaceHeader
        title="IP池"
        description="SOCKS5 统一进入 IP池。可以单个新增，也可以 TXT / CSV 批量导入；账号绑定后长期复用固定 IP。"
        actions={<><Button onClick={() => setCreateOpen(true)}>+ 新建 IP</Button><Button variant="primary" onClick={() => setImportOpen(true)}>批量导入</Button></>}
      />
      <PrepareNav />

      {message && <div className="prepare-message">{message}</div>}

      <div className="resource-pool-summary">
        <div><span>IP总数</span><strong>{items.length}</strong></div>
        <div><span>已分配</span><strong>{assignedCount}</strong></div>
        <div><span>未分配</span><strong>{items.length - assignedCount}</strong></div>
        <div><span>异常</span><strong>{errorCount}</strong></div>
      </div>

      <section className="resource-pool-shell">
        <div className="resource-pool-toolbar">
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索 Host、出口 IP、标签或 ID…" />
          <span>单个新增和批量导入使用同一个 IP池；不会生成两套数据。</span>
        </div>

        {selected.length > 0 && (
          <div className="environment-selection-bar">
            <strong>已选择 {selected.length} 条 IP</strong>
            <span>已绑定账号的 IP 不允许直接删除。</span>
            <div><Button variant="danger" onClick={deleteSelected} disabled={busy}>删除所选</Button></div>
          </div>
        )}

        <div className="resource-pool-table" role="table" aria-label="SOCKS5 IP池">
          <div className="resource-pool-row resource-pool-row--head" role="row">
            <div><input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="选择全部可见 IP" /></div>
            <div>SOCKS5</div>
            <div>认证</div>
            <div>状态</div>
            <div>出口 IP</div>
            <div>分配</div>
          </div>
          {visible.length === 0 ? (
            <EmptyState title="IP池为空" description="可以新建单个 SOCKS5，也可以直接批量导入。" />
          ) : visible.map((item) => {
            const status = statusView(item.status)
            return (
              <div className="resource-pool-row" role="row" key={item.id}>
                <div><input type="checkbox" checked={selectedSet.has(item.id)} onChange={() => setSelected((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} aria-label={`选择 IP ${item.id}`} /></div>
                <div className="resource-pool-endpoint"><strong>{item.host}:{item.port}</strong><span>IP #{item.id}{item.label ? ` · ${item.label}` : ''}</span></div>
                <div><StatusChip tone={item.username_configured ? 'info' : 'neutral'}>{item.username_configured ? '账号密码认证' : '无认证'}</StatusChip></div>
                <div><StatusChip tone={status.tone}>{status.label}</StatusChip>{item.latency_ms != null && <small>{item.latency_ms} ms</small>}</div>
                <div><strong>{item.exit_ip || '未检测'}</strong><span>{[item.country, item.region].filter(Boolean).join(' · ') || '—'}</span></div>
                <div><StatusChip tone={item.assigned_count > 0 ? 'success' : 'neutral'}>{item.assigned_count > 0 ? `已分配 ${item.assigned_count}` : '未分配'}</StatusChip></div>
              </div>
            )
          })}
        </div>
      </section>

      {createOpen && (
        <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setCreateOpen(false)}>
          <div className="sp-form-dialog account-dialog" role="dialog" aria-modal="true" aria-label="新建 SOCKS5" onMouseDown={(event) => event.stopPropagation()}>
            <form onSubmit={createProxy}>
              <header><div><span>IP池</span><h2>新建 SOCKS5</h2></div><button type="button" onClick={() => setCreateOpen(false)} disabled={busy}>×</button></header>
              <div className="account-dialog-body">
                <div className="resource-entry-grid"><label><span>Host / IP</span><input name="host" placeholder="128.241.28.247" required /></label><label><span>Port</span><input name="port" type="number" min="1" max="65535" placeholder="37263" required /></label></div>
                <div className="resource-entry-grid"><label><span>用户名（可选）</span><input name="username" placeholder="LR1LbJaq" /></label><label><span>密码（可选）</span><input name="password" type="password" placeholder="SOCKS5 密码" /></label></div>
                <label><span>标签（可选）</span><input name="label" placeholder="US-01" /></label>
                <div className="account-dialog-hint">带认证的 SOCKS5 请同时填写用户名和密码。密码通过 Windows DPAPI 加密保存。</div>
              </div>
              <footer><Button type="button" onClick={() => setCreateOpen(false)} disabled={busy}>取消</Button><Button type="submit" variant="primary" disabled={busy}>{busy ? '保存中…' : '保存 IP'}</Button></footer>
            </form>
          </div>
        </div>
      )}

      {importOpen && (
        <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setImportOpen(false)}>
          <div className="sp-form-dialog resource-import-dialog" role="dialog" aria-modal="true" aria-label="批量导入 SOCKS5" onMouseDown={(event) => event.stopPropagation()}>
            <form onSubmit={importPool}>
              <header><div><span>IP池</span><h2>批量导入 SOCKS5</h2></div><button type="button" onClick={() => setImportOpen(false)} disabled={busy} aria-label="关闭">×</button></header>
              <div className="resource-import-body">
                <label className="resource-file-picker"><span>读取 TXT / CSV</span><input type="file" accept=".txt,.csv,text/plain,text/csv" onChange={(event) => readFile(event.target.files?.[0])} /></label>
                <label><span>导入内容</span><textarea value={importText} onChange={(event) => setImportText(event.target.value)} rows={14} placeholder={'支持：\n128.241.28.247:37263\n128.241.28.247:37263:LR1LbJaq:AqkY3X3y6U\nsocks5://user:password@128.241.28.247:37263\nhost,port,username,password,label'} /></label>
                <div className="account-dialog-hint">四段格式按 IP:Port:Username:Password 解析。用户名和密码不会写入普通 SQLite；重复记录自动跳过。</div>
              </div>
              <footer><Button type="button" onClick={() => setImportOpen(false)} disabled={busy}>取消</Button><Button type="submit" variant="primary" disabled={busy || !importText.trim()}>{busy ? '导入中…' : '开始导入'}</Button></footer>
            </form>
          </div>
        </div>
      )}
    </main>
  )
}
