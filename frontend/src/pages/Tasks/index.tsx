import React, { useEffect, useMemo, useState } from 'react'

import { api, formatDateTime } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'

type WorkerTask = {
  id: string
  task_type: string
  profile_id: number
  status: string
  attempts: number
  error_message?: string | null
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
}

const filters = ['all', 'queued', 'running', 'succeeded', 'failed', 'needs_review'] as const

export default function TasksPage() {
  const [tasks, setTasks] = useState<WorkerTask[]>([])
  const [filter, setFilter] = useState<(typeof filters)[number]>('all')
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      const result = await api<{ items: WorkerTask[] }>('/api/worker/tasks?limit=100')
      setTasks(result.items)
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

  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="任务中心"
        title="执行任务"
        description="统一查看实际执行状态和运行历史；needs_review 继续作为一级安全状态。"
        actions={<PhaseBadge />}
      />

      {error && <div className="notice">{error}</div>}
      <p className="v1-inline-note">Phase 1 暂时读取现有 WorkerTask。Phase 2 会建立 PublishJob → PublishAttempt，Phase 3 再把 Stage / Timeline 映射到正式任务中心。</p>

      <section className="v1-panel">
        <div className="v1-toolbar">
          <div className="filter-row">
            {filters.map((item) => <button key={item} className={`compact-button ${filter === item ? 'worker-button' : ''}`} onClick={() => setFilter(item)}>{item}</button>)}
          </div>
          <span className="v1-muted">{filtered.length} 个任务</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>任务</th><th>环境</th><th>类型</th><th>状态</th><th>尝试</th><th>开始</th><th>结束 / 错误</th></tr></thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={7}><div className="empty-state compact-empty"><strong>暂无匹配任务</strong><span>运行发布或浏览器测试后会显示在这里。</span></div></td></tr>
              ) : filtered.map((task) => (
                <tr key={task.id}>
                  <td><strong>{task.id.slice(0, 8)}</strong></td>
                  <td>#{task.profile_id}</td>
                  <td>{task.task_type}</td>
                  <td><span className={`task-status task-${task.status}`}>{task.status}</span></td>
                  <td>{task.attempts}</td>
                  <td>{formatDateTime(task.started_at ?? task.created_at)}</td>
                  <td>{task.error_message || formatDateTime(task.finished_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  )
}
