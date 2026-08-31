import React from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import CommandPalette from './command-palette'
import AdminSidebar from './sidebar'

function workspaceName(pathname: string) {
  if (pathname === '/') return '工作台'
  if (pathname.startsWith('/accounts') || pathname.startsWith('/assets') || pathname.startsWith('/flows')) return '准备'
  if (pathname.startsWith('/publish') || pathname.startsWith('/plans')) return '发布'
  if (pathname.startsWith('/tasks')) return '运行'
  if (pathname.startsWith('/review')) return '检查'
  if (pathname.startsWith('/settings')) return '设置'
  return '工作区'
}

export default function AdminLayout() {
  const location = useLocation()

  return (
    <div className="sp-desktop-app">
      <AdminSidebar />
      <section className="sp-desktop-main">
        <header className="sp-topbar">
          <div className="sp-topbar-context">
            <strong>Social Publisher</strong>
            <span>/</span>
            <span>{workspaceName(location.pathname)}</span>
          </div>
          <CommandPalette />
        </header>
        <div className="admin-main sp-desktop-content">
          <Outlet />
        </div>
      </section>
    </div>
  )
}
