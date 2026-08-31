import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../../app/api'
import { AccountIcon, AssetIcon, BrowserIcon, FlowIcon } from '../../ui/icons'
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
  proxy_type?: string | null
  proxy_ip?: string | null
  proxy_port?: string | null
  real_ip?: string | null
  is_available: boolean
}

type Account = {
  id: number
  enabled: boolean
  status: string
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

const loggedInStates = new Set(['logged_in', 'healthy', 'ok', 'ready'])

export default function PreparePage() {
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null)
  const [profiles, setProfiles] = useState<BrowserProfile[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [channels, setChannels] = useState<Channel[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [flows, setFlows] = useState<Flow[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      const [nextRuntime, nextProfiles, nextAccounts, nextChannels, nextAssets, nextFlows] = await Promise.all([
        api<RuntimeStatus>('/api/status'),
        api<BrowserProfile[]>('/api/browser-profiles'),
        api<Account[]>('/api/accounts'),
        api<Channel[]>('/api/channels'),
        api<Asset[]>('/api/assets?limit=100'),
        api<Flow[]>('/api/flows'),
      ])
      setRuntime(nextRuntime)
      setProfiles(nextProfiles)
      setAccounts(nextAccounts)
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
    const socks5Profiles = profiles.filter((item) => item.proxy_type === 'socks5' && item.proxy_ip && item.proxy_port).length
    const detectedExitIps = profiles.filter((item) => item.real_ip).length
    const enabledAccounts = accounts.filter((item) => item.enabled)
    const loggedInAccounts = enabledAccounts.filter((item) => loggedInStates.has(item.status)).length
    const healthyChannels = channels.filter((item) => item.enabled && ['healthy', 'ok', 'running'].includes(item.health_status)).length
    const enabledChannels = channels.filter((item) => item.enabled).length
    const activeFlows = flows.filter((item) => item.enabled && item.current_revision_id).length

    const browserTone = runtime?.ixbrowser?.connected && availableProfiles > 0 ? 'success' : 'danger'
    const accountTone = enabledAccounts.length > 0 && loggedInAccounts === enabledAccounts.length ? 'success' : 'warning'
    const assetTone = assets.length > 0 ? 'success' : 'warning'
    const flowTone = activeFlows > 0 ? 'success' : 'warning'

    return [
      {
        key: 'browser',
        title: '浏览器环境 + SOCKS5',
        description: 'iXBrowser Profile、SOCKS5、出口 IP 与真实浏览器会话统一管理。',
        href: '/prepare/environments',
        icon: BrowserIcon,
        tone: browserTone,
        status: browserTone === 'success' ? '已连接' : '需要检查',
        meta: runtime?.ixbrowser?.connected
          ? `${availableProfiles} / ${profiles.length} 个环境可用 · ${socks5Profiles} 个配置 SOCKS5 · ${detectedExitIps} 个有出口 IP`
          : 'iXBrowser Local API 未连接',
      },
      {
        key: 'accounts',
        title: '社交账号',
        description: '创建账号时直接创建/绑定 iX 环境、配置 SOCKS5，并在真实窗口完成登录。',
        href: '/prepare/accounts',
        icon: AccountIcon,
        tone: accountTone,
        status: accountTone === 'success' ? '已登录' : '需要准备',
        meta: `${enabledAccounts.length} 个启用账号 · ${loggedInAccounts} 个已登录 · ${healthyChannels} / ${enabledChannels} 个 Channel 正常`,
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
  }, [runtime, profiles, accounts, channels, assets, flows])

  const readyCount = items.filter((item) => item.tone === 'success').length
  const allReady = readyCount === items.length

  return (
    <main className="prepare-workspace">
      <WorkspaceHeader
        title="准备"
        description="账号、iX 环境、SOCKS5 和登录现在按同一条工作流准备，不再拆成独立网络中心。"
        actions={<Button variant="primary" onClick={load}>重新检查</Button>}
      />
      <PrepareNav />

      {error && <div className="sp-inline-alert">{error}</div>}

      <div className="prepare-overview-summary">
        <div>
          <span>整体准备度</span>
          <strong>{readyCount} / {items.length}</strong>
          <small>网络是 iX 浏览器环境的一部分：工作台只展示安全的 SOCKS5 Host / Port 与出口 IP，不显示代理密码。</small>
        </div>
        <StatusChip tone={allReady ? 'success' : 'warning'}>{allReady ? '已具备发布条件' : '存在未完成准备项'}</StatusChip>
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
