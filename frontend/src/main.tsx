import React from 'react'
import { createRoot } from 'react-dom/client'

import AdminSidebar from './AdminSidebar'
import App from './App'
import FacebookFlowConfigPanel from './FacebookFlowConfigPanel'
import FacebookTargetPanel from './FacebookTargetPanel'
import './styles.css'
import './publish.css'
import './facebook-target.css'
import './admin-shell.css'
import './facebook-flow-config.css'

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <div className="admin-app">
      <AdminSidebar />
      <div className="admin-main">
        <div id="workspace" className="admin-section-anchor">
          <App />
        </div>
        <div id="facebook-targets" className="admin-section-anchor">
          <FacebookTargetPanel />
        </div>
        <div id="facebook-flow" className="admin-section-anchor">
          <FacebookFlowConfigPanel />
        </div>
      </div>
    </div>
  </React.StrictMode>,
)
