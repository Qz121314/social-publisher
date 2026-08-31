import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../../app/api'
import { AccountIcon, AssetIcon, FlowIcon, NetworkIcon } from '../../ui/icons'
import { Button, Panel, StatusChip, WorkspaceHeader } from '../../ui/components'
import PrepareNav from './PrepareNav'

type Account = {
  id: number
  enabled: boolean
  status: string
  proxy_id?: number | null
  ix_profile_id?: number | null
}

type ProxyEndpoint = {
  id: number
  status: string
  enabled: boolean
  assigned_count: number
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
  const [accounts, setAccounts] = useState<Account[]>([])
  const [proxies, setProxies] = useState<ProxyEndpoint[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [flows, setFlows] = useState<Flow[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      const [nextAccounts, nextProxies, nextAssets, nextFlows] = await Promise.all([
        api<Account[]>('/api/accounts'),
        api<ProxyEndpoint[]>('/api/proxy-pool'),
        api<Asset[]>('/api/assets?limit=100'),
        api<Flow[]>('/api/flows'),
      ])
      setAccounts(nextAccounts)
      setProxies(nextProxies)
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
    const enabledAccounts = accounts.filter((item) => item.enabled)
    const assignedAccounts = enabledAccounts.filter((item) => item.proxy_id).length
    const materializedAccounts = enabledAccounts.filter((item) => item.ix_profile_id).length
    const enabledProxies = proxies.filter((item) => item.enabled)
    const assignedProxies = enabledProxies.filter((item) => item.assigned_count > 0).length
    const errorProxies = enabledProxies.filter((item) => item.status === 'error').length
    const activeFlows = flows.filter((item) => item.enabled && item.current_revision_id).length

    return [
      {
        key: 'proxy-pool',
        title: 'IP池',
        description: '批量导入 SOCKS5，统一管理分配和网络健康状态。',
        href: '/prepare/proxies',
        icon: NetworkIcon,
        tone: enabledProxies.length > 0 && errorProxies === 0 ? 'success' : 'warning',
        status: enabledProxies.length > 0 ? '已有资源' : '需要导入',
        meta: `${enabledProxies.length} 条可用记录 · ${assignedProxies} 条已分配 · ${errorProxies} 条异常`,
      },
      {
        key: 'account-pool',
        title: '账号池',
        description: '批量准备账号、Cookie、密码、2FA、分组和固定 IP。',
        href: '/prepare/accounts',
        icon: AccountIcon,
        tone: enabledAccounts.length > 0 ? 'success' : 'warning',
        status: enabledAccounts.length > 0 ? '已有账号' : '需要导入',
        meta: `${enabledAccounts.length} 个账号 · ${assignedAccounts} 个已分配 IP · ${materializedAccounts} 个已有 iX 环境`,
      },
      {
        key: 'asset-pool',
        title: '素材池',
        description: '准备文案、图片、视频和后续可复用的内容组合。',
        href: '/assets',
        icon: AssetIcon,
        tone: assets.length > 0 ? 'success' : 'warning',
        status: assets.length > 0 ? '已有素材' : '需要导入',
        meta: `${assets.length} 条当前可读取素材记录`,
      },
      {
        key: 'flows',
        title: '自动化流程',
        description: '登录、账号维护和发布任务复用的稳定执行流程。',
        href: '/flows',
        icon: FlowIcon,
        tone: activeFlows > 0 ? 'success' : 'warning',
        status: activeFlows > 0 ? '已配置' : '需要配置',
        meta: `${activeFlows} 个启用且绑定当前 Revision 的流程`,
      },
    ]
  }, [accounts, proxies, assets, flows])

  const readyCount = items.filter((item) => item.tone === 'success').length

  return (
    <main className="prepare-workspace">
      <WorkspaceHeader
        title="准备"
        description="先准备资源池，再创建批量任务。iXBrowser 是运行时基础设施，不再作为账号录入的前置步骤。"
        actions={<Button variant="primary" onClick={load}>重新检查</Button>}
      />
      <PrepareNav />

      {error && <div className="sp-inline-alert">{error}</div>}

      <div className="prepare-overview-summary">
        <div>
          <span>资源准备度</span>
          <strong>{readyCount} / {items.length}</strong>
          <small>正式路径：IP池 → 账号池 → 素材池 → 创建任务 → 系统执行 → 只处理异常。</small>
        </div>
        <StatusChip tone={readyCount >= 3 ? 'success' : 'warning'}>{readyCount >= 3 ? '资源基础已具备' : '仍有资源需要准备'}</StatusChip>
      </div>

      <Panel title="资源池" meta="批量导入 · 批量操作 · 任务复用">
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

      <div className="prepare-advanced-runtime-link">
        <Link to="/prepare/environments">高级：查看 iXBrowser 运行环境</Link>
      </div>
    </main>
  )
}
