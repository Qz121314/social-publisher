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
        eyebrow="准备"
        title="素材池"
        description="集中准备文案、图片和视频资源。后续 ContentPackage 会把这些资源组合成可直接用于批量任务的发布内容。"
        actions={<><PhaseBadge /><Link className="v1-link-button" to="/publish">使用素材发布</Link></>}
      />

      {error && <div className="notice">{error}</div>}
      <p className="v1-inline-note">当前素材池继续复用现有 ContentItem 数据源；本轮先统一资源池产品边界，后续再增加文件夹 / ZIP / CSV 批量导入和 ContentPackage。</p>

      <section className="v1-panel">
        <div className="v1-toolbar">
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索文案或平台…" />
          <span className="v1-muted">{filtered.length} 条素材记录</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>内容</th><th>平台</th><th>媒体</th><th>关联任务</th><th>状态</th><th>创建时间</th></tr></thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={6}><div className="empty-state compact-empty"><strong>素材池为空</strong><span>后续可在这里批量导入文案、图片和视频。</span></div></td></tr>
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
