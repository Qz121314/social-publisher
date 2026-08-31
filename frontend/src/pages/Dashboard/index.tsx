import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../../app/api'
import { Button, EmptyState, Panel, ProgressBar, StatusChip, WorkspaceHeader } from '../../ui/components'
import { AccountIcon, AlertIcon, AssetIcon, BrowserIcon, CheckIcon, FlowIcon, NetworkIcon, PlusIcon } from '../../ui/icons'
import './workbench.css'

type AppStatus = {
  app: string
  ixbrowser: { connected: boolean; total_profiles?: number; message?: string | null }
  browser_pool?: { total_sessions: number; warm_sessions: number; warm_session_ttl_seconds: number }
  worker?: { max_workers: number; active_tasks: number }
  scheduler?: { running: boolean; last_tick_at?: string | null; last_error?: string | null }
}

type PublishAttempt = {
  id: string
  status: string
  stage?: string | null
  total_ms?: number | null
}

type PublishJob = {
  id: string
  status: string
  stage?: string | null
  platform: string
  scheduled_at?: string | null
  updated_at?: string | null
  created_at: string
  channel_snapshot_json?: string | null
  content_snapshot_json?: string | null
  error_message?: string | null
  attempts?: PublishAttempt[]
}

type PublishPlan = {
  id: string
  status: string
  publish_mode?: string
  scheduled_at?: string | null
  created_at: string
  jobs?: Array<{ id: string; status: string; scheduled_at?: string | null }>
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

const stageLabels: Record<string, string> = {
  scheduled: '等待调度',
  queued: '等待执行',
  opening_browser: '启动浏览器',
  checking_login: '检查登录',
  checking_identity: '检查发布身份',
  navigating: '打开平台页面',
  opening_composer: '打开发布界面',
  writing_text: '写入正文',
  uploading_media: '上传媒体',
  waiting_media: '等待媒体处理',
  advancing: '推进发布流程',
  ready_to_submit: '准备发布',
  submitting: '提交发布',
  verifying: '验证发布结果',
  completed: '执行完成',
  failed: '执行失败',
  needs_review: '等待人工确认',
}

const stageProgress: Record<string, number> = {
  scheduled: 4,
  queued: 8,
  opening_browser: 16,
  checking_login: 25,
  checking_identity: 34,
  navigating: 43,
  opening_composer: 52,
  writing_text: 62,
  uploading_media: 72,
  waiting_media: 78,
  advancing: 84,
  ready_to_submit: 90,
  submitting: 94,
  verifying: 97,
  completed: 100,
}

function parseSnapshot<T>(raw?: string | null): T | null {
  if (!raw) return null
  try { return JSON.parse(raw) as T } catch { return null }
}

function isToday(value?: string | null) {
  if (!value) return false
  const date = new Date(value)
  const today = new Date()
  return date.getFullYear() === today.getFullYear()
    && date.getMonth() === today.getMonth()
    && date.getDate() === today.getDate()
}

function formatTime(value?: string | null) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function platformName(value: string) {
  if (value === 'facebook') return 'Facebook'
  if (value === 'instagram') return 'Instagram'
  return value || 'Platform'
}

function currentStage(job: PublishJob) {
  const attempt = [...(job.attempts ?? [])].at(-1)
  return job.stage || attempt?.stage || job.status
}

function targetName(job: PublishJob) {
  const channel = parseSnapshot<ChannelSnapshot>(job.channel_snapshot_json)
  return channel?.target_name || `${platformName(job.platform)} Channel`
}

function jobDescription(job: PublishJob) {
  const content = parseSnapshot<ContentSnapshot>(job.content_snapshot_json)
  const text = (content?.text || '').replace(/\s+/g, ' ').trim()
  const mediaCount = Array.isArray(content?.media) ? content.media.length : 0
  if (text) return `${text.slice(0, 54)}${text.length > 54 ? '…' : ''}${mediaCount ? ` · ${mediaCount} 个媒体` : ''}`
  return mediaCount ? `${mediaCount} 个媒体` : stageLabels[currentStage(job)] || '发布任务'
}

function statusTone(status: string) {
  if (status === 'needs_review') return 'warning' as const
  if (status === 'failed') return 'danger' as const
  if (status === 'running') return 'info' as const
  if (status === 'succeeded') return 'success' as const
  return 'neutral' as const
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
        api<PublishJob[]>('/api/tasks/publish-jobs?limit=100'),
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

  const attention = useMemo(
    () => jobs.filter((job) => job.status === 'needs_review' || job.status === 'failed').slice(0, 4),
    [jobs],
  )

  const running = useMemo(
    () => jobs.filter((job) => job.status === 'running' || job.status === 'queued').slice(0, 4),
    [jobs],
  )

  const upcoming = useMemo(
    () => plans
      .filter((plan) => plan.scheduled_at && new Date(plan.scheduled_at).getTime() >= Date.now() - 60_000)
      .sort((a, b) => new Date(a.scheduled_at || 0).getTime() - new Date(b.scheduled_at || 0).getTime())
      .slice(0, 6),
    [plans],
  )

  const summary = useMemo(() => ({
    attention: jobs.filter((job) => job.status === 'needs_review' || job.status === 'failed').length,
    running: jobs.filter((job) => job.status === 'running' || job.status === 'queued').length,
    today: plans.filter((plan) => isToday(plan.scheduled_at ?? plan.created_at)).length,
    published: jobs.filter((job) => job.status === 'succeeded' && isToday(job.updated_at || job.created_at)).length,
  }), [jobs, plans])

  const readiness = [
    {
      label: '浏览器环境',
      detail: status?.ixbrowser.connected ? `${status.ixbrowser.total_profiles ?? 0} 个 iX 环境已发现` : 'iXBrowser Local API 未连接',
      ok: Boolean(status?.ixbrowser.connected),
      icon: BrowserIcon,
      to: '/accounts',
    },
    {
      label: '网络 / IP',
      detail: status?.ixbrowser.connected ? '随环境执行连接与出口 IP 检查' : '等待 Browser Runtime',
      ok: Boolean(status?.ixbrowser.connected),
      icon: NetworkIcon,
      to: '/accounts',
    },
    {
      label: '社交账号',
      detail: '登录与发布身份在执行前再次确认',
      ok: Boolean(status?.ixbrowser.connected),
      icon: AccountIcon,
      to: '/accounts',
    },
    {
      label: '素材中心',
      detail: '内容资产可直接进入发布工作流',
      ok: true,
      icon: AssetIcon,
      to: '/assets',
    },
    {
      label: '自动化流程',
      detail: status?.scheduler?.running ? 'Scheduler 与正式 Flow 可用' : 'Scheduler 未运行',
      ok: Boolean(status?.scheduler?.running),
      icon: FlowIcon,
      to: '/flows',
    },
  ]

  const readinessIssues = readiness.filter((item) => !item.ok).length

  return (
    <main className="sp-workbench">
      <WorkspaceHeader
        title="工作台"
        description="先处理需要关注的事项，再查看当前运行和接下来要执行的发布。"
        actions={(
          <Link to="/publish" className="sp-button sp-button--primary">
            <PlusIcon /> 新建发布
          </Link>
        )}
      />

      {error && <div className="sp-inline-alert"><AlertIcon /> <span>{error}</span></div>}

      <section className="sp-workbench-summary" aria-label="工作台摘要">
        <div className="sp-summary-item">
          <span className="sp-summary-number">{summary.attention}</span>
          <span className="sp-summary-copy"><strong>需要处理</strong><span>待确认与明确失败</span></span>
        </div>
        <div className="sp-summary-item">
          <span className="sp-summary-number">{summary.running}</span>
          <span className="sp-summary-copy"><strong>当前运行</strong><span>queued + running</span></span>
        </div>
        <div className="sp-summary-item">
          <span className="sp-summary-number">{summary.today}</span>
          <span className="sp-summary-copy"><strong>今天计划</strong><span>今天创建或计划执行</span></span>
        </div>
        <div className="sp-summary-item">
          <span className="sp-summary-number">{summary.published}</span>
          <span className="sp-summary-copy"><strong>今天已发布</strong><span>已验证成功结果</span></span>
        </div>
      </section>

      <div className="sp-workbench-grid">
        <div className="sp-workbench-stack">
          <Panel title="今日重点" meta={summary.attention ? `${summary.attention} 项需要关注` : '暂无阻塞'} action={<Link className="sp-panel-link" to="/review">查看全部</Link>}>
            {attention.length === 0 ? (
              <EmptyState title="当前没有需要人工处理的事项" description="待确认、失败或人工接管事项会优先出现在这里。" />
            ) : attention.map((job) => (
              <div className="sp-attention-row" key={job.id}>
                <span className={`sp-attention-icon ${job.status === 'failed' ? 'is-danger' : ''}`}><AlertIcon /></span>
                <span className="sp-attention-copy">
                  <strong>{platformName(job.platform)} · {targetName(job)}</strong>
                  <span>{job.status === 'needs_review' ? '发布结果需要人工确认，系统不会自动重试' : job.error_message || stageLabels[currentStage(job)] || '执行失败'}</span>
                </span>
                <StatusChip tone={statusTone(job.status)}>{job.status === 'needs_review' ? '需要确认' : '失败'}</StatusChip>
              </div>
            ))}
          </Panel>

          <Panel title="今天即将发布" meta={upcoming.length ? `${upcoming.length} 个最近计划` : '暂无未来计划'} action={<Link className="sp-panel-link" to="/plans">查看计划</Link>}>
            {upcoming.length === 0 ? (
              <EmptyState title="暂无即将执行的定时发布" description="创建定时发布后，最近安排会出现在这里。" />
            ) : upcoming.map((plan) => (
              <div className="sp-schedule-row" key={plan.id}>
                <time className="sp-schedule-time">{formatTime(plan.scheduled_at)}</time>
                <span className="sp-schedule-copy">
                  <strong>{plan.jobs?.length ? `批量发布 · ${plan.jobs.length} 个目标` : '定时发布'}</strong>
                  <span>{plan.publish_mode === 'scheduled' ? '已进入本地 Scheduler' : plan.status}</span>
                </span>
                <StatusChip tone="info">已计划</StatusChip>
              </div>
            ))}
          </Panel>
        </div>

        <div className="sp-workbench-stack">
          <Panel title="当前运行" meta={summary.running ? `${summary.running} 个任务` : '空闲'} action={<Link className="sp-panel-link" to="/tasks">查看运行</Link>}>
            {running.length === 0 ? (
              <EmptyState title="当前没有正在执行的任务" description="队列和运行中的发布会实时显示在这里。" />
            ) : running.map((job) => {
              const stage = currentStage(job)
              const progress = stageProgress[stage] ?? (job.status === 'queued' ? 8 : 12)
              return (
                <div className="sp-run-row" key={job.id}>
                  <div className="sp-run-row-head">
                    <span className="sp-run-copy">
                      <strong>{platformName(job.platform)} · {targetName(job)}</strong>
                      <span>{stageLabels[stage] || stage} · {jobDescription(job)}</span>
                    </span>
                    <StatusChip tone={job.status === 'running' ? 'info' : 'neutral'}>{job.status === 'running' ? '运行中' : '队列中'}</StatusChip>
                  </div>
                  <div className="sp-run-progress-line"><ProgressBar value={progress} /><span>{progress}%</span></div>
                </div>
              )
            })}
          </Panel>

          <Panel title="准备状态" meta={readinessIssues ? `${readinessIssues} 项需要检查` : '全部可用'} action={<Link className="sp-panel-link" to="/accounts">进入准备</Link>}>
            <div className="sp-readiness-list">
              {readiness.map((item) => {
                const Icon = item.icon
                return (
                  <Link to={item.to} key={item.label} className="sp-readiness-row" style={{ color: 'inherit', textDecoration: 'none' }}>
                    <span className="sp-readiness-icon"><Icon /></span>
                    <span className="sp-readiness-copy"><strong>{item.label}</strong><span>{item.detail}</span></span>
                    <StatusChip tone={item.ok ? 'success' : 'warning'}>{item.ok ? '正常' : '检查'}</StatusChip>
                  </Link>
                )
              })}
            </div>
          </Panel>
        </div>
      </div>
    </main>
  )
}
