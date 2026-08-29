import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type IxStatus = {
  connected: boolean
  total_profiles?: number
  code?: number | string | null
  message?: string | null
}

type AppStatus = {
  app: string
  ixbrowser: IxStatus
}

function App() {
  const [status, setStatus] = useState<AppStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/status')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then(setStatus)
      .catch((err: Error) => setError(err.message))
  }, [])

  return (
    <main className="shell">
      <header>
        <p className="eyebrow">LOCAL CONTROL PLANE</p>
        <h1>Social Publisher</h1>
        <p className="subtitle">Multi-account publishing powered by iXBrowser profiles.</p>
      </header>

      <section className="grid">
        <article className="card">
          <span>Backend</span>
          <strong>{error ? 'Unavailable' : status ? 'Connected' : 'Checking…'}</strong>
          <small>FastAPI · 127.0.0.1:8765</small>
        </article>

        <article className="card">
          <span>iXBrowser</span>
          <strong>
            {status?.ixbrowser.connected ? 'Connected' : status ? 'Offline' : 'Checking…'}
          </strong>
          <small>
            {status?.ixbrowser.connected
              ? `${status.ixbrowser.total_profiles ?? 0} profiles detected`
              : status?.ixbrowser.message ?? 'Local API 127.0.0.1:53200'}
          </small>
        </article>

        <article className="card muted">
          <span>Scheduler</span>
          <strong>Next milestone</strong>
          <small>Job queue and worker pool</small>
        </article>
      </section>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
