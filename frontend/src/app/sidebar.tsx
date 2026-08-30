import React from 'react'
import { NavLink } from 'react-router-dom'

const primaryNav = [
  { to: '/', label: '总览', meta: '运行状态与待处理事项', end: true },
  { to: '/assets', label: '素材中心', meta: '内容资产与媒体' },
  { to: '/accounts', label: 'iX账号中心', meta: '环境、账号与渠道' },
  { to: '/flows', label: '流程中心', meta: '浏览器自动化流程' },
  { to: '/publish', label: '发布中心', meta: '创建一次发布' },
  { to: '/plans', label: '计划中心', meta: '未来发布安排' },
  { to: '/tasks', label: '任务中心', meta: '执行状态与历史' },
]

function NavItem({ to, label, meta, end = false }: { to: string; label: string; meta: string; end?: boolean }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => isActive ? 'active' : undefined}>
      <span>{label}</span>
      <small>{meta}</small>
    </NavLink>
  )
}

export default function AdminSidebar() {
  return (
    <aside className="admin-sidebar v1-sidebar">
      <div className="admin-brand">
        <div className="brand-mark">SP</div>
        <div>
          <strong>Social Publisher</strong>
          <span>V1 本地矩阵发布平台</span>
        </div>
      </div>

      <nav className="admin-nav" aria-label="V1 后台导航">
        <div className="nav-label">工作区</div>
        {primaryNav.map((item) => <NavItem key={item.to} {...item} />)}
      </nav>

      <nav className="admin-nav v1-settings-nav" aria-label="系统配置">
        <div className="nav-label">系统</div>
        <NavItem to="/settings" label="配置中心" meta="运行规则与平台配置" />
      </nav>

      <div className="sidebar-note">
        <span className="sidebar-status-dot"></span>
        <div>
          <strong>本地运行模式</strong>
          <small>iXBrowser + Selenium</small>
        </div>
      </div>
    </aside>
  )
}
