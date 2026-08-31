import React, { useMemo, useState } from 'react'

import { api } from '../../app/api'
import { Button, StatusChip } from '../../ui/components'

type AccountSummary = {
  id: number
  name: string
  platform: string
  status: string
  ix_profile_id?: number | null
  browser_profile?: { name: string } | null
}

type LoginExecution = {
  account_id: number
  profile_id: number
  state: string
  status: string
  message: string
  source_step: string
  identity_id?: string | null
  identity_confirmed: boolean
  action_required?: string | null
  browser_open: boolean
  current_url?: string | null
}

function statusView(status: string, hasRuntime: boolean) {
  if (!hasRuntime && status === 'prepared') return { label: '已准备', tone: 'info' as const }
  if (['logged_in', 'healthy', 'ok', 'ready'].includes(status)) return { label: '已登录', tone: 'success' as const }
  if (status === 'needs_2fa') return { label: '需要二次验证', tone: 'warning' as const }
  if (status === 'checkpoint') return { label: '安全检查', tone: 'warning' as const }
  if (status === 'needs_login') return { label: '需要登录', tone: 'warning' as const }
  if (status === 'needs_review') return { label: '需要确认', tone: 'warning' as const }
  if (['error', 'failed'].includes(status)) return { label: '登录失败', tone: 'danger' as const }
  return { label: '未检查', tone: 'neutral' as const }
}

export default function AccountLoginControl({
  account,
  onChanged,
  onMessage,
  onOpenSettings,
}: {
  account: AccountSummary
  onChanged: () => Promise<void> | void
  onMessage: (message: string) => void
  onOpenSettings: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [pendingConfirmation, setPendingConfirmation] = useState<LoginExecution | null>(null)
  const hasRuntime = Boolean(account.ix_profile_id && account.browser_profile)
  const status = useMemo(() => statusView(account.status, hasRuntime), [account.status, hasRuntime])
  const supported = account.platform === 'facebook' && hasRuntime

  const recover = async () => {
    if (!supported || busy) return
    setBusy(true)
    setPendingConfirmation(null)
    try {
      const result = await api<LoginExecution>(`/api/accounts/${account.id}/login/recover`, { method: 'POST' })
      await onChanged()
      if (result.action_required === '确认当前身份') {
        setPendingConfirmation(result)
        return
      }
      onMessage(result.message)
    } catch (error) {
      onMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const confirmIdentity = async () => {
    if (busy) return
    setBusy(true)
    try {
      const result = await api<LoginExecution>(`/api/accounts/${account.id}/login/confirm-identity`, { method: 'POST' })
      await onChanged()
      setPendingConfirmation(null)
      onMessage(result.message)
    } catch (error) {
      onMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="account-login-cell">
        <StatusChip tone={status.tone}>{status.label}</StatusChip>
        <div className="account-login-actions">
          {hasRuntime ? (
            <button
              type="button"
              className="account-login-recover"
              onClick={recover}
              disabled={!supported || busy}
              title={supported ? '检查现有登录状态，并只在必要时恢复登录' : '该平台的真实登录执行器尚未接入'}
            >
              {busy ? '处理中…' : supported ? '恢复登录' : '暂未接入'}
            </button>
          ) : (
            <span className="account-login-runtime-note" title="批量登录任务会自动创建并固定绑定 iX 环境">等待批量登录</span>
          )}
          <button type="button" className="account-login-settings" onClick={onOpenSettings} disabled={busy}>登录设置</button>
        </div>
      </div>

      {pendingConfirmation && (
        <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && setPendingConfirmation(null)}>
          <div className="sp-form-dialog account-dialog account-login-confirm-dialog" role="dialog" aria-modal="true" aria-label="确认当前登录身份" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div><span>首次身份确认</span><h2>确认当前 Facebook 账号</h2></div>
              <button type="button" onClick={() => setPendingConfirmation(null)} disabled={busy} aria-label="关闭">×</button>
            </header>
            <div className="account-dialog-body">
              <p className="account-login-confirm-copy">{pendingConfirmation.message}</p>
              <div className="account-login-confirm-summary">
                <div><span>账号</span><strong>{account.name}</strong></div>
                <div><span>浏览器环境</span><strong>{account.browser_profile?.name || '待创建'}{account.ix_profile_id ? ` · iX #${account.ix_profile_id}` : ''}</strong></div>
                <div><span>检测到的身份 ID</span><strong>{pendingConfirmation.identity_id || '未读取到'}</strong></div>
              </div>
              <div className="account-auth-note">请先查看已经打开的真实 iXBrowser 窗口，确认当前登录账号就是你准备绑定的账号。确认后，后续恢复登录会严格校验这个身份，不会自动覆盖。</div>
            </div>
            <footer>
              <Button type="button" onClick={() => setPendingConfirmation(null)} disabled={busy}>暂不确认</Button>
              <Button type="button" variant="primary" onClick={confirmIdentity} disabled={busy}>{busy ? '确认中…' : '确认当前身份'}</Button>
            </footer>
          </div>
        </div>
      )}
    </>
  )
}
