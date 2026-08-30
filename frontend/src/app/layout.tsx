import React from 'react'
import { Outlet } from 'react-router-dom'

import AdminSidebar from './sidebar'

export default function AdminLayout() {
  return (
    <div className="admin-app v1-admin-app">
      <AdminSidebar />
      <div className="admin-main v1-admin-main">
        <Outlet />
      </div>
    </div>
  )
}
