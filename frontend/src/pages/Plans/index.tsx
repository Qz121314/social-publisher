import React, { useEffect, useMemo, useState } from 'react'

import { api, formatDateTime } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'

type PublishJob = {
  id: string
  status: string
  stage?: string | null
  scheduled_at?: string | null
  error_message?: string | null
}

type PublishPlan = {
  id: string
  publish_mode: string
  status: string
  timezone: string
  scheduled_at?: string | null
  interval_seconds: number
  content_snapshot_json: string
  created_at: string
  jobs: PublishJob[]
}

const filters = ['all', 'scheduled', 'queued', 'running', 'succeeded', 'failed', 'needs_review', 'cancelled'] as const

function assetLabel(plan: PublishPlan) {
  try {
    const snapshot = JSON.parse(plan.content_snapshot_json) as { text?: string }
    const text = (snapshot.text ?? '').replace(/\s+/g, ' ').trim()
    if (!text) return '仅媒体素材'
    return text.length > 52 ? `${text.slice(0, 52)}…` : text
  } catch {
    return `Asset ${plan.id.slice(0, 8)}`
  }
}

function jobSummary(plan: PublishPlan) {
  const counts = new Map<string, number>()
  plan.jobs.forEach((job) => counts.set(job.status, (counts.get(job.status) ?? 0) + 1))
  return Array.from(counts.entries()).map(([status, count]) => `${status} ${count}`).join(' · ')
}

export default function PlansPage() {
  const [plans, setPlans] = useState<PublishPlan[]>([])
  const [filter, setFilter] = useState<(typeof filters)[number]>('all')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const load = async () => {
    try {
      setPlans(await api<PublishPlan[]>('/api/publish-plans?limit=100'))
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    }
  }

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 3000)
    return () => window.clearInterval(timer)
  }, [])

  const filtered = useMemo(
    () => filter === 'all' ? plans : plans.filter((plan) => plan.status === filter),
    [filter, plans],
  )

  const runNow = async (planId: string) => {
    setBusyId(planId)
    setMessage(null)
    try {
      await api<PublishPlan>(`/api/publish-plans/${planId}/run`, { method: 'POST' })
      setMessage(`计划 ${planId.slice(0, 8)} 已改为立即执行，Scheduler 将按 Worker 空闲槽位接管。`)
      await load()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyId(null)
    }
  }

  const cancel = async (planId: string) => {
    setBusyId(planId)
    setMessage(null)
    try {
      await api<PublishPlan>(`/api/publish-plans/${planId}/cancel`, { method: 'POST' })
      setMessage(`计划 ${planId.slice(0, 8)} 已取消。`)
      await load()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="计划中心"
        title="发布计划"
        description="SQLite 是计划真相来源；Scheduler 只负责发现到期 Job 并安全派发。"
        actions={<PhaseBadge>Phase 4</PhaseBadge>}
      />

      {message && <div className="notice">{message}</div>}
      <p className="v1-inline-note">Backend 重启不会丢失 future schedule。queued Job 会在启动恢复时退回 scheduled，running Job 则保守进入 needs_review，避免重复发布。</p>

      <section className="v1-panel">
        <div className="v1-toolbar">
          <div className="filter-row">
            {filters.map((item) => (
              <button key={item} className={`compact-button ${filter === item ? 'worker-button' : ''}`} onClick={() => setFilter(item)}>{item}</button>
            ))}
          </div>
          <span className="v1-muted">{filtered.length} 个计划</span>
        </div>

        <div className="table-wrap">
          <table>
            <thead><tr><th>计划 / 素材</th><th>方式</th><th>计划时间</th><th>Jobs</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={6}><div className="empty-state compact-empty"><strong>暂无匹配计划</strong><span>在发布中心创建立即发布或定时发布后会显示在这里。</span></div></td></tr>
              ) : filtered.map((plan) => {
                const canRun = plan.jobs.some((job) => ['draft', 'scheduled', 'failed'].includes(job.status))
                const canCancel = plan.jobs.length > 0 && plan.jobs.every((job) => ['draft', 'scheduled', 'failed'].includes(job.status))
                return (
                  <tr key={plan.id}>
                    <td><strong>{assetLabel(plan)}</strong><br /><small>#{plan.id.slice(0, 8)}</small></td>
                    <td>{plan.publish_mode === 'scheduled' ? '定时发布' : plan.publish_mode === 'immediate' ? '立即发布' : '草稿'}</td>
                    <td>{formatDateTime(plan.scheduled_at)}<br /><small>{plan.timezone}</small></td>
                    <td><strong>{plan.jobs.length}</strong><br /><small>{jobSummary(plan) || '—'}</small></td>
                    <td><span className={`task-status task-${plan.status}`}>{plan.status}</span></td>
                    <td>
                      <div className="v1-plan-actions">
                        {canRun && <button className="compact-button" disabled={busyId === plan.id} onClick={() => runNow(plan.id)}>立即执行</button>}
                        {canCancel && <button className="compact-button" disabled={busyId === plan.id} onClick={() => cancel(plan.id)}>取消</button>}
                        {!canRun && !canCancel && <span className="v1-muted">—</span>}
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
