import React, { FormEvent, useEffect, useMemo, useState } from 'react'

export type ComposerProfile = {
  profile_id: number
  name: string
  group_name?: string | null
  is_available: boolean
}

type PlatformCapability = {
  name: string
  display_name: string
  supports_text: boolean
  media_types: string[]
}

type MediaAsset = {
  id: string
  media_type: string
  original_name: string
  mime_type: string
  file_size: number
  sort_order: number
}

type PublishJob = {
  id: string
  profile_id: number
  platform: string
  status: string
  worker_task_id?: string | null
  published_url?: string | null
  error_message?: string | null
}

type ContentItem = {
  id: string
  platform: string
  text: string
  status: string
  media: MediaAsset[]
  jobs: PublishJob[]
  created_at: string
}

type Props = {
  profiles: ComposerProfile[]
  onMessage: (message: string | null) => void
}

const platformLabels: Record<string, string> = {
  facebook: 'Facebook',
  instagram: 'Instagram',
  x: 'X',
  tiktok: 'TikTok',
  threads: 'Threads',
  linkedin: 'LinkedIn',
  youtube: 'YouTube',
  pinterest: 'Pinterest',
  other: '其他',
}

const statusLabels: Record<string, string> = {
  draft: '草稿',
  queued: '排队中',
  running: '执行中',
  succeeded: '成功',
  failed: '失败',
  blocked: '已阻止',
  interrupted: '已中断',
  needs_review: '待人工确认',
}

function platformLabel(value: string) {
  return platformLabels[value] ?? value
}

function statusLabel(value: string) {
  return statusLabels[value] ?? value
}

function mediaTypeLabel(value: string) {
  if (value === 'image') return '图片'
  if (value === 'video') return '视频'
  return value
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`
  return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

function shortId(value: string) {
  return value.slice(0, 8)
}

function isRunnable(content: ContentItem) {
  return content.jobs.some((job) => job.status === 'draft' || job.status === 'failed')
}

export default function ContentComposer({ profiles, onMessage }: Props) {
  const [platforms, setPlatforms] = useState<PlatformCapability[]>([])
  const [platform, setPlatform] = useState('facebook')
  const [text, setText] = useState('')
  const [selectedProfiles, setSelectedProfiles] = useState<number[]>([])
  const [files, setFiles] = useState<File[]>([])
  const [contents, setContents] = useState<ContentItem[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [publishingId, setPublishingId] = useState<string | null>(null)

  const availableProfiles = useMemo(
    () => profiles.filter((profile) => profile.is_available),
    [profiles],
  )

  const selectedSet = useMemo(() => new Set(selectedProfiles), [selectedProfiles])
  const profileById = useMemo(
    () => new Map(profiles.map((profile, index) => [profile.profile_id, { profile, index }])),
    [profiles],
  )

  const loadPlatforms = async () => {
    const response = await fetch('/api/platforms')
    if (!response.ok) throw new Error(`加载平台能力失败（HTTP ${response.status}）。`)
    const data = await response.json() as { items: PlatformCapability[] }
    setPlatforms(data.items)
    if (data.items.length > 0 && !data.items.some((item) => item.name === platform)) {
      setPlatform(data.items[0].name)
    }
  }

  const loadContents = async () => {
    const response = await fetch('/api/contents?limit=20')
    if (!response.ok) throw new Error(`加载内容草稿失败（HTTP ${response.status}）。`)
    setContents(await response.json() as ContentItem[])
  }

  useEffect(() => {
    Promise.all([loadPlatforms(), loadContents()]).catch((error: Error) => onMessage(error.message))

    const timer = window.setInterval(() => {
      loadContents().catch(() => undefined)
    }, 3000)
    return () => window.clearInterval(timer)
  }, [])

  const toggleProfile = (profileId: number) => {
    setSelectedProfiles((current) =>
      current.includes(profileId)
        ? current.filter((item) => item !== profileId)
        : [...current, profileId],
    )
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (selectedProfiles.length === 0) {
      onMessage('请至少选择一个 iX 环境。')
      return
    }
    if (!text.trim() && files.length === 0) {
      onMessage('请填写帖子文案、添加图片/视频，或同时添加两者。')
      return
    }

    setSubmitting(true)
    onMessage(null)
    const form = new FormData()
    form.append('platform', platform)
    form.append('text', text)
    form.append('profile_ids', JSON.stringify(selectedProfiles))
    files.forEach((file) => form.append('files', file))

    try {
      const response = await fetch('/api/contents', { method: 'POST', body: form })
      if (!response.ok) {
        let detail = `请求失败（HTTP ${response.status}）`
        try {
          const data = await response.json()
          detail = data.detail ?? detail
        } catch {
          // 保留 HTTP 状态作为兜底错误信息。
        }
        throw new Error(detail)
      }

      const created = await response.json() as ContentItem
      setText('')
      setFiles([])
      setSelectedProfiles([])
      await loadContents()
      onMessage(
        `草稿 ${shortId(created.id)} 已创建：${created.jobs.length} 个 iX 环境，${created.media.length} 个媒体文件。`,
      )
    } catch (error) {
      onMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setSubmitting(false)
    }
  }

  const publishNow = async (content: ContentItem) => {
    setPublishingId(content.id)
    onMessage(null)
    try {
      const response = await fetch(`/api/contents/${content.id}/run`, { method: 'POST' })
      if (!response.ok) {
        let detail = `请求失败（HTTP ${response.status}）`
        try {
          const data = await response.json()
          detail = data.detail ?? detail
        } catch {
          // 保留 HTTP 状态作为兜底错误信息。
        }
        throw new Error(detail)
      }
      const result = await response.json() as { queued_count: number }
      await loadContents()
      onMessage(`草稿 ${shortId(content.id)} 已加入 ${result.queued_count} 个发布任务。`)
    } catch (error) {
      onMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setPublishingId(null)
    }
  }

  const removeContent = async (content: ContentItem) => {
    if (!window.confirm(`确定删除草稿 ${shortId(content.id)} 及其本地媒体文件吗？`)) return
    try {
      const response = await fetch(`/api/contents/${content.id}`, { method: 'DELETE' })
      if (!response.ok) {
        let detail = `删除失败（HTTP ${response.status}）。`
        try {
          const data = await response.json()
          detail = data.detail ?? detail
        } catch {
          // 保留 HTTP 状态作为兜底错误信息。
        }
        throw new Error(detail)
      }
      await loadContents()
      onMessage(`草稿 ${shortId(content.id)} 已删除。`)
    } catch (error) {
      onMessage(error instanceof Error ? error.message : String(error))
    }
  }

  return (
    <>
      <section className="panel composer-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">内容中心</p>
            <h2>创建发布草稿</h2>
          </div>
          <span className="section-meta">支持图片和视频</span>
        </div>

        <form className="composer" onSubmit={submit}>
          <div className="composer-main">
            <label className="field-block">
              <span>发布平台</span>
              <select value={platform} onChange={(event) => setPlatform(event.target.value)}>
                {platforms.length === 0 && <option value="facebook">Facebook</option>}
                {platforms.map((item) => (
                  <option key={item.name} value={item.name}>{platformLabel(item.name)}</option>
                ))}
              </select>
            </label>

            <label className="field-block">
              <span>帖子文案</span>
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder="输入要发布的内容…"
                rows={7}
              />
            </label>

            <label className="media-picker">
              <span>添加图片 / 视频</span>
              <input
                type="file"
                accept="image/*,video/*"
                multiple
                onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
              />
            </label>

            {files.length > 0 && (
              <div className="selected-media">
                {files.map((file, index) => (
                  <div className="selected-media-item" key={`${file.name}-${file.lastModified}-${index}`}>
                    <span className={`media-kind ${file.type.startsWith('video/') ? 'video' : 'image'}`}>
                      {file.type.startsWith('video/') ? '视频' : '图片'}
                    </span>
                    <div>
                      <strong>{file.name}</strong>
                      <small>{formatBytes(file.size)}</small>
                    </div>
                    <button
                      type="button"
                      className="text-button danger"
                      onClick={() => setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                    >
                      移除
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <aside className="profile-selector">
            <div className="profile-selector-head">
              <div>
                <span>目标 iX 环境</span>
                <strong>已选择 {selectedProfiles.length} 个</strong>
              </div>
              <div className="selector-actions">
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setSelectedProfiles(availableProfiles.map((item) => item.profile_id))}
                >
                  全选
                </button>
                <button type="button" className="text-button" onClick={() => setSelectedProfiles([])}>
                  清空
                </button>
              </div>
            </div>

            <div className="profile-options">
              {availableProfiles.length === 0 ? (
                <div className="profile-selector-empty">请先同步 iX 环境。</div>
              ) : availableProfiles.map((profile, index) => (
                <label className={`profile-option ${selectedSet.has(profile.profile_id) ? 'selected' : ''}`} key={profile.profile_id}>
                  <input
                    type="checkbox"
                    checked={selectedSet.has(profile.profile_id)}
                    onChange={() => toggleProfile(profile.profile_id)}
                  />
                  <span className="profile-sequence">{String(index + 1).padStart(3, '0')}</span>
                  <span className="profile-option-copy">
                    <strong>{profile.name}</strong>
                    <small>iX #{profile.profile_id}{profile.group_name ? ` · ${profile.group_name}` : ''}</small>
                  </span>
                </label>
              ))}
            </div>

            <button className="primary create-draft-button" disabled={submitting} type="submit">
              {submitting ? '正在保存媒体…' : '创建草稿'}
            </button>
          </aside>
        </form>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">发布队列</p>
            <h2>最近内容</h2>
          </div>
          <span className="section-meta">最近 {contents.length} 条</span>
        </div>

        {contents.length === 0 ? (
          <div className="empty-state compact-empty">
            <strong>暂无内容草稿</strong>
            <span>可以在上方使用文字、图片、视频或组合方式创建草稿。</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="content-table">
              <thead>
                <tr>
                  <th>草稿</th>
                  <th>平台</th>
                  <th>内容</th>
                  <th>媒体</th>
                  <th>目标任务</th>
                  <th>状态</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {contents.map((content) => (
                  <tr key={content.id}>
                    <td><strong>{shortId(content.id)}</strong></td>
                    <td><span className="platform-pill">{platformLabel(content.platform)}</span></td>
                    <td className="content-copy" title={content.text}>{content.text || '仅媒体帖子'}</td>
                    <td>
                      <div className="media-summary">
                        {content.media.length === 0 ? (
                          <span>无</span>
                        ) : content.media.map((asset) => (
                          <a
                            key={asset.id}
                            href={`/api/media/${asset.id}/file`}
                            target="_blank"
                            rel="noreferrer"
                            title={`${asset.original_name} · ${formatBytes(asset.file_size)}`}
                          >
                            {mediaTypeLabel(asset.media_type)}
                          </a>
                        ))}
                      </div>
                    </td>
                    <td>
                      <div className="job-targets">
                        {content.jobs.map((job) => {
                          const meta = profileById.get(job.profile_id)
                          const sequence = meta ? String(meta.index + 1).padStart(3, '0') : `#${job.profile_id}`
                          const label = meta?.profile.name || `iX #${job.profile_id}`
                          return (
                            <div className="job-target" key={job.id} title={job.error_message || label}>
                              <span>{sequence}</span>
                              <strong>{label}</strong>
                              <em className={`task-status task-${job.status}`}>{statusLabel(job.status)}</em>
                              {job.published_url && (
                                <a href={job.published_url} target="_blank" rel="noreferrer">查看帖子</a>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </td>
                    <td><span className={`task-status task-${content.status}`}>{statusLabel(content.status)}</span></td>
                    <td className="actions content-actions">
                      <button
                        className="compact-button worker-button"
                        onClick={() => publishNow(content)}
                        disabled={publishingId === content.id || !isRunnable(content)}
                        title={isRunnable(content) ? '立即将所有草稿/失败目标加入发布队列' : '当前没有可执行的目标任务'}
                      >
                        {publishingId === content.id ? '加入队列…' : '立即发布'}
                      </button>
                      <button
                        className="text-button danger"
                        onClick={() => removeContent(content)}
                        disabled={content.jobs.some((job) => job.status === 'queued' || job.status === 'running')}
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}
