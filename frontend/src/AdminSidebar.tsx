import React from 'react'

const navItems = [
  { href: '#workspace', label: '控制台', meta: '状态与发布' },
  { href: '#facebook-targets', label: 'Facebook 目标', meta: '身份与主页' },
  { href: '#facebook-flow', label: '流程关键词', meta: '自动化规则' },
]

export default function AdminSidebar() {
  return (
    <aside className="admin-sidebar">
      <div className="admin-brand">
        <div className="brand-mark">SP</div>
        <div>
          <strong>Social Publisher</strong>
          <span>矩阵发布控制台</span>
        </div>
      </div>

      <nav className="admin-nav" aria-label="后台导航">
        <div className="nav-label">工作区</div>
        {navItems.map((item) => (
          <a key={item.href} href={item.href}>
            <span>{item.label}</span>
            <small>{item.meta}</small>
          </a>
        ))}
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
