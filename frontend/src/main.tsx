import React from 'react'
import { createRoot } from 'react-dom/client'

import App from './App'
import FacebookTargetPanel from './FacebookTargetPanel'
import './styles.css'
import './publish.css'
import './facebook-target.css'

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <FacebookTargetPanel />
    <App />
  </React.StrictMode>,
)
