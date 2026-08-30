import React, { useEffect, useMemo, useState } from 'react'

import FacebookFlowConfigPanel from '../../FacebookFlowConfigPanel'
import { api, formatDateTime } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'

type FlowStep = {
  id: string
  sort_order: number
  action_type: string
  name: string
  config_json: string
  enabled: boolean
}

type FlowRevision = {
  id: string
  version: number
  label: string
  status: string
  notes?: string | null
  published_at?: string | null
  steps: FlowStep[]
}

type Flow = {
  id: string
  platform: string
  key: string
  name: string
  enabled: boolean
  current_revision_id?: string | null
  revisions: FlowRevision[]
}

function configSummary(raw: string) {
  try {
    const value = JSON.parse(raw) as Record<string, unknown>
    const entries = Object.entries(value)
    if (entries.length === 0) return '默认配置'
    return entries.map(([key, item]) => `${key}: ${String(item)}`).join(' · ')
  } catch {
    return raw || '默认配置'
  }
}

export default function FlowsPage() {
  const [flows, setFlows] = useState<Flow[]>([])
  const [selectedFlowId, setSelectedFlowId] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      const result = await api<Flow[]>('/api/flows')
      setFlows(result)
      setSelectedFlowId((current) => current || result[0]?.id || '')
      setError(null)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    }
  }

  useEffect(() => {
    load()
  }, [])

  const flow = useMemo(
    () => flows.find((item) => item.id === selectedFlowId) ?? flows[0],
    [flows, selectedFlowId],
  )
  const revision = useMemo(
    () => flow?.revisions.find((item) => item.id === flow.current_revision_id) ?? flow?.revisions[0],
    [flow],
  )

  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="流程中心"
        title="Browser Workflow"
        description="正式读取 Flow → FlowRevision → FlowStep；已创建的发布计划固定绑定对应 Revision。"
        actions={<PhaseBadge>Phase 3</PhaseBadge>}
      />

      {error && <div className="notice">{error}</div>}

      <section className="v1-panel">
        <div className="v1-panel-heading">
          <div>
            <h2>{flow?.name || '暂无流程'}</h2>
            <p>{revision ? `${revision.label} · ${revision.status}` : '尚未建立发布版本'}</p>
          </div>
          {revision && <span className="v1-health-state">当前版本</span>}
        </div>

        {flows.length > 1 && (
          <div className="v1-toolbar">
            <select value={flow?.id || ''} onChange={(event) => setSelectedFlowId(event.target.value)}>
              {flows.map((item) => <option key={item.id} value={item.id}>{item.platform} · {item.name}</option>)}
            </select>
          </div>
        )}

        {!revision ? (
          <div className="empty-state compact-empty"><strong>暂无可执行 Revision</strong><span>发布中心只允许绑定已发布流程版本。</span></div>
        ) : (
          <>
            <div className="v1-flow-meta">
              <span>Revision #{revision.version}</span>
              <span>{revision.steps.filter((step) => step.enabled).length} 个启用步骤</span>
              <span>发布时间 {formatDateTime(revision.published_at)}</span>
            </div>
            <div className="v1-flow-list">
              {revision.steps.map((step, index) => (
                <div className={`v1-flow-row ${step.enabled ? '' : 'is-disabled'}`} key={step.id}>
                  <strong>{String(index + 1).padStart(2, '0')}</strong>
                  <div><strong>{step.name}</strong><small className="v1-flow-config">{configSummary(step.config_json)}</small></div>
                  <small>{step.action_type}</small>
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      <p className="v1-inline-note">下面保留现有 Facebook 高级关键词配置。它属于平台执行细节；正式任务绑定的是上方固定 Flow Revision，Phase 7 再进一步把 Adapter 内部拆成组合式模块。</p>
      <FacebookFlowConfigPanel />
    </main>
  )
}
