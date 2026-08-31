import React, { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { api } from './api'
import { HomeIcon, PrepareIcon, ReviewIcon, RunIcon, SendIcon, SettingsIcon } from '../ui/icons'

type RuntimeStatus = {
  app?: string
  ixbrowser?: { connected?: boolean }
}

const navigation = [
  { to: '/', label: '工作台', icon: HomeIcon, match: ['/'] },
  { to: '/accounts', label: '准备', icon: PrepareIcon, match: ['/accounts', '/assets', '/flows'] },
  { to: '/publish', label: '发布', icon: SendIcon, match: ['/publish', '/plans'] },
  { to: '/tasks', label: '运行', icon: RunIcon, match: ['/tasks'] },
  { to: '/review', label: '检查', icon: ReviewIcon, match: ['/review'] },
]

function isActive(pathname: string, match: string[]) {
  if (match.includes('/')) return pathname === '/'
  return match.some((path) => pathname === path || pathname.startsWith(`${path}/`))
}

export default function AdminSidebar() {
  const location = useLocation()
  const [status, setStatus] = useState<RuntimeStatus | null>(null)

  useEffect(() => {
    let alive = true
    const load = () => api<RuntimeStatus>('/api/status').then((next) => {
      if (alive) setStatus(next)
    }).catch(() => {
      if (alive) setStatus(null)
    })
    load()
    const timer = window.setInterval(load, 10000)
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [])

  const runtimeOk = status?.app === 'ok' && Boolean(status?.ixbrowser?.connected)

  return (
    <aside className="sp-sidebar">
      <div className="sp-brand">
        <div className="sp-brand-mark">SP</div>
        <div className="sp-brand-copy">
          <strong>Social Publisher</strong>
          <span>Desktop Workspace</span>
        </div>
      </div>

      <nav className="sp-nav" aria-label="主导航">
        {navigation.map((item) => {
          const Icon = item.icon
          const active = isActive(location.pathname, item.match)
          return (
            <Link key={item.label} className={`sp-nav-item ${active ? 'is-active' : ''}`} to={item.to} aria-current={active ? 'page' : undefined}>
              <Icon />
              <span>{item.label}</span>
            </Link>
          )
        })}
      </nav>

      <div className="sp-sidebar-spacer" />

      <nav className="sp-nav sp-nav--system" aria-label="系统导航">
        <Link className={`sp-nav-item ${location.pathname.startsWith('/settings') ? 'is-active' : ''}`} to="/settings">
          <SettingsIcon />
          <span>设置</span>
        </Link>
      </nav>

      <div className="sp-runtime-card">
        <span className={`sp-runtime-dot ${runtimeOk ? 'is-online' : ''}`} />
        <div>
          <strong>{runtimeOk ? 'Runtime 正常' : 'Runtime 待检查'}</strong>
          <span>{status?.ixbrowser?.connected ? 'iXBrowser 已连接' : 'iXBrowser 未连接'}</span>
        </div>
      </div>
    </aside>
  )
}
