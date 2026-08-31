import React from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import AdminLayout from './layout'
import AssetsPage from '../pages/Assets'
import DashboardPage from '../pages/Dashboard'
import FlowsPage from '../pages/Flows'
import PlansPage from '../pages/Plans'
import PreparePage from '../pages/Prepare'
import BrowserEnvironmentsPage from '../pages/Prepare/BrowserEnvironments'
import SocialAccountsPage from '../pages/Prepare/SocialAccounts'
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
          <Route path="prepare" element={<PreparePage />} />
          <Route path="prepare/environments" element={<BrowserEnvironmentsPage />} />
          <Route path="prepare/network" element={<Navigate to="/prepare/environments" replace />} />
          <Route path="prepare/accounts" element={<SocialAccountsPage />} />
          <Route path="assets" element={<AssetsPage />} />
          <Route path="accounts" element={<Navigate to="/prepare/accounts" replace />} />
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
