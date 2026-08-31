import React from 'react'

import { NetworkIcon } from '../../ui/icons'
import { Panel, StatusChip, WorkspaceHeader } from '../../ui/components'
import PrepareNav from './PrepareNav'

export default function NetworkPage() {
  return (
    <main className="prepare-workspace">
      <WorkspaceHeader
        title="网络 / IP"
        description="这一层将独立管理 Proxy、出口 IP、连通性和浏览器环境绑定，不直接依赖 iX Profile 原始配置字段。"
      />
      <PrepareNav />

      <Panel title="网络服务" meta="Phase 10 后续模块">
        <div className="prepare-network-empty">
          <div className="prepare-network-icon"><NetworkIcon /></div>
          <div>
            <strong>独立 Proxy / IP 服务尚未接入</strong>
            <p>当前版本不会从 iXBrowser raw profile 中猜测、复制或展示 Proxy 用户名、密码和出口 IP。后续会用单独的 ProxyEndpoint / Network Health 服务管理这些信息。</p>
          </div>
          <StatusChip tone="neutral">待接入</StatusChip>
        </div>
      </Panel>
    </main>
  )
}
