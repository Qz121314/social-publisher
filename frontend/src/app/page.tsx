import React, { ReactNode } from 'react'

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string
  title: string
  description: string
  actions?: ReactNode
}) {
  return (
    <header className="page-header v1-page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="subtitle">{description}</p>
      </div>
      {actions && <div className="v1-page-actions">{actions}</div>}
    </header>
  )
}

export function PhaseBadge({ children = 'Phase 1' }: { children?: ReactNode }) {
  return <span className="v1-phase-badge">{children}</span>
}

export function ModuleEmpty({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children?: ReactNode
}) {
  return (
    <div className="v1-module-empty">
      <strong>{title}</strong>
      <span>{description}</span>
      {children}
    </div>
  )
}
