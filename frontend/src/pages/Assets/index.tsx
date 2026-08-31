import React, { FormEvent, useEffect, useMemo, useState } from 'react'

import { api, formatDateTime } from '../../app/api'
import { Button, EmptyState, StatusChip, WorkspaceHeader } from '../../ui/components'
import PrepareNav from '../Prepare/PrepareNav'

type Asset = {
  id: string
  name: string
  asset_type: 'text' | 'image' | 'video'
  platform: string
  text_content?: string | null
  original_name?: string | null
  mime_type?: string | null
  file_size?: number | null
  status: string
  created_at: string
}

type ImportResult = { received: number; created: number; skipped: number }
type EntryMode = 'text' | 'media'

function typeLabel(value: string) {
  if (value === 'text') return '文案'
  if (value === 'image') return '图片'
  if (value === 'video') return '视频'
  return value
}

function platformLabel(value: string) {
  if (value === 'generic') return '通用'
  if (value === 'facebook') return 'Facebook'
  if (value === 'instagram') return 'Instagram'
  return value
}

function sizeLabel(value?: number | null) {
  if (!value) return '—'
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

export default function AssetsPage() {
  const [items, setItems] = useState<Asset[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [createMode, setCreateMode] = useState<EntryMode>('text')
  const [singleFile, setSingleFile] = useState<File | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [importMode, setImportMode] = useState<EntryMode>('text')
  const [importText, setImportText] = useState('')
  const [batchFiles, setBatchFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = async () => {
    try {
      setItems(await api<Asset[]>('/api/asset-pool'))
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    }
  }

  useEffect(() => { load() }, [])

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) return items
    return items.filter((item) => `${item.name} ${item.asset_type} ${item.platform} ${item.text_content ?? ''} ${item.original_name ?? ''}`.toLowerCase().includes(keyword))
  }, [items, search])

  const selectedSet = useMemo(() => new Set(selected), [selected])
  const allVisibleSelected = filtered.length > 0 && filtered.every((item) => selectedSet.has(item.id))

  const toggleVisible = () => {
    if (allVisibleSelected) {
      const ids = new Set(filtered.map((item) => item.id))
      setSelected((current) => current.filter((id) => !ids.has(id)))
    } else {
      setSelected((current) => Array.from(new Set([...current, ...filtered.map((item) => item.id)])))
    }
  }

  const createAsset = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (busy) return
    const form = new FormData(event.currentTarget)
    setBusy(true)
    setMessage(null)
    try {
      if (createMode === 'text') {
        await api('/api/asset-pool/text', {
          method: 'POST',
          body: JSON.stringify({
            name: String(form.get('name') ?? '').trim(),
            platform: String(form.get('platform') ?? 'generic'),
            text: String(form.get('text') ?? '').trim(),
          }),
        })
      } else {
        if (!singleFile) throw new Error('请选择一个图片或视频文件。')
        const body = new FormData()
        body.set('name', String(form.get('name') ?? '').trim())
        body.set('platform', String(form.get('platform') ?? 'generic'))
        body.set('file', singleFile)
        await api('/api/asset-pool/media', { method: 'POST', body })
      }
      await load()
      setSingleFile(null)
      setCreateOpen(false)
      setMessage('素材已加入素材池。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally { setBusy(false) }
  }

  const importAssets = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setMessage(null)
    try {
      let result: ImportResult
      if (importMode === 'text') {
        if (!importText.trim()) throw new Error('请粘贴或读取文案 CSV。')
        result = await api<ImportResult>('/api/asset-pool/text/import', {
          method: 'POST',
          body: JSON.stringify({ text: importText }),
        })
      } else {
        if (batchFiles.length === 0) throw new Error('请选择图片或视频文件。')
        const form = new FormData(event.currentTarget)
        const body = new FormData()
        body.set('platform', String(form.get('platform') ?? 'generic'))
        batchFiles.forEach((file) => body.append('files', file))
        result = await api<ImportResult>('/api/asset-pool/media/import', { method: 'POST', body })
      }
      await load()
      setImportOpen(false)
      setImportText('')
      setBatchFiles([])
      setMessage(`素材导入完成：新增 ${result.created} 条。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally { setBusy(false) }
  }

  const deleteOne = async (asset: Asset) => {
    if (busy || !window.confirm(`确认删除素材“${asset.name}”？`)) return
    setBusy(true)
    try {
      await api(`/api/asset-pool/${asset.id}`, { method: 'DELETE' })
      setSelected((current) => current.filter((id) => id !== asset.id))
      await load()
      setMessage('素材已删除。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally { setBusy(false) }
  }

  const deleteSelected = async () => {
    if (selected.length === 0 || busy) return
    setBusy(true)
    try {
      const result = await api<{ deleted: number }>('/api/asset-pool/batch/delete', {
        method: 'POST',
        body: JSON.stringify({ asset_ids: selected }),
      })
      setSelected([])
      await load()
      setMessage(`已删除 ${result.deleted} 条素材。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally { setBusy(false) }
  }

  const textCount = items.filter((item) => item.asset_type === 'text').length
  const imageCount = items.filter((item) => item.asset_type === 'image').length
  const videoCount = items.filter((item) => item.asset_type === 'video').length

  return (
    <main className="prepare-workspace resource-pool-workspace asset-pool-workspace">
      <WorkspaceHeader
        title="素材池"
        description="文案、图片和视频统一进入素材池。支持单个添加和批量导入；创建素材不会立即创建发布任务。"
        actions={<><Button onClick={() => { setCreateMode('text'); setCreateOpen(true) }}>+ 添加素材</Button><Button variant="primary" onClick={() => { setImportMode('text'); setImportOpen(true) }}>批量导入</Button></>}
      />
      <PrepareNav />
      {message && <div className="prepare-message">{message}</div>}

      <div className="resource-pool-summary"><div><span>素材总数</span><strong>{items.length}</strong></div><div><span>文案</span><strong>{textCount}</strong></div><div><span>图片</span><strong>{imageCount}</strong></div><div><span>视频</span><strong>{videoCount}</strong></div></div>

      <section className="resource-pool-shell">
        <div className="resource-pool-toolbar"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索名称、文案、文件名或平台…" /><span>素材池是可编辑 Source；后续发布任务会冻结自己的内容快照。</span></div>

        {selected.length > 0 && <div className="environment-selection-bar"><strong>已选择 {selected.length} 条素材</strong><span>批量操作只作用于当前选择。</span><div><Button variant="danger" onClick={deleteSelected} disabled={busy}>删除所选</Button></div></div>}

        <div className="asset-pool-table" role="table" aria-label="素材池">
          <div className="asset-pool-row asset-pool-row--head" role="row"><div><input type="checkbox" checked={allVisibleSelected} onChange={toggleVisible} aria-label="选择全部可见素材" /></div><div>素材</div><div>类型</div><div>平台</div><div>大小</div><div>创建时间</div><div>操作</div></div>
          {filtered.length === 0 ? <EmptyState title="素材池为空" description="可以添加单个文案 / 图片 / 视频，也可以批量导入。" /> : filtered.map((item) => (
            <div className="asset-pool-row" role="row" key={item.id}>
              <div><input type="checkbox" checked={selectedSet.has(item.id)} onChange={() => setSelected((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} aria-label={`选择 ${item.name}`} /></div>
              <div className="asset-pool-primary"><strong>{item.name}</strong><span>{item.asset_type === 'text' ? (item.text_content || '').slice(0, 72) : item.original_name || '媒体素材'}</span></div>
              <div><StatusChip tone={item.asset_type === 'text' ? 'info' : 'neutral'}>{typeLabel(item.asset_type)}</StatusChip></div>
              <div>{platformLabel(item.platform)}</div>
              <div>{sizeLabel(item.file_size)}</div>
              <div>{formatDateTime(item.created_at)}</div>
              <div className="asset-pool-actions">{item.asset_type !== 'text' && <a className="sp-inline-link" href={`/api/asset-pool/${item.id}/file`} target="_blank" rel="noreferrer">预览</a>}<button type="button" onClick={() => deleteOne(item)} disabled={busy}>删除</button></div>
            </div>
          ))}
        </div>
      </section>

      {createOpen && <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setCreateOpen(false)}><div className="sp-form-dialog resource-import-dialog" role="dialog" aria-modal="true" aria-label="添加素材" onMouseDown={(event) => event.stopPropagation()}><form onSubmit={createAsset}><header><div><span>素材池</span><h2>添加素材</h2></div><button type="button" onClick={() => setCreateOpen(false)} disabled={busy}>×</button></header><div className="resource-import-body"><div className="resource-mode-switch"><button type="button" className={createMode === 'text' ? 'is-active' : ''} onClick={() => setCreateMode('text')}>文案</button><button type="button" className={createMode === 'media' ? 'is-active' : ''} onClick={() => setCreateMode('media')}>图片 / 视频</button></div><div className="resource-entry-grid"><label><span>素材名称</span><input name="name" required /></label><label><span>平台</span><select name="platform" defaultValue="generic"><option value="generic">通用</option><option value="facebook">Facebook</option><option value="instagram">Instagram</option></select></label></div>{createMode === 'text' ? <label><span>文案内容</span><textarea name="text" rows={12} required /></label> : <label className="resource-file-picker"><span>选择图片或视频</span><input type="file" accept="image/*,video/*" onChange={(event) => setSingleFile(event.target.files?.[0] ?? null)} required /></label>}<div className="account-dialog-hint">添加素材只进入素材池，不会自动创建发布 Job。</div></div><footer><Button type="button" onClick={() => setCreateOpen(false)} disabled={busy}>取消</Button><Button type="submit" variant="primary" disabled={busy}>{busy ? '保存中…' : '保存素材'}</Button></footer></form></div></div>}

      {importOpen && <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setImportOpen(false)}><div className="sp-form-dialog resource-import-dialog" role="dialog" aria-modal="true" aria-label="批量导入素材" onMouseDown={(event) => event.stopPropagation()}><form onSubmit={importAssets}><header><div><span>素材池</span><h2>批量导入素材</h2></div><button type="button" onClick={() => setImportOpen(false)} disabled={busy}>×</button></header><div className="resource-import-body"><div className="resource-mode-switch"><button type="button" className={importMode === 'text' ? 'is-active' : ''} onClick={() => setImportMode('text')}>文案 CSV</button><button type="button" className={importMode === 'media' ? 'is-active' : ''} onClick={() => setImportMode('media')}>批量媒体</button></div>{importMode === 'text' ? <><label className="resource-file-picker"><span>读取 CSV</span><input type="file" accept=".csv,text/csv" onChange={async (event) => { const file = event.target.files?.[0]; if (file) setImportText(await file.text()) }} /></label><label><span>CSV 内容</span><textarea rows={14} value={importText} onChange={(event) => setImportText(event.target.value)} placeholder={'名称,平台,文案\n产品A-01,facebook,"Summer sale..."\n产品A-02,generic,"Second copy..."'} /></label></> : <><label><span>平台</span><select name="platform" defaultValue="generic"><option value="generic">通用</option><option value="facebook">Facebook</option><option value="instagram">Instagram</option></select></label><label className="resource-file-picker"><span>选择多个图片 / 视频</span><input type="file" accept="image/*,video/*" multiple onChange={(event) => setBatchFiles(Array.from(event.target.files ?? []))} /></label><div className="account-dialog-hint">已选择 {batchFiles.length} 个文件；每个文件会作为独立素材进入素材池。</div></>} </div><footer><Button type="button" onClick={() => setImportOpen(false)} disabled={busy}>取消</Button><Button type="submit" variant="primary" disabled={busy}>{busy ? '导入中…' : '开始导入'}</Button></footer></form></div></div>}
    </main>
  )
}
