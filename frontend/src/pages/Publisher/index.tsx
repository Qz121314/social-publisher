import React, { useEffect, useState } from 'react'

import ContentComposer, { ComposerProfile } from '../../ContentComposer'
import { api } from '../../app/api'
import { PageHeader, PhaseBadge } from '../../app/page'

export default function PublisherPage() {
  const [profiles, setProfiles] = useState<ComposerProfile[]>([])
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    api<ComposerProfile[]>('/api/browser-profiles')
      .then(setProfiles)
      .catch((error) => setMessage(error instanceof Error ? error.message : String(error)))
  }, [])

  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="发布中心"
        title="创建发布"
        description="V1 高频工作区：准备内容、选择发布目标，并创建一次发布意图。"
        actions={<PhaseBadge />}
      />

      {message && <div className="notice">{message}</div>}
      <p className="v1-inline-note">当前先挂载已经跑通的 ContentComposer 即时发布 PoC；立即 / 定时统一 PublishPlan 流水线将在 Phase 2–4 完成。</p>
      <ContentComposer profiles={profiles} onMessage={setMessage} />
    </main>
  )
}
