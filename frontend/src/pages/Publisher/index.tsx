import React, { FormEvent, useEffect, useMemo, useState } from 'react'

import { api } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'

type MediaAsset = {
  id: string
  media_type: string
  original_name: string
}

type Asset = {
  id: string
  platform: string
  text: string
  media: MediaAsset[]
  created_at: string
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

type PublishPlan = {
  id: string
  flow_revision_id: string
  jobs: Array<{ id: string; status: string }>
}

function shortText(value: string, length = 56) {
  const normalized = value.replace(/\s+/g, ' ').trim()
  if (!normalized) return '仅媒体素材'
  return normalized.length > length ? `${normalized.slice(0, length)}…` : normalized
}

export default function PublisherPage() {
  const [assets, setAssets] = useState<Asset[]>([])
  const [channels, setChannels] = useState<Channel[]>([])
  const [selectedAssetId, setSelectedAssetId] = useState('')
  const [selectedChannels, setSelectedChannels] = useState<string[]>([])
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [fileKey, setFileKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = async () => {
    const [assetItems, channelItems] = await Promise.all([
      api<Asset[]>('/api/assets?limit=30'),
      api<Channel[]>('/api/channels?platform=facebook&enabled=true'),
    ])
    setAssets(assetItems)
    setChannels(channelItems)
  }

  useEffect(() => {
    load().catch((error) => setMessage(error instanceof Error ? error.message : String(error)))
  }, [])

  const selectedAsset = useMemo(
    () => assets.find((item) => item.id === selectedAssetId),
    [assets, selectedAssetId],
  )
  const selectedSet = useMemo(() => new Set(selectedChannels), [selectedChannels])

  const toggleChannel = (channelId: string) => {
    setSelectedChannels((current) => current.includes(channelId)
      ? current.filter((item) => item !== channelId)
      : [...current, channelId])
  }

  const createTemporaryAsset = async () => {
    const form = new FormData()
    form.append('platform', 'facebook')
    form.append('text', text)
    files.forEach((file) => form.append('files', file))
    return api<Asset>('/api/assets/upload', { method: 'POST', body: form })
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (selectedChannels.length === 0) {
      setMessage('请至少选择一个 Facebook Channel。')
      return
    }
    if (!selectedAsset && !text.trim() && files.length === 0) {
      setMessage('请选择已有素材，或填写文案 / 添加媒体。')
      return
    }

    setBusy(true)
    setMessage(null)
    try {
      const asset = selectedAsset ?? await createTemporaryAsset()
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
      const plan = await api<PublishPlan>('/api/publish-plans', {
        method: 'POST',
        body: JSON.stringify({
          content_id: asset.id,
          channel_ids: selectedChannels,
          publish_mode: 'immediate',
          timezone,
          scheduled_at: null,
          interval_seconds: 0,
          flow_revision_id: null,
        }),
      })
      const result = await api<{ queued_count: number; errors: Array<{ job_id: string; error: string }> }>(`/api/publish-plans/${plan.id}/run`, { method: 'POST' })
      setMessage(`发布计划 ${plan.id.slice(0, 8)} 已创建，${result.queued_count} 个正式 PublishJob 已进入 Worker。${result.errors.length ? ` ${result.errors.length} 个任务未能入队。` : ''}`)
      setSelectedAssetId('')
      setSelectedChannels([])
      setText('')
      setFiles([])
      setFileKey((value) => value + 1)
      await load()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="发布中心"
        title="创建发布"
        description="正式链路：Asset → PublishPlan → Channel Snapshot → PublishJob → PublishAttempt → Facebook Worker。"
        actions={<PhaseBadge>Phase 3</PhaseBadge>}
      />

      {message && <div className="notice">{message}</div>}
      <p className="v1-inline-note">Phase 3 先完成“立即发布”的正式模型迁移。定时发布与立即发布统一调度由 Phase 4 Scheduler 接管；发布间隔与分组批量选择在 Phase 5。</p>

      <form className="v1-publisher-grid" onSubmit={submit}>
        <section className="v1-panel v1-publisher-content">
          <div className="v1-panel-heading"><div><h2>1. 内容 / 素材</h2><p>选择素材中心已有内容，或临时创建一个新 Asset。</p></div></div>

          <label className="field-block">
            <span>已有素材</span>
            <select value={selectedAssetId} onChange={(event) => setSelectedAssetId(event.target.value)}>
              <option value="">临时创建新素材</option>
              {assets.map((asset) => <option key={asset.id} value={asset.id}>{shortText(asset.text)} · {asset.media.length} 个媒体</option>)}
            </select>
          </label>

          {selectedAsset ? (
            <div className="v1-asset-preview">
              <strong>{shortText(selectedAsset.text, 120)}</strong>
              <span>{selectedAsset.media.length > 0 ? selectedAsset.media.map((item) => item.original_name).join(' · ') : '无媒体'}</span>
              <small>Asset #{selectedAsset.id.slice(0, 8)}</small>
            </div>
          ) : (
            <>
              <label className="field-block">
                <span>帖子文案</span>
                <textarea value={text} onChange={(event) => setText(event.target.value)} rows={9} placeholder="输入 Facebook 帖子正文…" />
              </label>
              <label className="field-block">
                <span>图片 / 视频</span>
                <input key={fileKey} type="file" multiple accept="image/*,video/*" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} />
              </label>
              {files.length > 0 && <div className="v1-file-summary">已选择 {files.length} 个文件：{files.map((file) => file.name).join(' · ')}</div>}
            </>
          )}
        </section>

        <section className="v1-panel v1-publisher-targets">
          <div className="v1-panel-heading"><div><h2>2. 发布目标</h2><p>只展示已启用的正式 Facebook Channel。</p></div><span className="v1-muted">已选 {selectedChannels.length}</span></div>

          <div className="v1-channel-picker">
            {channels.length === 0 ? (
              <div className="empty-state compact-empty"><strong>暂无可发布 Channel</strong><span>先到 iX账号中心扫描并选择 Facebook 发布主页。</span></div>
            ) : channels.map((channel) => (
              <label className={`v1-channel-option ${selectedSet.has(channel.id) ? 'selected' : ''}`} key={channel.id}>
                <input type="checkbox" checked={selectedSet.has(channel.id)} onChange={() => toggleChannel(channel.id)} />
                <span><strong>{channel.target_name}</strong><small>iX #{channel.profile_id} · {channel.target_type === 'page' ? '公共主页' : '个人主页'} · {channel.health_status}</small></span>
              </label>
            ))}
          </div>

          <div className="v1-publish-summary">
            <div><span>发布方式</span><strong>立即发布</strong></div>
            <div><span>流程版本</span><strong>当前 Published Revision</strong></div>
            <div><span>任务模型</span><strong>每个 Channel 一个 Job</strong></div>
          </div>

          <button className="primary v1-publish-submit" type="submit" disabled={busy || channels.length === 0}>{busy ? '正在创建任务…' : '创建并立即发布'}</button>
        </section>
      </form>
    </main>
  )
}
