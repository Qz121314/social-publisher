import React, { useEffect, useMemo, useState } from 'react'

import { api } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'

type AppStatus = {
  app: string
  ixbrowser: { connected: boolean; total_profiles?: number; message?: string | null }
  browser_sessions?: number
  worker?: { max_workers: number; active_tasks: number }
  scheduler?: {
    running: boolean
    poll_interval_seconds: number
    last_tick_at?: string | null
    dispatched_total: number
    dispatch_errors_total: number
    last_error?: string | null
  }
}

type PublishJob = {
  id: string
  status: string
  scheduled_at?: string | null
  updated_at?: string | null
}

type PublishPlan = {
  id: string
  status: string
  scheduled_at?: string | null
  created_at: string
}

function isToday(value?: string | null) {
  if (!value) return false
  const date = new Date(value)
  const today = new Date()
  return date.getFullYear() === today.getFullYear()
    && date.getMonth() === today.getMonth()
    && date.getDate() === today.getDate()
}

export default function DashboardPage() {
  const [status, setStatus] = useState<AppStatus | null>(null)
  const [jobs, setJobs] = useState<PublishJob[]>([])
  const [plans, setPlans] = useState<PublishPlan[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      const [nextStatus, jobItems, planItems] = await Promise.all([
        api<AppStatus>('/api/status'),
        api<PublishJob[]>('/api/domain/publish-jobs?limit=200'),
        api<PublishPlan[]>('/api/publish-plans?limit=100'),
      ])
      setStatus(nextStatus)
      setJobs(jobItems)
      setPlans(planItems)
      setError(null)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    }
  }

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 5000)
    return () => window.clearInterval(timer)
  }, [])

  const counts = useMemo(() => ({
    plansToday: plans.filter((plan) => isToday(plan.scheduled_at ?? plan.created_at)).length,
    running: jobs.filter((job) => job.status === 'running' || job.status === 'queued').length,
    succeededToday: jobs.filter((job) => job.status === 'succeeded' && isToday(job.updated_at)).length,
    issues: jobs.filter((job) => job.status === 'failed' || job.status === 'needs_review').length,
  }), [jobs, plans])

  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="总览"
        title="系统运行总览"
        description="聚合正式 PublishPlan / PublishJob 状态、异常和执行基础设施健康度。"
        actions={<PhaseBadge>Phase 4</PhaseBadge>}
      />

      {error && <div className="notice">{error}</div>}

      <section className="v1-kpi-grid" aria-label="运行指标">
        <article className="v1-kpi"><span>今日计划</span><strong>{counts.plansToday}</strong><small>SQLite PublishPlan</small></article>
        <article className="v1-kpi"><span>执行中</span><strong>{counts.running}</strong><small>queued + running PublishJob</small></article>
        <article className="v1-kpi"><span>今日成功</span><strong>{counts.succeededToday}</strong><small>正式 PublishJob</small></article>
        <article className="v1-kpi"><span>异常 / 待人工确认</span><strong>{counts.issues}</strong><small>failed + needs_review</small></article>
      </section>

      <div className="v1-grid-2">
        <section className="v1-panel">
          <div className="v1-panel-heading"><div><h2>系统健康状态</h2><p>普通视图只显示业务可理解状态。</p></div></div>
          <div className="v1-health-list">
            <div className="v1-health-row"><div><strong>Backend</strong><br /><small>FastAPI / SQLite</small></div><span className={`v1-health-state ${status?.app === 'ok' ? '' : 'off'}`}>{status?.app === 'ok' ? '正常' : '不可用'}</span></div>
            <div className="v1-health-row"><div><strong>iXBrowser</strong><br /><small>{status?.ixbrowser.total_profiles ?? 0} 个已发现环境</small></div><span className={`v1-health-state ${status?.ixbrowser.connected ? '' : 'off'}`}>{status?.ixbrowser.connected ? '正常' : '未连接'}</span></div>
            <div className="v1-health-row"><div><strong>Worker Pool</strong><br /><small>最大并发 {status?.worker?.max_workers ?? '—'}</small></div><span className={`v1-health-state ${status?.worker ? '' : 'off'}`}>{status?.worker ? `${status.worker.active_tasks} 运行中` : '未知'}</span></div>
            <div className="v1-health-row"><div><strong>Scheduler</strong><br /><small>{status?.scheduler ? `${status.scheduler.poll_interval_seconds}s 轮询 · 已派发 ${status.scheduler.dispatched_total}` : 'SQLite-backed scheduler'}</small></div><span className={`v1-health-state ${status?.scheduler?.running ? '' : 'off'}`}>{status?.scheduler?.running ? '正常' : '未运行'}</span></div>
            <div className="v1-health-row"><div><strong>Facebook Flow</strong><br /><small>Snapshot-bound Flow Revision</small></div><span className="v1-health-state">已接入</span></div>
          </div>
        </section>

        <section className="v1-panel">
          <div className="v1-panel-heading"><div><h2>V1 进度</h2><p>严格按 README 的阶段顺序推进。</p></div></div>
          <div className="v1-flow-list">
            <div className="v1-flow-row"><strong>01</strong><div><strong>后台信息架构</strong><br /><small>8 个中心 + 真实路由</small></div><span className="v1-health-state">完成</span></div>
            <div className="v1-flow-row"><strong>02</strong><div><strong>领域模型</strong><br /><small>Channel / PublishPlan / Attempt / Flow Revision</small></div><span className="v1-health-state">完成</span></div>
            <div className="v1-flow-row"><strong>03</strong><div><strong>迁移 Facebook PoC</strong><br /><small>正式模型连接 Facebook Worker</small></div><span className="v1-health-state">完成</span></div>
            <div className="v1-flow-row"><strong>04</strong><div><strong>Scheduler</strong><br /><small>立即 / 定时统一 SQLite 流水线</small></div><span className="v1-health-state">当前</span></div>
          </div>
          {status?.scheduler?.last_error && <div className="v1-scheduler-error">Scheduler 最近错误：{status.scheduler.last_error}</div>}
        </section>
      </div>
    </main>
  )
}
