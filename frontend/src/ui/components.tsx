import React, { ButtonHTMLAttributes, ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type StatusTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

export function Button({
  variant = 'secondary',
  className = '',
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button className={`sp-button sp-button--${variant} ${className}`.trim()} {...props}>
      {children}
    </button>
  )
}

export function StatusChip({ tone = 'neutral', children }: { tone?: StatusTone; children: ReactNode }) {
  return <span className={`sp-status sp-status--${tone}`}>{children}</span>
}

export function Panel({
  title,
  meta,
  action,
  children,
  className = '',
}: {
  title?: ReactNode
  meta?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`sp-panel ${className}`.trim()}>
      {(title || action) && (
        <header className="sp-panel-header">
          <div className="sp-panel-heading">
            {title && <h2>{title}</h2>}
            {meta && <span>{meta}</span>}
          </div>
          {action}
        </header>
      )}
      <div className="sp-panel-body">{children}</div>
    </section>
  )
}

export function ListRow({
  title,
  meta,
  action,
  children,
}: {
  title: ReactNode
  meta?: ReactNode
  action?: ReactNode
  children?: ReactNode
}) {
  return (
    <div className="sp-list-row">
      <div className="sp-list-row-main">
        <div className="sp-list-row-title">{title}</div>
        {meta && <div className="sp-list-row-meta">{meta}</div>}
        {children}
      </div>
      {action}
    </div>
  )
}

export function ProgressBar({ value }: { value: number }) {
  const normalized = Math.max(0, Math.min(100, value))
  return <div className="sp-progress" aria-label={`${normalized}%`}><span style={{ width: `${normalized}%` }} /></div>
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="sp-empty">
      <div>
        <strong>{title}</strong>
        {description && <span>{description}</span>}
      </div>
    </div>
  )
}

export function WorkspaceHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <header className="sp-workspace-header">
      <div className="sp-workspace-header-copy">
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="sp-workspace-header-actions">{actions}</div>}
    </header>
  )
}
