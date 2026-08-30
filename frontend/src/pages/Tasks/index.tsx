import React, { useEffect, useMemo, useState } from 'react'

import { api, formatDateTime } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'

type PublishAttempt = {
  id: string
  attempt_no: number
  status: string
  stage?: string | null
  total_ms?: number | null
  error_message?: string | null
  started_at?: string | null
  finished_at?: string | null
}

type PublishJob = {
  id: string
  plan_id?: string | null
  channel_id?: string | null
  platform: string
  status: string
  stage?: string | null
  scheduled_at?: string | null
  content_snapshot_json: string
  channel_snapshot_json: string
  error_message?: string | null
  created_at: string
  attempts: PublishAttempt[]
}

type ChannelSnapshot = {
  profile_id?: number
  target_name?: string
  target_type?: string
}

type ContentSnapshot = {
  text?: string
  media?: unknown[]
}

const filters = ['all', 'scheduled', 'queued', 'running', 'succeeded', 'failed', 'needs_review'] as const

function parseSnapshot<T>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

function shortText(value?: string) {
  const normalized = (value || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return '仅媒体'
  return normalized.length > 42 ? `${normalized.slice(0, 42)}…` : normalized
}

function durationLabel(value?: number | null) {
  if (value == null) return '—'
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(1)} s`
}

export default function TasksPage() {
  const [tasks, setTasks] = useState<PublishJob[]>([])
  const [filter, setFilter] = useState<(typeof filters)[number]>('all')
  const [error, setError] = useState<string | null>(null)
  const [runningId, setRunningId] = useState<string | null>(null)

  const load = async () => {
    try {
      const result = await api<PublishJob[]>('/api/domain/publish-jobs?limit=100')
      setTasks(result)
      setError(null)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    }
  }

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 3000)
    return () => window.clearInterval(timer)
  }, [])

  const filtered = useMemo(() => filter === 'all' ? tasks : tasks.filter((task) => task.status === filter), [filter, tasks])

  const runAgain = async (job: PublishJob) => {
    setRunningId(job.id)
    setError(null)
    try {
      await api(`/api/publish-jobs/${job.id}/run`, { method: 'POST' })
      await load()
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    } finally {
      setRunningId(null)
    }
  }

  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="任务中心"
        title="PublishJob 执行任务"
        description="正式展示 PublishJob → PublishAttempt；WorkerTask 已降为内部 Runtime 对象。"
        actions={<PhaseBadge>Phase 3</PhaseBadge>}
      />

      {error && <div className="notice">{error}</div>}
      <p className="v1-inline-note">当前 Stage 为 Worker 的粗粒度执行阶段；逐步骤 Timeline、性能拆分和 needs_review 人工确认体验在 Phase 6 完成。</p>

      <section className="v1-panel">
        <div className="v1-toolbar">
          <div className="filter-row">
            {filters.map((item) => <button key={item} type="button" className={`compact-button ${filter === item ? 'worker-button' : ''}`} onClick={() => setFilter(item)}>{item}</button>)}
          </div>
          <span className="v1-muted">{filtered.length} 个正式任务</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>状态</th><th>Channel</th><th>素材</th><th>当前阶段</th><th>计划时间</th><th>Attempt</th><th>结果 / 操作</th></tr></thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={7}><div className="empty-state compact-empty"><strong>暂无正式 PublishJob</strong><span>从发布中心创建一次立即发布后会显示在这里。</span></div></td></tr>
              ) : filtered.map((task) => {
                const channel = parseSnapshot<ChannelSnapshot>(task.channel_snapshot_json)
                const content = parseSnapshot<ContentSnapshot>(task.content_snapshot_json)
                const attempt = task.attempts[task.attempts.length - 1]
                const canRun = ['draft', 'scheduled', 'failed'].includes(task.status)
                return (
                  <tr key={task.id}>
                    <td><span className={`task-status task-${task.status}`}>{task.status}</span><br /><small>#{task.id.slice(0, 8)}</small></td>
                    <td><strong>{channel?.target_name || 'Unknown Channel'}</strong><br /><small>iX #{channel?.profile_id ?? '—'} · {task.platform}</small></td>
                    <td>{shortText(content?.text)}<br /><small>{Array.isArray(content?.media) ? content?.media?.length : 0} 个媒体</small></td>
                    <td><strong>{task.stage || attempt?.stage || '—'}</strong></td>
                    <td>{formatDateTime(task.scheduled_at || task.created_at)}</td>
                    <td>{attempt ? `#${attempt.attempt_no} · ${durationLabel(attempt.total_ms)}` : '尚未执行'}<br /><small>{attempt ? formatDateTime(attempt.started_at) : '—'}</small></td>
                    <td>
                      <div className="v1-task-result">
                        <span>{task.error_message || attempt?.error_message || (task.status === 'succeeded' ? '发布成功' : '—')}</span>
                        {canRun && <button type="button" className="compact-button" onClick={() => runAgain(task)} disabled={runningId === task.id}>{runningId === task.id ? '入队中…' : task.status === 'failed' ? '重新执行' : '立即执行'}</button>}
                        {task.status === 'needs_review' && <small className="v1-warning-text">禁止自动重试，请先人工确认 Facebook 是否已经发布。</small>}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  )
}
