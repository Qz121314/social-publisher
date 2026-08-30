import React from 'react'

import FacebookFlowConfigPanel from '../../FacebookFlowConfigPanel'
import { PageHeader, PhaseBadge } from '../../app/page'

const facebookSteps = [
  ['01', '检查登录', 'CHECK_LOGIN'],
  ['02', '校验发布身份', 'VERIFY_ACTOR'],
  ['03', '打开目标主页', 'NAVIGATE'],
  ['04', '打开发帖 Composer', 'CLICK_TEXT'],
  ['05', '输入正文', 'INPUT_TEXT'],
  ['06', '上传媒体（如有）', 'UPLOAD_MEDIA'],
  ['07', '等待媒体完成', 'WAIT_MEDIA_READY'],
  ['08', '下一页（如存在）', 'NEXT'],
  ['09', '发布前身份复核', 'VERIFY_ACTOR'],
  ['10', '最终发布', 'PUBLISH'],
  ['11', '验证结果', 'VERIFY_RESULT'],
]

export default function FlowsPage() {
  return (
    <main className="v1-page">
      <PageHeader
        eyebrow="流程中心"
        title="Browser Workflow"
        description="以受约束的 Flow Step 描述浏览器自动化流程，不开放任意 JavaScript / Python / Shell。"
        actions={<PhaseBadge />}
      />

      <section className="v1-panel">
        <div className="v1-panel-heading"><div><h2>Facebook · 普通帖子</h2><p>当前已实际验证的个人主页 / 公共主页统一发布流水线。</p></div><span className="v1-health-state">PoC 已验证</span></div>
        <div className="v1-flow-list">
          {facebookSteps.map(([index, label, action]) => (
            <div className="v1-flow-row" key={index}><strong>{index}</strong><div><strong>{label}</strong></div><small>{action}</small></div>
          ))}
        </div>
      </section>

      <p className="v1-inline-note">Flow / FlowRevision / FlowStep 的数据库模型和版本绑定属于 Phase 2。本阶段只先把“流程”从一级旧配置面板提升为正式业务中心。</p>
      <FacebookFlowConfigPanel />
    </main>
  )
}
