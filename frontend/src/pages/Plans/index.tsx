import React from 'react'

import { ModuleEmpty, PageHeader, PhaseBadge } from '../../app/page'

export default function PlansPage() {
  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="计划中心"
        title="发布计划"
        description="管理未来发布安排。SQLite 将作为 Scheduler 的 Source of Truth。"
        actions={<PhaseBadge />}
      />

      <section className="v1-panel">
        <div className="v1-panel-heading"><div><h2>计划列表</h2><p>月 / 周 / 列表视图的正式入口已经建立。</p></div><span className="v1-muted">数据模型待 Phase 2</span></div>
        <ModuleEmpty
          title="PublishPlan 尚未接入"
          description="Phase 1 不直接在旧 Content/Job 模型上堆定时 UI。Phase 2 先建立 PublishPlan 与快照模型，Phase 4 再接入 SQLite-backed Scheduler。"
        />
      </section>
    </main>
  )
}
