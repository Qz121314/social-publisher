import React, { FormEvent, useEffect, useMemo, useState } from 'react'

import { api, formatDateTime } from '../../app/api'
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

type PlatformInfo = {
  name: string
  display_name: string
  supports_text: boolean
  media_types: string[]
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

type BrowserProfile = {
  profile_id: number
  name: string
  group_id?: number | null
  group_name?: string | null
  is_available: boolean
}

type PublishMode = 'immediate' | 'scheduled' | 'draft'

type PublishPlan = {
  id: string
  publish_mode: PublishMode
  status: string
  scheduled_at?: string | null
  interval_seconds: number
  flow_revision_id: string
  jobs: Array<{ id: string; status: string; scheduled_at?: string | null }>
}

type ChannelGroup = {
  key: string
  label: string
  channels: Channel[]
}

function shortText(value: string, length = 56) {
  const normalized = value.replace(/\s+/g, ' ').trim()
  if (!normalized) return '仅媒体素材'
  return normalized.length > length ? `${normalized.slice(0, length)}…` : normalized
}

function platformDisplay(platform: string) {
  if (platform === 'facebook') return 'Facebook'
  if (platform === 'instagram') return 'Instagram'
  return platform
}

function channelTypeLabel(channel: Channel) {
  if (channel.platform === 'facebook') return channel.target_type === 'page' ? '公共主页' : '个人主页'
  if (channel.platform === 'instagram') return 'Feed 账号'
  return channel.target_type
}

export default function PublisherPage() {
  const [platforms, setPlatforms] = useState<PlatformInfo[]>([])
  const [platform, setPlatform] = useState('facebook')
  const [assets, setAssets] = useState<Asset[]>([])
  const [channels, setChannels] = useState<Channel[]>([])
  const [profiles, setProfiles] = useState<BrowserProfile[]>([])
  const [selectedAssetId, setSelectedAssetId] = useState('')
  const [selectedChannels, setSelectedChannels] = useState<string[]>([])
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [fileKey, setFileKey] = useState(0)
  const [publishMode, setPublishMode] = useState<PublishMode>('immediate')
  const [scheduledAt, setScheduledAt] = useState('')
  const [intervalSeconds, setIntervalSeconds] = useState(10)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const loadStatic = async () => {
    const [platformResult, assetItems, profileItems] = await Promise.all([
      api<{ items: PlatformInfo[] }>('/api/platforms'),
      api<Asset[]>('/api/assets?limit=100'),
      api<BrowserProfile[]>('/api/browser-profiles'),
    ])
    setPlatforms(platformResult.items)
    setAssets(assetItems)
    setProfiles(profileItems)
    if (!platformResult.items.some((item) => item.name === platform)) {
      setPlatform(platformResult.items[0]?.name || 'facebook')
    }
  }

  const loadChannels = async (selectedPlatform: string) => {
    const items = await api<Channel[]>(`/api/channels?platform=${encodeURIComponent(selectedPlatform)}&enabled=true`)
    setChannels(items)
  }

  useEffect(() => {
    loadStatic().catch((error) => setMessage(error instanceof Error ? error.message : String(error)))
  }, [])

  useEffect(() => {
    setSelectedAssetId('')
    setSelectedChannels([])
    setText('')
    setFiles([])
    setFileKey((value) => value + 1)
    loadChannels(platform).catch((error) => setMessage(error instanceof Error ? error.message : String(error)))
  }, [platform])

  const platformAssets = useMemo(
    () => assets.filter((item) => item.platform === platform),
    [assets, platform],
  )
  const selectedAsset = useMemo(
    () => platformAssets.find((item) => item.id === selectedAssetId),
    [platformAssets, selectedAssetId],
  )
  const selectedSet = useMemo(() => new Set(selectedChannels), [selectedChannels])
  const profileById = useMemo(
    () => new Map(profiles.map((profile) => [profile.profile_id, profile])),
    [profiles],
  )

  const groups = useMemo<ChannelGroup[]>(() => {
    const grouped = new Map<string, ChannelGroup>()
    channels.forEach((channel) => {
      const profile = profileById.get(channel.profile_id)
      const groupKey = profile?.group_id != null
        ? `group:${profile.group_id}`
        : `name:${profile?.group_name || 'ungrouped'}`
      const label = profile?.group_name?.trim() || '未分组'
      const current = grouped.get(groupKey) ?? { key: groupKey, label, channels: [] }
      current.channels.push(channel)
      grouped.set(groupKey, current)
    })
    return Array.from(grouped.values())
      .map((group) => ({
        ...group,
        channels: group.channels.sort((a, b) => a.profile_id - b.profile_id || a.target_name.localeCompare(b.target_name)),
      }))
      .sort((a, b) => {
        if (a.label === '未分组') return 1
        if (b.label === '未分组') return -1
        return a.label.localeCompare(b.label)
      })
  }, [channels, profileById])

  const selectedProfileCount = useMemo(() => {
    const selectedProfiles = new Set(
      channels.filter((channel) => selectedSet.has(channel.id)).map((channel) => channel.profile_id),
    )
    return selectedProfiles.size
  }, [channels, selectedSet])

  const toggleChannel = (channelId: string) => {
    setSelectedChannels((current) => current.includes(channelId)
      ? current.filter((item) => item !== channelId)
      : [...current, channelId])
  }

  const toggleGroup = (group: ChannelGroup) => {
    const groupIds = group.channels.map((channel) => channel.id)
    const allSelected = groupIds.every((channelId) => selectedSet.has(channelId))
    setSelectedChannels((current) => {
      if (allSelected) {
        const groupSet = new Set(groupIds)
        return current.filter((channelId) => !groupSet.has(channelId))
      }
      const next = [...current]
      groupIds.forEach((channelId) => {
        if (!next.includes(channelId)) next.push(channelId)
      })
      return next
    })
  }

  const toggleAll = () => {
    if (channels.length > 0 && channels.every((channel) => selectedSet.has(channel.id))) {
      setSelectedChannels([])
      return
    }
    setSelectedChannels(channels.map((channel) => channel.id))
  }

  const createTemporaryAsset = async () => {
    const form = new FormData()
    form.append('platform', platform)
    form.append('text', text)
    files.forEach((file) => form.append('files', file))
    return api<Asset>('/api/assets/upload', { method: 'POST', body: form })
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (selectedChannels.length === 0) {
      setMessage(`请至少选择一个 ${platformDisplay(platform)} Channel。`)
      return
    }
    if (!selectedAsset && !text.trim() && files.length === 0) {
      setMessage('请选择已有素材，或填写文案 / 添加媒体。')
      return
    }
    if (platform === 'instagram' && !selectedAsset && files.length === 0) {
      setMessage('Instagram Feed Post 至少需要 1 个图片或视频。')
      return
    }
    if (selectedAsset && platform === 'instagram' && selectedAsset.media.length === 0) {
      setMessage('这个 Instagram 素材没有媒体，Feed Post 无法发布。')
      return
    }
    if (publishMode === 'scheduled' && !scheduledAt) {
      setMessage('请选择定时发布时间。')
      return
    }
    if (!Number.isInteger(intervalSeconds) || intervalSeconds < 0 || intervalSeconds > 3600) {
      setMessage('发布间隔必须是 0–3600 秒之间的整数。')
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
          publish_mode: publishMode,
          timezone,
          scheduled_at: publishMode === 'scheduled' ? scheduledAt : null,
          interval_seconds: intervalSeconds,
          flow_revision_id: null,
        }),
      })

      const batchText = `${plan.jobs.length} 个 PublishJob，间隔 ${plan.interval_seconds} 秒`
      if (publishMode === 'immediate') {
        setMessage(`${platformDisplay(platform)} 发布计划 ${plan.id.slice(0, 8)} 已进入 Scheduler：${batchText}。同一 iX 环境仍强制串行。`)
      } else if (publishMode === 'scheduled') {
        setMessage(`${platformDisplay(platform)} 发布计划 ${plan.id.slice(0, 8)} 已保存到 SQLite，将从 ${formatDateTime(plan.scheduled_at)} 开始执行 ${plan.jobs.length} 个任务。`)
      } else {
        setMessage(`${platformDisplay(platform)} 草稿计划 ${plan.id.slice(0, 8)} 已保存：${batchText}。`)
      }

      setSelectedAssetId('')
      setSelectedChannels([])
      setText('')
      setFiles([])
      setFileKey((value) => value + 1)
      setScheduledAt('')
      await loadStatic()
      await loadChannels(platform)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const actionLabel = publishMode === 'immediate'
    ? `创建并立即发布到 ${platformDisplay(platform)}`
    : publishMode === 'scheduled'
      ? `创建 ${platformDisplay(platform)} 定时发布`
      : '保存草稿计划'

  const estimatedSpan = Math.max(0, selectedChannels.length - 1) * intervalSeconds

  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="发布中心"
        title="创建多平台批量发布"
        description="同一套 Asset → PublishPlan → PublishJob → Scheduler 流水线现在支持 Facebook 与 Instagram。"
        actions={<PhaseBadge>Phase 8</PhaseBadge>}
      />

      {message && <div className="notice">{message}</div>}

      <section className="v1-panel">
        <div className="v1-panel-heading"><div><h2>发布平台</h2><p>一个 PublishPlan 仍只绑定一个平台，避免跨平台 Flow 和验证语义混在同一批任务中。</p></div></div>
        <div className="filter-row">
          {platforms.map((item) => (
            <button
              key={item.name}
              type="button"
              className={`compact-button ${platform === item.name ? 'worker-button' : ''}`}
              onClick={() => setPlatform(item.name)}
            >
              {item.display_name}
            </button>
          ))}
        </div>
        {platform === 'instagram' && <p className="v1-inline-note">Instagram Phase 8A 当前支持 Feed 图片 / 视频 / 多媒体 Post。至少需要 1 个媒体；Story、音乐、协作者等不在本阶段。</p>}
      </section>

      <form className="v1-publisher-grid" onSubmit={submit}>
        <section className="v1-panel v1-publisher-content">
          <div className="v1-panel-heading"><div><h2>1. 内容 / 素材</h2><p>只显示与当前平台匹配的 Asset，也可以临时创建新素材。</p></div></div>

          <label className="field-block">
            <span>已有素材</span>
            <select value={selectedAssetId} onChange={(event) => setSelectedAssetId(event.target.value)}>
              <option value="">临时创建新素材</option>
              {platformAssets.map((asset) => <option key={asset.id} value={asset.id}>{shortText(asset.text)} · {asset.media.length} 个媒体</option>)}
            </select>
          </label>

          {selectedAsset ? (
            <div className="v1-asset-preview">
              <strong>{shortText(selectedAsset.text, 120)}</strong>
              <span>{selectedAsset.media.length > 0 ? selectedAsset.media.map((item) => item.original_name).join(' · ') : '无媒体'}</span>
              <small>{platformDisplay(selectedAsset.platform)} Asset #{selectedAsset.id.slice(0, 8)}</small>
            </div>
          ) : (
            <>
              <label className="field-block">
                <span>{platform === 'instagram' ? 'Caption' : '帖子文案'}</span>
                <textarea value={text} onChange={(event) => setText(event.target.value)} rows={9} placeholder={`输入 ${platformDisplay(platform)} ${platform === 'instagram' ? 'Caption' : '帖子正文'}…`} />
              </label>
              <label className="field-block">
                <span>图片 / 视频{platform === 'instagram' ? '（必需）' : ''}</span>
                <input key={fileKey} type="file" multiple accept="image/*,video/*" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} />
              </label>
              {files.length > 0 && <div className="v1-file-summary">已选择 {files.length} 个文件：{files.map((file) => file.name).join(' · ')}</div>}
            </>
          )}
        </section>

        <section className="v1-panel v1-publisher-targets">
          <div className="v1-panel-heading">
            <div><h2>2. 发布目标</h2><p>按 iX 分组整组选择当前平台 Channel，也可以逐个调整。</p></div>
            <span className="v1-muted">{selectedChannels.length} Channels / {selectedProfileCount} iX</span>
          </div>

          <div className="v1-batch-toolbar">
            <button type="button" className="compact-button" onClick={toggleAll} disabled={channels.length === 0}>
              {channels.length > 0 && channels.every((channel) => selectedSet.has(channel.id)) ? '取消全选' : '全选全部'}
            </button>
            <span className="v1-muted">当前平台：{platformDisplay(platform)} · 执行顺序会冻结到 PublishPlan。</span>
          </div>

          <div className="v1-group-picker">
            {channels.length === 0 ? (
              <div className="empty-state compact-empty"><strong>暂无可发布 Channel</strong><span>先到 iX账号中心配置 {platformDisplay(platform)} Channel。</span></div>
            ) : groups.map((group) => {
              const selectedCount = group.channels.filter((channel) => selectedSet.has(channel.id)).length
              const allSelected = selectedCount === group.channels.length && group.channels.length > 0
              return (
                <section className="v1-channel-group" key={group.key}>
                  <div className="v1-channel-group-heading">
                    <div><strong>{group.label}</strong><small>{selectedCount}/{group.channels.length} 已选</small></div>
                    <button type="button" className="compact-button" onClick={() => toggleGroup(group)}>{allSelected ? '取消整组' : '选择整组'}</button>
                  </div>
                  <div className="v1-channel-picker">
                    {group.channels.map((channel) => {
                      const profile = profileById.get(channel.profile_id)
                      return (
                        <label className={`v1-channel-option ${selectedSet.has(channel.id) ? 'selected' : ''}`} key={channel.id}>
                          <input type="checkbox" checked={selectedSet.has(channel.id)} onChange={() => toggleChannel(channel.id)} />
                          <span>
                            <strong>{channel.platform === 'instagram' ? `@${channel.target_name}` : channel.target_name}</strong>
                            <small>iX #{channel.profile_id} {profile?.name ? `· ${profile.name}` : ''} · {channelTypeLabel(channel)} · {channel.health_status}</small>
                          </span>
                        </label>
                      )
                    })}
                  </div>
                </section>
              )
            })}
          </div>

          <div className="v1-schedule-box">
            <strong>3. 发布方式</strong>
            <label><input type="radio" name="publish-mode" checked={publishMode === 'immediate'} onChange={() => setPublishMode('immediate')} /> 立即发布</label>
            <label><input type="radio" name="publish-mode" checked={publishMode === 'scheduled'} onChange={() => setPublishMode('scheduled')} /> 定时发布</label>
            <label><input type="radio" name="publish-mode" checked={publishMode === 'draft'} onChange={() => setPublishMode('draft')} /> 保存草稿</label>
            {publishMode === 'scheduled' && (
              <label className="field-block v1-scheduled-input">
                <span>本地发布时间</span>
                <input type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} />
                <small>时区：{Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'}</small>
              </label>
            )}
          </div>

          <div className="v1-batch-options">
            <label className="field-block">
              <span>发布间隔（秒）</span>
              <input
                type="number"
                min={0}
                max={3600}
                step={1}
                value={intervalSeconds}
                onChange={(event) => setIntervalSeconds(Number(event.target.value))}
              />
              <small>固定间隔写入每个 Job 的 scheduled_at；0 表示连续调度，但同一 Profile 仍不会并发。</small>
            </label>
            <div className="v1-batch-estimate">
              <span>本批任务</span><strong>{selectedChannels.length}</strong>
              <small>预计调度跨度 {estimatedSpan}s</small>
            </div>
          </div>

          <button type="submit" className="primary" disabled={busy || channels.length === 0}>{busy ? '创建中…' : actionLabel}</button>
        </section>
      </form>
    </main>
  )
}
