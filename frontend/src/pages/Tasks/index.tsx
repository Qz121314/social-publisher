import React, { useEffect, useMemo, useState } from 'react'

import { api, formatDateTime } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'

type AttemptEvent = {
  id: string
  sequence: number
  stage: string
  message: string
  details_json?: string | null
  created_at: string
}

type PublishAttempt = {
  id: string
  attempt_no: number
  status: string
  stage?: string | null
  total_ms?: number | null
  browser_open_ms?: number | null
  platform_ms?: number | null
  media_ms?: number | null
  verification_ms?: number | null
  result_json?: string | null
  error_message?: string | null
  started_at?: string | null
  submitted_at?: string | null
  finished_at?: string | null
  created_at: string
  events: AttemptEvent[]
}

type PublishJob = {
  id: string
  plan_id?: string | null
  channel_id?: string | null
  flow_revision_id?: string | null
  platform: string
  status: string
  stage?: string | null
  scheduled_at?: string | null
  content_snapshot_json: string
  channel_snapshot_json: string
  published_url?: string | null
  error_message?: string | null
  created_at: string
  updated_at: string
  attempts: PublishAttempt[]
}

type ChannelSnapshot = {
  profile_id?: number
  target_name?: string
  target_type?: string
  target_url?: string
}

type ContentSnapshot = {
  text?: string
  media?: unknown[]
}

type Filter = 'all' | 'scheduled' | 'queued' | 'running' | 'succeeded' | 'failed' | 'needs_review'

const filters: Array<{ value: Filter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'scheduled', label: '等待' },
  { value: 'queued', label: '队列中' },
  { value: 'running', label: '执行中' },
  { value: 'succeeded', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'needs_review', label: '待人工确认' },
]

const stageLabels: Record<string, string> = {
  scheduled: '等待调度',
  queued: '进入队列',
  opening_browser: '启动浏览器',
  platform_automation: '平台自动化',
  checking_login: '检查登录',
  checking_identity: '校验发布身份',
  navigating: '打开目标主页',
  opening_composer: '打开 Composer',
  writing_text: '输入正文',
  uploading_media: '上传媒体',
  waiting_media: '等待媒体处理',
  advancing: '推进发布流程',
  ready_to_submit: '等待最终发布',
  submitting: '最终发布',
  verifying: '验证发布结果',
  completed: '执行完成',
  failed: '执行失败',
  needs_review: '待人工确认',
  interrupted: '执行中断',
  manual_confirmed_published: '人工确认已发布',
  manual_confirmed_not_published: '人工确认未发布',
}

function parseSnapshot<T>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

function shortText(value?: string, length = 42) {
  const normalized = (value || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return '仅媒体'
  return normalized.length > length ? `${normalized.slice(0, length)}…` : normalized
}

function durationLabel(value?: number | null) {
  if (value == null) return '—'
  if (value < 1000) return `${value} ms`
  if (value < 60_000) return `${(value / 1000).toFixed(1)} s`
  return `${(value / 60_000).toFixed(1)} min`
}

function stageLabel(value?: string | null) {
  if (!value) return '—'
  return stageLabels[value] ?? value
}

function latestAttempt(job: PublishJob) {
  return [...job.attempts].sort((a, b) => a.attempt_no - b.attempt_no).at(-1)
}

function errorSuggestion(stage?: string | null) {
  switch (stage) {
    case 'opening_browser': return '检查 iXBrowser 是否运行、环境是否可打开，然后重新执行。'
    case 'checking_login': return '打开对应 iX 环境，完成 Facebook 登录或安全验证后再执行。'
    case 'checking_identity': return '检查 Channel 配置的目标主页与当前 Facebook 身份是否一致。'
    case 'navigating': return '检查目标主页 URL 是否仍有效，并确认当前账号有访问权限。'
    case 'opening_composer': return 'Facebook 页面结构可能变化，可先人工打开该主页确认发帖入口。'
    case 'writing_text': return '检查 Composer 是否可编辑；如果页面异常，刷新 Facebook 后再执行。'
    case 'uploading_media':
    case 'waiting_media': return '检查媒体文件是否存在、格式是否受支持，以及 Facebook 上传入口是否正常。'
    case 'submitting':
    case 'verifying': return '不要直接重试。先在 Facebook 确认帖子是否已经发布。'
    default: return '查看 Timeline 最后一个成功阶段和错误原因，再决定是否重新执行。'
  }
}

function eventTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).format(new Date(value))
}

function AttemptTimeline({ attempt }: { attempt: PublishAttempt }) {
  const events = [...attempt.events].sort((a, b) => a.sequence - b.sequence)
  return (
    <section className="v1-task-detail-section">
      <div className="v1-task-section-heading">
        <div><strong>Attempt #{attempt.attempt_no}</strong><span className={`task-status task-${attempt.status}`}>{attempt.status}</span></div>
        <small>{formatDateTime(attempt.started_at || attempt.created_at)}</small>
      </div>
      {events.length === 0 ? (
        <div className="v1-task-empty-timeline">该 Attempt 创建于 Phase 6 之前，没有逐阶段 Timeline 事件。</div>
      ) : (
        <div className="v1-task-timeline">
          {events.map((event) => (
            <div className="v1-task-timeline-row" key={event.id}>
              <time>{eventTime(event.created_at)}</time>
              <span className="v1-task-timeline-dot" />
              <div><strong>{stageLabel(event.stage)}</strong><p>{event.message}</p></div>
            </div>
          ))}
        </div>
      )}
      <div className="v1-performance-grid">
        <div><span>总耗时</span><strong>{durationLabel(attempt.total_ms)}</strong></div>
        <div><span>浏览器启动</span><strong>{durationLabel(attempt.browser_open_ms)}</strong></div>
        <div><span>平台自动化</span><strong>{durationLabel(attempt.platform_ms)}</strong></div>
        <div><span>媒体</span><strong>{durationLabel(attempt.media_ms)}</strong></div>
        <div><span>结果验证</span><strong>{durationLabel(attempt.verification_ms)}</strong></div>
      </div>
    </section>
  )
}

export default function TasksPage() {
  const [tasks, setTasks] = useState<PublishJob[]>([])
  const [filter, setFilter] = useState<Filter>('all')
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [busyAction, setBusyAction] = useState<string | null>(null)

  const load = async () => {
    try {
      const result = await api<PublishJob[]>('/api/tasks/publish-jobs?limit=100')
      setTasks(result)
      setError(null)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    }
  }

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 2500)
    return () => window.clearInterval(timer)
  }, [])

  const filtered = useMemo(
    () => filter === 'all' ? tasks : tasks.filter((task) => task.status === filter),
    [filter, tasks],
  )
  const selected = tasks.find((task) => task.id === selectedId) ?? null
  const selectedChannel = selected ? parseSnapshot<ChannelSnapshot>(selected.channel_snapshot_json) : null
  const selectedContent = selected ? parseSnapshot<ContentSnapshot>(selected.content_snapshot_json) : null
  const selectedLatestAttempt = selected ? latestAttempt(selected) : undefined

  const refreshSelected = async (jobId: string) => {
    const next = await api<PublishJob>(`/api/tasks/publish-jobs/${jobId}`)
    setTasks((current) => current.map((item) => item.id === next.id ? next : item))
  }

  const runAgain = async (job: PublishJob) => {
    setBusyAction('run')
    setError(null)
    try {
      await api(`/api/tasks/publish-jobs/${job.id}/run`, { method: 'POST' })
      await load()
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    } finally {
      setBusyAction(null)
    }
  }

  const confirmPublished = async (job: PublishJob) => {
    setBusyAction('published')
    try {
      await api(`/api/tasks/publish-jobs/${job.id}/review/confirm-published`, { method: 'POST' })
      await refreshSelected(job.id)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    } finally {
      setBusyAction(null)
    }
  }

  const confirmNotPublishedAndRetry = async (job: PublishJob) => {
    if (!window.confirm('请确认你已经在 Facebook 检查过：该帖子确实没有发布。确认后系统会立即创建安全重试。')) return
    setBusyAction('retry')
    try {
      await api(`/api/tasks/publish-jobs/${job.id}/review/retry`, { method: 'POST' })
      await refreshSelected(job.id)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    } finally {
      setBusyAction(null)
    }
  }

  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="任务中心"
        title="执行任务与运行历史"
        description="查看 PublishJob → PublishAttempt → Timeline，定位当前阶段、耗时和需要人工处理的异常。"
        actions={<PhaseBadge>Phase 6</PhaseBadge>}
      />

      {error && <div className="notice">{error}</div>}
      <p className="v1-inline-note">`needs_review` 继续作为一级安全状态：系统可能已经执行最终发布点击时，禁止自动重试，必须先人工确认 Facebook。</p>

      <section className="v1-panel">
        <div className="v1-toolbar">
          <div className="filter-row">
            {filters.map((item) => (
              <button key={item.value} type="button" className={`compact-button ${filter === item.value ? 'worker-button' : ''}`} onClick={() => setFilter(item.value)}>{item.label}</button>
            ))}
          </div>
          <span className="v1-muted">{filtered.length} 个正式任务</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>状态</th><th>账号 / Channel</th><th>平台</th><th>素材</th><th>当前步骤</th><th>计划时间</th><th>耗时</th><th>操作</th></tr></thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={8}><div className="empty-state compact-empty"><strong>暂无匹配任务</strong><span>从发布中心创建任务后会显示在这里。</span></div></td></tr>
              ) : filtered.map((task) => {
                const channel = parseSnapshot<ChannelSnapshot>(task.channel_snapshot_json)
                const content = parseSnapshot<ContentSnapshot>(task.content_snapshot_json)
                const attempt = latestAttempt(task)
                const canRun = ['draft', 'scheduled', 'failed'].includes(task.status)
                return (
                  <tr key={task.id} className="v1-task-row" onClick={() => setSelectedId(task.id)}>
                    <td><span className={`task-status task-${task.status}`}>{task.status}</span><br /><small>#{task.id.slice(0, 8)}</small></td>
                    <td><strong>{channel?.target_name || 'Unknown Channel'}</strong><br /><small>iX #{channel?.profile_id ?? '—'}</small></td>
                    <td>{task.platform}</td>
                    <td>{shortText(content?.text)}<br /><small>{Array.isArray(content?.media) ? content?.media?.length : 0} 个媒体</small></td>
                    <td><strong>{stageLabel(task.stage || attempt?.stage)}</strong></td>
                    <td>{formatDateTime(task.scheduled_at || task.created_at)}</td>
                    <td>{durationLabel(attempt?.total_ms)}</td>
                    <td onClick={(event) => event.stopPropagation()}>
                      <div className="v1-plan-actions">
                        <button type="button" className="compact-button" onClick={() => setSelectedId(task.id)}>详情</button>
                        {canRun && <button type="button" className="compact-button" onClick={() => runAgain(task)} disabled={busyAction === 'run'}>{task.status === 'failed' ? '重新执行' : '立即执行'}</button>}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {selected && (
        <div className="v1-task-drawer-backdrop" onMouseDown={() => setSelectedId(null)}>
          <aside className="v1-task-drawer" onMouseDown={(event) => event.stopPropagation()}>
            <header className="v1-task-drawer-header">
              <div><span>任务 #{selected.id.slice(0, 8)}</span><h2>{selectedChannel?.target_name || 'PublishJob 详情'}</h2><p>iX #{selectedChannel?.profile_id ?? '—'} · {selected.platform} · {shortText(selectedContent?.text, 70)}</p></div>
              <button type="button" className="compact-button" onClick={() => setSelectedId(null)}>关闭</button>
            </header>

            <div className="v1-task-drawer-body">
              <div className="v1-task-summary-grid">
                <div><span>状态</span><strong><span className={`task-status task-${selected.status}`}>{selected.status}</span></strong></div>
                <div><span>当前步骤</span><strong>{stageLabel(selected.stage || selectedLatestAttempt?.stage)}</strong></div>
                <div><span>计划时间</span><strong>{formatDateTime(selected.scheduled_at)}</strong></div>
                <div><span>Attempts</span><strong>{selected.attempts.length}</strong></div>
              </div>

              {selected.status === 'needs_review' && (
                <section className="v1-review-panel">
                  <strong>需要人工确认，禁止自动重试</strong>
                  <p>系统可能已经点击最终发布，但无法确认 Facebook 是否成功。直接重试可能造成重复帖子。</p>
                  {selectedLatestAttempt?.error_message && <div className="v1-review-reason">{selectedLatestAttempt.error_message}</div>}
                  <div className="v1-review-actions">
                    {selectedChannel?.target_url && <button type="button" className="compact-button" onClick={() => window.open(selectedChannel.target_url, '_blank', 'noopener,noreferrer')}>打开 Facebook</button>}
                    <button type="button" className="primary" disabled={busyAction !== null} onClick={() => confirmPublished(selected)}>{busyAction === 'published' ? '处理中…' : '确认已发布'}</button>
                    <button type="button" className="compact-button danger-outline" disabled={busyAction !== null} onClick={() => confirmNotPublishedAndRetry(selected)}>{busyAction === 'retry' ? '重新入队…' : '确认未发布并重新执行'}</button>
                  </div>
                </section>
              )}

              {selectedLatestAttempt?.error_message && selected.status !== 'needs_review' && (
                <section className="v1-task-error-panel">
                  <strong>失败阶段：{stageLabel(selectedLatestAttempt.stage)}</strong>
                  <p>原因：{selectedLatestAttempt.error_message}</p>
                  <p>建议：{errorSuggestion(selectedLatestAttempt.stage)}</p>
                </section>
              )}

              {[...selected.attempts].sort((a, b) => b.attempt_no - a.attempt_no).map((attempt) => (
                <AttemptTimeline key={attempt.id} attempt={attempt} />
              ))}

              <details className="v1-technical-details">
                <summary>技术详情</summary>
                <dl>
                  <div><dt>PublishJob ID</dt><dd>{selected.id}</dd></div>
                  <div><dt>Plan ID</dt><dd>{selected.plan_id || '—'}</dd></div>
                  <div><dt>Channel ID</dt><dd>{selected.channel_id || '—'}</dd></div>
                  <div><dt>Flow Revision</dt><dd>{selected.flow_revision_id || '—'}</dd></div>
                  <div><dt>Published URL</dt><dd>{selected.published_url || '—'}</dd></div>
                </dl>
                {selectedLatestAttempt?.result_json && <pre>{selectedLatestAttempt.result_json}</pre>}
              </details>
            </div>
          </aside>
        </div>
      )}
    </main>
  )
}
