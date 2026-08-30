import React from 'react'
import { createRoot } from 'react-dom/client'

import AppRouter from './app/router'
import './styles.css'
import './publish.css'
import './facebook-target.css'
import './admin-shell.css'
import './facebook-flow-config.css'
import './app/v1-shell.css'
import './app/phase3.css'

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppRouter />
  </React.StrictMode>,
)
