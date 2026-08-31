import React from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import AdminLayout from './layout'
import AccountsPage from '../pages/Accounts'
import AssetsPage from '../pages/Assets'
import DashboardPage from '../pages/Dashboard'
import FlowsPage from '../pages/Flows'
import PlansPage from '../pages/Plans'
import PublisherPage from '../pages/Publisher'
import ReviewPage from '../pages/Review'
import SettingsPage from '../pages/Settings'
import TasksPage from '../pages/Tasks'

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AdminLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="assets" element={<AssetsPage />} />
          <Route path="accounts" element={<AccountsPage />} />
          <Route path="flows" element={<FlowsPage />} />
          <Route path="publish" element={<PublisherPage />} />
          <Route path="plans" element={<PlansPage />} />
          <Route path="tasks" element={<TasksPage />} />
          <Route path="review" element={<ReviewPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
