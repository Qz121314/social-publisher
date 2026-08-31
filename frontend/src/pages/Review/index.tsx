import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, formatDateTime } from '../../app/api'
import { EmptyState, Panel, StatusChip, WorkspaceHeader } from '../../ui/components'
import { AlertIcon } from '../../ui/icons'
import './review.css'

type PublishJob = {
  id: string
  platform: string
  status: string
  stage?: string | null
  channel_snapshot_json?: string | null
  error_message?: string | null
  updated_at?: string | null
  created_at: string
}

type ChannelSnapshot = {
  target_name?: string
  profile_id?: number
}

function parseChannel(raw?: string | null): ChannelSnapshot | null {
  if (!raw) return null
  try { return JSON.parse(raw) as ChannelSnapshot } catch { return null }
}

function platformName(value: string) {
  if (value === 'facebook') return 'Facebook'
  if (value === 'instagram') return 'Instagram'
  return value
}

export default function ReviewPage() {
  const [items, setItems] = useState<PublishJob[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      setItems(await api<PublishJob[]>('/api/tasks/publish-jobs?limit=100'))
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

  const needsAction = useMemo(
    () => items.filter((item) => item.status === 'needs_review' || item.status === 'failed'),
    [items],
  )

  return (
    <main className="sp-review-page">
      <WorkspaceHeader
        title="检查"
        description="这里只放需要判断或处理的结果；技术 Timeline 和高级诊断仍保留在任务详情中。"
        actions={<Link className="sp-button sp-button--secondary" to="/tasks">查看全部运行记录</Link>}
      />

      {error && <div className="sp-inline-alert"><AlertIcon /><span>{error}</span></div>}

      <Panel title="需要处理" meta={`${needsAction.length} 项`}>
        {needsAction.length === 0 ? (
          <EmptyState title="当前没有需要处理的结果" description="发布结果不确定或明确失败时，会进入这里等待人工判断。" />
        ) : (
          <div className="sp-review-list">
            {needsAction.map((item) => {
              const channel = parseChannel(item.channel_snapshot_json)
              const review = item.status === 'needs_review'
              return (
                <article className="sp-review-row" key={item.id}>
                  <span className={`sp-review-icon ${review ? '' : 'is-danger'}`}><AlertIcon /></span>
                  <div className="sp-review-copy">
                    <strong>{platformName(item.platform)} · {channel?.target_name || 'Channel'}</strong>
                    <p>{review ? '系统可能已经执行最终发布动作，但当前无法确认发布结果。' : item.error_message || '任务明确失败，需要检查最后一个成功阶段。'}</p>
                    <small>iX #{channel?.profile_id ?? '—'} · {formatDateTime(item.updated_at || item.created_at)}</small>
                  </div>
                  <div className="sp-review-actions">
                    <StatusChip tone={review ? 'warning' : 'danger'}>{review ? '需要确认' : '失败'}</StatusChip>
                    <Link className="sp-button sp-button--secondary" to="/tasks">打开详情</Link>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </Panel>
    </main>
  )
}
