import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, formatDateTime } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'
import './run-center.css'

type TaskJob = {
  id: string
  batch_id: string
  account_id?: number | null
  job_type: string
  status: string
  stage: string
  account_snapshot_json: string
  profile_id?: number | null
  result_json?: string | null
  error_message?: string | null
  attempts: number
  created_at: string
  started_at?: string | null
  finished_at?: string | null
}

type BatchTask = {
  id: string
  task_type: string
  source_type: string
  source_selection_json: string
  target_snapshot_json: string
  status: string
  total_jobs: number
  succeeded_jobs: number
  attention_jobs: number
  failed_jobs: number
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  jobs: TaskJob[]
}

type AccountSnapshot = {
  account_id?: number
  name?: string
  platform?: string
  group_id?: number | null
  proxy_id?: number | null
  ix_profile_id?: number | null
}

type GroupSource = { group_id?: number; group_name?: string }
type SelectionSource = { account_ids?: number[] }
type Filter = 'all' | 'active' | 'attention' | 'succeeded' | 'failed'

const filters: Array<{ value: Filter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'active', label: '执行中' },
  { value: 'attention', label: '需要处理' },
  { value: 'succeeded', label: '已完成' },
  { value: 'failed', label: '失败' },
]

const terminalJobStatuses = new Set(['succeeded', 'needs_attention', 'needs_review', 'waiting_user', 'blocked', 'failed'])
const attentionJobStatuses = new Set(['needs_attention', 'needs_review', 'waiting_user', 'blocked'])

function parseJson<T>(raw: string): T | null {
  try { return JSON.parse(raw) as T } catch { return null }
}

function statusMeta(status: string) {
  switch (status) {
    case 'queued': return { label: '等待执行', tone: 'neutral' }
    case 'running': return { label: '执行中', tone: 'info' }
    case 'succeeded': return { label: '已完成', tone: 'success' }
    case 'needs_attention': return { label: '需要处理', tone: 'warning' }
    case 'partial': return { label: '部分完成', tone: 'warning' }
    case 'failed': return { label: '失败', tone: 'danger' }
    default: return { label: status, tone: 'neutral' }
  }
}

function jobStatusLabel(status: string) {
  if (status === 'queued') return '等待执行'
  if (status === 'running') return '执行中'
  if (status === 'succeeded') return '已完成'
  if (attentionJobStatuses.has(status)) return '需要处理'
  if (status === 'failed') return '失败'
  return status
}

function stageLabel(stage: string) {
  const labels: Record<string, string> = {
    queued: '等待执行',
    preparing_runtime: '准备 iX 环境',
    recovering_login: '恢复登录',
    completed: '登录状态正常',
    preflight: '准备条件不足',
    needs_attention: '需要人工处理',
    blocked: '环境暂时被占用',
    unsupported: '需要人工处理',
    interrupted: '执行被中断',
    failed: '执行失败',
  }
  return labels[stage] ?? stage
}

function platformLabel(platform?: string) {
  if (platform === 'facebook') return 'Facebook'
  if (platform === 'instagram') return 'Instagram'
  return platform || '—'
}

function sourceLabel(task: BatchTask) {
  if (task.source_type === 'group') {
    const source = parseJson<GroupSource>(task.source_selection_json)
    return source?.group_name ? `分组 · ${source.group_name}` : `账号分组 #${source?.group_id ?? '—'}`
  }
  const source = parseJson<SelectionSource>(task.source_selection_json)
  return `手动选择 · ${source?.account_ids?.length ?? task.total_jobs} 个账号`
}

function progress(task: BatchTask) {
  const done = Math.min(task.total_jobs, task.succeeded_jobs + task.attention_jobs + task.failed_jobs)
  return {
    done,
    percent: task.total_jobs > 0 ? Math.round((done / task.total_jobs) * 100) : 0,
  }
}

function taskMatches(task: BatchTask, filter: Filter) {
  if (filter === 'all') return true
  if (filter === 'active') return task.status === 'queued' || task.status === 'running'
  if (filter === 'attention') return task.attention_jobs > 0 || task.status === 'needs_attention' || task.status === 'partial'
  if (filter === 'succeeded') return task.status === 'succeeded'
  if (filter === 'failed') return task.status === 'failed' || task.failed_jobs > 0
  return true
}

function jobAccount(job: TaskJob) {
  return parseJson<AccountSnapshot>(job.account_snapshot_json) ?? {}
}

function taskRunningJobs(task: BatchTask) {
  return task.jobs.filter((job) => job.status === 'running').length
}

function taskQueuedJobs(task: BatchTask) {
  return task.jobs.filter((job) => job.status === 'queued').length
}

function taskDuration(task: BatchTask) {
  if (!task.started_at) return '—'
  const start = new Date(task.started_at).getTime()
  const end = task.finished_at ? new Date(task.finished_at).getTime() : Date.now()
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return '—'
  const seconds = Math.round((end - start) / 1000)
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  if (minutes < 60) return `${minutes} 分 ${rest} 秒`
  return `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`
}

export default function RunCenterPage() {
  const [tasks, setTasks] = useState<BatchTask[]>([])
  const [filter, setFilter] = useState<Filter>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null)

  const load = async () => {
    try {
      const next = await api<BatchTask[]>('/api/batch-tasks?limit=100')
      setTasks(next.filter((item) => item.task_type === 'login_recover'))
      setError(null)
      setLastUpdatedAt(new Date())
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    }
  }

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 1500)
    return () => window.clearInterval(timer)
  }, [])

  const filtered = useMemo(() => tasks.filter((task) => taskMatches(task, filter)), [tasks, filter])
  const selected = tasks.find((task) => task.id === selectedId) ?? null
  const activeTasks = tasks.filter((task) => ['queued', 'running'].includes(task.status)).length
  const attentionJobs = tasks.reduce((sum, task) => sum + task.attention_jobs, 0)
  const failedJobs = tasks.reduce((sum, task) => sum + task.failed_jobs, 0)
  const completedJobs = tasks.reduce((sum, task) => sum + task.succeeded_jobs, 0)

  const selectedJobs = useMemo(() => {
    if (!selected) return []
    const priority = (job: TaskJob) => {
      if (attentionJobStatuses.has(job.status)) return 0
      if (job.status === 'failed') return 1
      if (job.status === 'running') return 2
      if (job.status === 'queued') return 3
      return 4
    }
    return [...selected.jobs].sort((a, b) => priority(a) - priority(b) || (a.account_id ?? 0) - (b.account_id ?? 0))
  }, [selected])

  return (
    <main className="v1-page run-center-page">
      <PageHeader
        eyebrow="运行中心"
        title="账号任务与运行进度"
        description="统一查看批量登录、Runtime 创建、登录恢复和异常结果。任务创建后目标快照固定，账号池后续变化不会改写正在执行的任务。"
        actions={<PhaseBadge>Phase 10</PhaseBadge>}
      />

      <div className="run-center-tabs" role="navigation" aria-label="运行中心任务类型">
        <span className="run-center-tab is-active">账号任务</span>
        <Link className="run-center-tab" to="/tasks/publish">发布任务</Link>
      </div>

      {error && <div className="notice">{error}</div>}

      <section className="run-center-summary" aria-label="账号任务摘要">
        <div><span>活跃批次</span><strong>{activeTasks}</strong><small>排队或执行中</small></div>
        <div><span>已完成账号</span><strong>{completedJobs}</strong><small>登录状态已恢复</small></div>
        <div><span>需要处理</span><strong>{attentionJobs}</strong><small>2FA / Checkpoint / 前置条件</small></div>
        <div><span>失败账号</span><strong>{failedJobs}</strong><small>执行错误</small></div>
      </section>

      <section className="v1-panel run-center-panel">
        <div className="v1-toolbar run-center-toolbar">
          <div className="filter-row">
            {filters.map((item) => (
              <button key={item.value} type="button" className={`compact-button ${filter === item.value ? 'worker-button' : ''}`} onClick={() => setFilter(item.value)}>{item.label}</button>
            ))}
          </div>
          <div className="run-center-refresh"><span>{filtered.length} 个批次</span><button type="button" className="compact-button" onClick={load}>刷新</button></div>
        </div>

        {tasks.length === 0 ? (
          <div className="empty-state run-center-empty"><strong>还没有账号运行任务</strong><span>在准备 → 账号池选择分组或账号并点击“批量登录”，任务会自动进入这里。</span></div>
        ) : filtered.length === 0 ? (
          <div className="empty-state run-center-empty"><strong>当前筛选没有任务</strong><span>切换筛选条件查看其他批次。</span></div>
        ) : (
          <div className="run-batch-list">
            {filtered.map((task) => {
              const meta = statusMeta(task.status)
              const value = progress(task)
              const running = taskRunningJobs(task)
              const queued = taskQueuedJobs(task)
              return (
                <article key={task.id} className="run-batch-card" onClick={() => setSelectedId(task.id)}>
                  <header>
                    <div><span className={`run-status run-status--${meta.tone}`}>{meta.label}</span><strong>{sourceLabel(task)}</strong><small>任务 #{task.id.slice(0, 8)} · {formatDateTime(task.created_at)}</small></div>
                    <button type="button" className="compact-button" onClick={(event) => { event.stopPropagation(); setSelectedId(task.id) }}>详情</button>
                  </header>
                  <div className="run-progress-row"><div className="run-progress-track"><span style={{ width: `${value.percent}%` }} /></div><strong>{value.done} / {task.total_jobs}</strong><span>{value.percent}%</span></div>
                  <div className="run-batch-metrics">
                    <div><span>执行中</span><strong>{running}</strong></div>
                    <div><span>排队</span><strong>{queued}</strong></div>
                    <div><span>成功</span><strong>{task.succeeded_jobs}</strong></div>
                    <div><span>需要处理</span><strong>{task.attention_jobs}</strong></div>
                    <div><span>失败</span><strong>{task.failed_jobs}</strong></div>
                    <div><span>耗时</span><strong>{taskDuration(task)}</strong></div>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </section>

      <div className="run-center-footnote">{lastUpdatedAt ? `最近刷新：${lastUpdatedAt.toLocaleTimeString('zh-CN')}` : '正在读取运行状态…'} · 执行中的任务每 1.5 秒自动刷新。</div>

      {selected && (
        <div className="v1-task-drawer-backdrop" onMouseDown={() => setSelectedId(null)}>
          <aside className="v1-task-drawer run-batch-drawer" onMouseDown={(event) => event.stopPropagation()}>
            <header className="v1-task-drawer-header">
              <div><span>批量登录 #{selected.id.slice(0, 8)}</span><h2>{sourceLabel(selected)}</h2><p>{selected.total_jobs} 个账号 · 创建于 {formatDateTime(selected.created_at)}</p></div>
              <button type="button" className="compact-button" onClick={() => setSelectedId(null)}>关闭</button>
            </header>
            <div className="v1-task-drawer-body">
              <div className="v1-task-summary-grid run-batch-summary-grid">
                <div><span>状态</span><strong>{statusMeta(selected.status).label}</strong></div>
                <div><span>完成进度</span><strong>{progress(selected).done} / {selected.total_jobs}</strong></div>
                <div><span>开始时间</span><strong>{formatDateTime(selected.started_at)}</strong></div>
                <div><span>总耗时</span><strong>{taskDuration(selected)}</strong></div>
              </div>

              {selected.attention_jobs > 0 && (
                <section className="run-attention-callout"><strong>{selected.attention_jobs} 个账号需要人工处理</strong><p>当前先在这里保留错误与阶段信息。下一阶段会把 2FA / Checkpoint 正式汇入“检查中心”，不会在运行中心自动绕过安全验证。</p></section>
              )}

              <section className="run-job-section">
                <div className="v1-task-section-heading"><div><strong>账号执行明细</strong><span>{selected.jobs.length} 个 Job</span></div></div>
                <div className="run-job-list">
                  {selectedJobs.map((job) => {
                    const account = jobAccount(job)
                    const terminal = terminalJobStatuses.has(job.status)
                    return (
                      <div key={job.id} className={`run-job-row ${attentionJobStatuses.has(job.status) || job.status === 'failed' ? 'has-issue' : ''}`}>
                        <div className="run-job-account"><strong>{account.name || `账号 #${job.account_id ?? '—'}`}</strong><span>{platformLabel(account.platform)} · 账号 #{job.account_id ?? '—'} · iX #{job.profile_id ?? account.ix_profile_id ?? '待创建'}</span></div>
                        <div className="run-job-stage"><strong>{stageLabel(job.stage)}</strong><span>{jobStatusLabel(job.status)}{job.attempts > 0 ? ` · Attempt ${job.attempts}` : ''}</span></div>
                        <div className="run-job-time"><span>{terminal ? formatDateTime(job.finished_at) : formatDateTime(job.started_at || job.created_at)}</span></div>
                        <div className="run-job-message">{job.error_message || (job.status === 'queued' ? '等待执行槽位' : job.status === 'running' ? '正在执行' : '执行完成')}</div>
                      </div>
                    )
                  })}
                </div>
              </section>

              <details className="v1-technical-details">
                <summary>技术详情</summary>
                <dl>
                  <div><dt>BatchTask ID</dt><dd>{selected.id}</dd></div>
                  <div><dt>Task Type</dt><dd>{selected.task_type}</dd></div>
                  <div><dt>Source Type</dt><dd>{selected.source_type}</dd></div>
                  <div><dt>Started</dt><dd>{formatDateTime(selected.started_at)}</dd></div>
                  <div><dt>Finished</dt><dd>{formatDateTime(selected.finished_at)}</dd></div>
                </dl>
              </details>
            </div>
          </aside>
        </div>
      )}
    </main>
  )
}
