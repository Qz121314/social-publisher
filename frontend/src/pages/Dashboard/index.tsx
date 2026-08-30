import React, { useEffect, useMemo, useState } from 'react'

import { api } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'

type AppStatus = {
  app: string
  ixbrowser: { connected: boolean; total_profiles?: number; message?: string | null }
  browser_sessions?: number
  worker?: { max_workers: number; active_tasks: number }
}

type WorkerTask = {
  id: string
  status: string
  finished_at?: string | null
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
  const [tasks, setTasks] = useState<WorkerTask[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      const [nextStatus, taskResult] = await Promise.all([
        api<AppStatus>('/api/status'),
        api<{ items: WorkerTask[] }>('/api/worker/tasks?limit=100'),
      ])
      setStatus(nextStatus)
      setTasks(taskResult.items)
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
    running: tasks.filter((task) => task.status === 'running' || task.status === 'queued').length,
    succeededToday: tasks.filter((task) => task.status === 'succeeded' && isToday(task.finished_at)).length,
    issues: tasks.filter((task) => task.status === 'failed' || task.status === 'needs_review').length,
  }), [tasks])

  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="总览"
        title="系统运行总览"
        description="聚合当前执行状态、待处理异常和核心运行健康度。"
        actions={<PhaseBadge />}
      />

      {error && <div className="notice">{error}</div>}

      <section className="v1-kpi-grid" aria-label="运行指标">
        <article className="v1-kpi"><span>今日计划</span><strong>—</strong><small>PublishPlan / Scheduler 将在后续阶段接入</small></article>
        <article className="v1-kpi"><span>执行中</span><strong>{counts.running}</strong><small>当前队列与运行任务</small></article>
        <article className="v1-kpi"><span>今日成功</span><strong>{counts.succeededToday}</strong><small>现有 Runtime Task 统计</small></article>
        <article className="v1-kpi"><span>异常 / 待人工确认</span><strong>{counts.issues}</strong><small>failed + needs_review</small></article>
      </section>

      <div className="v1-grid-2">
        <section className="v1-panel">
          <div className="v1-panel-heading"><div><h2>系统健康状态</h2><p>普通视图只显示业务可理解状态。</p></div></div>
          <div className="v1-health-list">
            <div className="v1-health-row"><div><strong>Backend</strong><br /><small>FastAPI / SQLite</small></div><span className={`v1-health-state ${status?.app === 'ok' ? '' : 'off'}`}>{status?.app === 'ok' ? '正常' : '不可用'}</span></div>
            <div className="v1-health-row"><div><strong>iXBrowser</strong><br /><small>{status?.ixbrowser.total_profiles ?? 0} 个已发现环境</small></div><span className={`v1-health-state ${status?.ixbrowser.connected ? '' : 'off'}`}>{status?.ixbrowser.connected ? '正常' : '未连接'}</span></div>
            <div className="v1-health-row"><div><strong>Worker Pool</strong><br /><small>最大并发 {status?.worker?.max_workers ?? '—'}</small></div><span className={`v1-health-state ${status?.worker ? '' : 'off'}`}>{status?.worker ? `${status.worker.active_tasks} 运行中` : '未知'}</span></div>
            <div className="v1-health-row"><div><strong>Scheduler</strong><br /><small>SQLite-backed scheduler</small></div><span className="v1-health-state off">Phase 4</span></div>
            <div className="v1-health-row"><div><strong>Facebook Flow</strong><br /><small>当前 PoC 发布链路</small></div><span className="v1-health-state">已验证</span></div>
          </div>
        </section>

        <section className="v1-panel">
          <div className="v1-panel-heading"><div><h2>当前阶段</h2><p>严格按 README 的 V1 开发顺序推进。</p></div></div>
          <div className="v1-flow-list">
            <div className="v1-flow-row"><strong>01</strong><div><strong>后台信息架构</strong><br /><small>8 个中心 + 真实路由</small></div><span className="v1-health-state">进行中</span></div>
            <div className="v1-flow-row"><strong>02</strong><div><strong>领域模型</strong><br /><small>Channel / PublishPlan / Attempt / Flow Revision</small></div><span className="v1-muted">下一阶段</span></div>
            <div className="v1-flow-row"><strong>03</strong><div><strong>迁移 Facebook PoC</strong><br /><small>按中心拆分现有能力</small></div><span className="v1-muted">待开始</span></div>
            <div className="v1-flow-row"><strong>04</strong><div><strong>Scheduler</strong><br /><small>立即 / 定时统一流水线</small></div><span className="v1-muted">待开始</span></div>
          </div>
        </section>
      </div>
    </main>
  )
}
