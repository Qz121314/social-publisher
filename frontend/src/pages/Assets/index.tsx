import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, formatDateTime } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'

type ContentItem = {
  id: string
  platform: string
  text: string
  status: string
  created_at: string
  media: { id: string; media_type: string }[]
  jobs: { id: string }[]
}

export default function AssetsPage() {
  const [items, setItems] = useState<ContentItem[]>([])
  const [search, setSearch] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api<ContentItem[]>('/api/contents?limit=100')
      .then(setItems)
      .catch((nextError) => setError(nextError instanceof Error ? nextError.message : String(nextError)))
  }, [])

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) return items
    return items.filter((item) => item.text.toLowerCase().includes(keyword) || item.platform.toLowerCase().includes(keyword))
  }, [items, search])

  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="素材中心"
        title="内容资产"
        description="管理文案和媒体资产。Phase 2 会把当前 ContentItem 正式解耦为 Asset / Content。"
        actions={<><PhaseBadge /><Link className="v1-link-button" to="/publish">使用素材发布</Link></>}
      />

      {error && <div className="notice">{error}</div>}
      <p className="v1-inline-note">当前先以现有 ContentItem 作为素材视图的数据来源；这里不新增账号、时间或调度逻辑，避免在 Phase 1 固化旧模型。</p>

      <section className="v1-panel">
        <div className="v1-toolbar">
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索文案或平台…" />
          <span className="v1-muted">{filtered.length} 条素材记录</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>内容</th><th>平台</th><th>媒体</th><th>旧 Job</th><th>状态</th><th>创建时间</th></tr></thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={6}><div className="empty-state compact-empty"><strong>暂无素材</strong><span>可以先到发布中心创建一条现有 PoC 草稿。</span></div></td></tr>
              ) : filtered.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.text.trim().slice(0, 72) || '仅媒体素材'}</strong><br /><small>#{item.id.slice(0, 8)}</small></td>
                  <td>{item.platform}</td>
                  <td>{item.media.length}</td>
                  <td>{item.jobs.length}</td>
                  <td>{item.status}</td>
                  <td>{formatDateTime(item.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  )
}
