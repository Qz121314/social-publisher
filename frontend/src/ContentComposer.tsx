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
    if (!response.ok) throw new Error(`Unable to load platform capabilities (${response.status}).`)
    const data = await response.json() as { items: PlatformCapability[] }
    setPlatforms(data.items)
    if (data.items.length > 0 && !data.items.some((item) => item.name === platform)) {
      setPlatform(data.items[0].name)
    }
  }

  const loadContents = async () => {
    const response = await fetch('/api/contents?limit=20')
    if (!response.ok) throw new Error(`Unable to load content drafts (${response.status}).`)
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
      onMessage('Select at least one iX profile.')
      return
    }
    if (!text.trim() && files.length === 0) {
      onMessage('Add post text, image/video media, or both.')
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
        let detail = `HTTP ${response.status}`
        try {
          const data = await response.json()
          detail = data.detail ?? detail
        } catch {
          // Keep the HTTP fallback.
        }
        throw new Error(detail)
      }

      const created = await response.json() as ContentItem
      setText('')
      setFiles([])
      setSelectedProfiles([])
      await loadContents()
      onMessage(
        `Draft ${shortId(created.id)} created for ${created.jobs.length} iX profile(s) with ${created.media.length} media file(s).`,
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
        let detail = `HTTP ${response.status}`
        try {
          const data = await response.json()
          detail = data.detail ?? detail
        } catch {
          // Keep fallback.
        }
        throw new Error(detail)
      }
      const result = await response.json() as { queued_count: number }
      await loadContents()
      onMessage(`Queued ${result.queued_count} Facebook publish job(s) for draft ${shortId(content.id)}.`)
    } catch (error) {
      onMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setPublishingId(null)
    }
  }

  const removeContent = async (content: ContentItem) => {
    if (!window.confirm(`Delete draft ${shortId(content.id)} and its local media files?`)) return
    try {
      const response = await fetch(`/api/contents/${content.id}`, { method: 'DELETE' })
      if (!response.ok) {
        let detail = `Delete failed (${response.status}).`
        try {
          const data = await response.json()
          detail = data.detail ?? detail
        } catch {
          // Keep fallback.
        }
        throw new Error(detail)
      }
      await loadContents()
      onMessage(`Draft ${shortId(content.id)} deleted.`)
    } catch (error) {
      onMessage(error instanceof Error ? error.message : String(error))
    }
  }

  return (
    <>
      <section className="panel composer-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">CONTENT CENTER</p>
            <h2>Create publish draft</h2>
          </div>
          <span className="section-meta">Image + video media supported</span>
        </div>

        <form className="composer" onSubmit={submit}>
          <div className="composer-main">
            <label className="field-block">
              <span>Platform</span>
              <select value={platform} onChange={(event) => setPlatform(event.target.value)}>
                {platforms.length === 0 && <option value="facebook">Facebook</option>}
                {platforms.map((item) => (
                  <option key={item.name} value={item.name}>{item.display_name}</option>
                ))}
              </select>
            </label>

            <label className="field-block">
              <span>Post text</span>
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder="Write the post content…"
                rows={7}
              />
            </label>

            <label className="media-picker">
              <span>Add images / videos</span>
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
                      {file.type.startsWith('video/') ? 'VIDEO' : 'IMAGE'}
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
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <aside className="profile-selector">
            <div className="profile-selector-head">
              <div>
                <span>Target iX profiles</span>
                <strong>{selectedProfiles.length} selected</strong>
              </div>
              <div className="selector-actions">
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setSelectedProfiles(availableProfiles.map((item) => item.profile_id))}
                >
                  Select all
                </button>
                <button type="button" className="text-button" onClick={() => setSelectedProfiles([])}>
                  Clear
                </button>
              </div>
            </div>

            <div className="profile-options">
              {availableProfiles.length === 0 ? (
                <div className="profile-selector-empty">Sync iX profiles first.</div>
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
              {submitting ? 'Saving media…' : 'Create draft'}
            </button>
          </aside>
        </form>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">PUBLISH QUEUE</p>
            <h2>Recent content</h2>
          </div>
          <span className="section-meta">{contents.length} recent item(s)</span>
        </div>

        {contents.length === 0 ? (
          <div className="empty-state compact-empty">
            <strong>No content drafts yet</strong>
            <span>Create one above using text, images, videos, or a combination.</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="content-table">
              <thead>
                <tr>
                  <th>Draft</th>
                  <th>Platform</th>
                  <th>Content</th>
                  <th>Media</th>
                  <th>Target jobs</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {contents.map((content) => (
                  <tr key={content.id}>
                    <td><strong>{shortId(content.id)}</strong></td>
                    <td><span className="platform-pill">{content.platform}</span></td>
                    <td className="content-copy" title={content.text}>{content.text || 'Media-only post'}</td>
                    <td>
                      <div className="media-summary">
                        {content.media.length === 0 ? (
                          <span>None</span>
                        ) : content.media.map((asset) => (
                          <a
                            key={asset.id}
                            href={`/api/media/${asset.id}/file`}
                            target="_blank"
                            rel="noreferrer"
                            title={`${asset.original_name} · ${formatBytes(asset.file_size)}`}
                          >
                            {asset.media_type}
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
                              <em className={`task-status task-${job.status}`}>{job.status}</em>
                              {job.published_url && (
                                <a href={job.published_url} target="_blank" rel="noreferrer">Open post</a>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </td>
                    <td><span className={`task-status task-${content.status}`}>{content.status}</span></td>
                    <td className="actions content-actions">
                      <button
                        className="compact-button worker-button"
                        onClick={() => publishNow(content)}
                        disabled={publishingId === content.id || !isRunnable(content)}
                        title={isRunnable(content) ? 'Queue all draft/failed targets now' : 'No runnable target jobs'}
                      >
                        {publishingId === content.id ? 'Queueing…' : 'Publish now'}
                      </button>
                      <button
                        className="text-button danger"
                        onClick={() => removeContent(content)}
                        disabled={content.jobs.some((job) => job.status === 'queued' || job.status === 'running')}
                      >
                        Delete
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
