import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../../app/api'
import { AccountIcon, AssetIcon, BrowserIcon, FlowIcon, NetworkIcon } from '../../ui/icons'
import { Button, Panel, StatusChip, WorkspaceHeader } from '../../ui/components'
import PrepareNav from './PrepareNav'

type RuntimeStatus = {
  app?: string
  ixbrowser?: { connected?: boolean; total_profiles?: number; message?: string | null }
  browser_pool?: { total_sessions?: number; warm_sessions?: number }
}

type BrowserProfile = {
  profile_id: number
  name: string
  group_name?: string | null
  is_available: boolean
}

type Channel = {
  id: string
  profile_id: number
  platform: string
  enabled: boolean
  health_status: string
}

type Asset = { id: string }

type Flow = { id: string; enabled: boolean; current_revision_id?: string | null }

type ReadinessItem = {
  key: string
  title: string
  description: string
  href: string
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>
  tone: 'success' | 'warning' | 'danger' | 'info' | 'neutral'
  status: string
  meta: string
}

export default function PreparePage() {
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null)
  const [profiles, setProfiles] = useState<BrowserProfile[]>([])
  const [channels, setChannels] = useState<Channel[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [flows, setFlows] = useState<Flow[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      const [nextRuntime, nextProfiles, nextChannels, nextAssets, nextFlows] = await Promise.all([
        api<RuntimeStatus>('/api/status'),
        api<BrowserProfile[]>('/api/browser-profiles'),
        api<Channel[]>('/api/channels'),
        api<Asset[]>('/api/assets?limit=100'),
        api<Flow[]>('/api/flows'),
      ])
      setRuntime(nextRuntime)
      setProfiles(nextProfiles)
      setChannels(nextChannels)
      setAssets(nextAssets)
      setFlows(nextFlows)
      setError(null)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    }
  }

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 10000)
    return () => window.clearInterval(timer)
  }, [])

  const items = useMemo<ReadinessItem[]>(() => {
    const availableProfiles = profiles.filter((item) => item.is_available).length
    const healthyChannels = channels.filter((item) => item.enabled && ['healthy', 'ok', 'running'].includes(item.health_status)).length
    const enabledChannels = channels.filter((item) => item.enabled).length
    const activeFlows = flows.filter((item) => item.enabled && item.current_revision_id).length

    const browserTone = runtime?.ixbrowser?.connected && availableProfiles > 0 ? 'success' : 'danger'
    const accountTone = enabledChannels === 0 ? 'warning' : healthyChannels === enabledChannels ? 'success' : 'warning'
    const assetTone = assets.length > 0 ? 'success' : 'warning'
    const flowTone = activeFlows > 0 ? 'success' : 'warning'

    return [
      {
        key: 'browser',
        title: '浏览器环境',
        description: 'iXBrowser Profile、会话状态与人工打开/关闭。',
        href: '/prepare/environments',
        icon: BrowserIcon,
        tone: browserTone,
        status: browserTone === 'success' ? '已就绪' : '需要检查',
        meta: runtime?.ixbrowser?.connected
          ? `${availableProfiles} / ${profiles.length} 个环境可用 · ${runtime.browser_pool?.total_sessions ?? 0} 个已打开会话`
          : 'iXBrowser Local API 未连接',
      },
      {
        key: 'network',
        title: '网络 / IP',
        description: 'Proxy、出口 IP、连接质量与环境绑定。',
        href: '/prepare/network',
        icon: NetworkIcon,
        tone: 'neutral',
        status: '待接入',
        meta: '当前版本尚未建立独立 Proxy / IP 服务，不展示模拟数据。',
      },
      {
        key: 'accounts',
        title: '社交账号',
        description: 'Facebook / Instagram 登录身份与正式 Channel。',
        href: '/accounts',
        icon: AccountIcon,
        tone: accountTone,
        status: accountTone === 'success' ? '已就绪' : '需要检查',
        meta: `${enabledChannels} 个启用 Channel · ${healthyChannels} 个状态正常`,
      },
      {
        key: 'assets',
        title: '素材中心',
        description: '提前准备文案、图片、视频与后续 ContentPackage。',
        href: '/assets',
        icon: AssetIcon,
        tone: assetTone,
        status: assetTone === 'success' ? '有可用素材' : '暂无素材',
        meta: `${assets.length} 条当前可读取素材记录`,
      },
      {
        key: 'flows',
        title: '自动化流程',
        description: '平台发布流程、稳定 Revision 与高级诊断配置。',
        href: '/flows',
        icon: FlowIcon,
        tone: flowTone,
        status: flowTone === 'success' ? '已验证' : '需要配置',
        meta: `${activeFlows} 个启用且绑定当前 Revision 的流程`,
      },
    ]
  }, [runtime, profiles, channels, assets, flows])

  const readyCount = items.filter((item) => item.tone === 'success').length

  return (
    <main className="prepare-workspace">
      <WorkspaceHeader
        title="准备"
        description="在创建发布之前检查浏览器、账号、素材和流程是否已经具备执行条件。"
        actions={<Button variant="primary" onClick={load}>重新检查</Button>}
      />
      <PrepareNav />

      {error && <div className="sp-inline-alert">{error}</div>}

      <div className="prepare-overview-summary">
        <div>
          <span>整体准备度</span>
          <strong>{readyCount} / {items.length}</strong>
          <small>这里只统计当前已经真实接入的数据源；网络 / IP 在独立服务完成前保持“待接入”。</small>
        </div>
        <StatusChip tone={readyCount >= 4 ? 'success' : 'warning'}>{readyCount >= 4 ? '可继续准备发布' : '存在未完成准备项'}</StatusChip>
      </div>

      <Panel title="发布前条件" meta="按真实运行依赖排序">
        <div className="prepare-readiness-list">
          {items.map((item) => {
            const Icon = item.icon
            return (
              <Link to={item.href} className="prepare-readiness-row" key={item.key}>
                <div className="prepare-readiness-icon"><Icon /></div>
                <div className="prepare-readiness-main">
                  <div className="prepare-readiness-title">{item.title}</div>
                  <div className="prepare-readiness-description">{item.description}</div>
                  <div className="prepare-readiness-meta">{item.meta}</div>
                </div>
                <StatusChip tone={item.tone}>{item.status}</StatusChip>
              </Link>
            )
          })}
        </div>
      </Panel>
    </main>
  )
}
