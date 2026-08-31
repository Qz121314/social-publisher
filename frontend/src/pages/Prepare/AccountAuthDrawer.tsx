import React, { FormEvent, useEffect, useState } from 'react'

import { api } from '../../app/api'
import { Button, StatusChip } from '../../ui/components'

type AccountSummary = {
  id: number
  name: string
  platform: string
  ix_profile_id?: number | null
  browser_profile?: { name: string } | null
}

type AuthConfig = {
  account_id: number
  login_identifier?: string | null
  allow_cookie_restore: boolean
  allow_password_login: boolean
  allow_totp: boolean
  password_configured: boolean
  totp_configured: boolean
  cookie_configured: boolean
  cookie_count: number
  vault_supported: boolean
  vault_backend: string
  login_plan: string[]
}

const planLabels: Record<string, string> = {
  existing_session: '现有登录状态',
  cookie_restore: 'Cookie 恢复',
  password: '账号密码',
  totp: 'TOTP 二次验证',
  manual_takeover: '人工处理',
}

export default function AccountAuthDrawer({
  account,
  onClose,
  onSaved,
}: {
  account: AccountSummary
  onClose: () => void
  onSaved?: (message: string) => void
}) {
  const [config, setConfig] = useState<AuthConfig | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
    api<AuthConfig>(`/api/accounts/auth/${account.id}`)
      .then(setConfig)
      .catch((next) => setError(next instanceof Error ? next.message : String(next)))
  }, [account.id])

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!config) return
    const form = new FormData(event.currentTarget)
    setBusy(true)
    setError(null)
    try {
      const payload = {
        login_identifier: String(form.get('login_identifier') ?? '').trim(),
        allow_cookie_restore: form.get('allow_cookie_restore') === 'on',
        allow_password_login: form.get('allow_password_login') === 'on',
        allow_totp: form.get('allow_totp') === 'on',
        password: String(form.get('password') ?? '') || undefined,
        totp_secret: String(form.get('totp_secret') ?? '') || undefined,
        cookie_json: String(form.get('cookie_json') ?? '') || undefined,
      }
      const next = await api<AuthConfig>(`/api/accounts/auth/${account.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      setConfig(next)
      onSaved?.(`账号“${account.name}”的登录设置已保存。`)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError))
    } finally {
      setBusy(false)
    }
  }

  const runtimeLabel = account.browser_profile && account.ix_profile_id
    ? `${account.browser_profile.name} · iX #${account.ix_profile_id}`
    : '将在批量登录时自动创建并固定绑定'

  return (
    <div className="environment-create-backdrop" role="presentation" onMouseDown={() => !busy && onClose()}>
      <aside className="environment-create-drawer account-auth-drawer" role="dialog" aria-modal="true" aria-label="账号登录设置" onMouseDown={(event) => event.stopPropagation()}>
        <form onSubmit={save}>
          <header className="environment-create-header">
            <div><h2>登录设置</h2><p>{account.name} · {account.platform === 'facebook' ? 'Facebook' : 'Instagram'} · {runtimeLabel}</p></div>
            <button type="button" className="environment-create-close" onClick={onClose} disabled={busy} aria-label="关闭">×</button>
          </header>

          <div className="environment-create-body account-auth-body">
            {error && <div className="sp-inline-alert">{error}</div>}
            {!config ? <p>正在读取安全设置…</p> : (
              <>
                <div className="account-auth-summary">
                  <div><span>Cookie</span><StatusChip tone={config.cookie_configured ? 'success' : 'neutral'}>{config.cookie_configured ? `${config.cookie_count} 条已保存` : '未配置'}</StatusChip></div>
                  <div><span>密码</span><StatusChip tone={config.password_configured ? 'success' : 'neutral'}>{config.password_configured ? '已安全保存' : '未配置'}</StatusChip></div>
                  <div><span>TOTP</span><StatusChip tone={config.totp_configured ? 'success' : 'neutral'}>{config.totp_configured ? '已安全保存' : '未配置'}</StatusChip></div>
                </div>

                <label className="environment-field"><span>登录账号 / 邮箱</span><input name="login_identifier" defaultValue={config.login_identifier ?? ''} placeholder="可选，用于账号密码登录" /></label>
                <label className="environment-field"><span>密码</span><input name="password" type="password" autoComplete="new-password" placeholder={config.password_configured ? '已配置；留空保持不变' : '可选'} /></label>
                <label className="environment-field"><span>TOTP Secret</span><input name="totp_secret" type="password" autoComplete="off" placeholder={config.totp_configured ? '已配置；留空保持不变' : '可选，用于 Authenticator 6 位验证码'} /></label>
                <label className="environment-field"><span>Cookie JSON</span><textarea name="cookie_json" rows={8} placeholder={config.cookie_configured ? '已配置；留空保持不变' : '粘贴浏览器导出的 Cookie JSON 数组'} /></label>

                <div className="account-auth-options">
                  <label><input type="checkbox" name="allow_cookie_restore" defaultChecked={config.allow_cookie_restore} />允许 Cookie 恢复</label>
                  <label><input type="checkbox" name="allow_password_login" defaultChecked={config.allow_password_login} />必要时账号密码登录</label>
                  <label><input type="checkbox" name="allow_totp" defaultChecked={config.allow_totp} />允许 TOTP 自动验证</label>
                </div>

                <div className="account-auth-plan">
                  <strong>登录策略</strong>
                  <div>{config.login_plan.map((step, index) => <span key={step}>{index + 1}. {planLabels[step] || step}</span>)}</div>
                </div>
                <div className="account-auth-note">密码、Cookie、TOTP 不会回显到界面，也不会写入普通 SQLite。Windows 上由 DPAPI 加密保存。短信、邮箱、App Approval、Security Key、Checkpoint 等仍转人工处理。</div>
              </>
            )}
          </div>

          <footer className="environment-create-footer">
            <Button type="button" onClick={onClose} disabled={busy}>关闭</Button>
            <Button variant="primary" type="submit" disabled={busy || !config}>{busy ? '保存中…' : '保存登录设置'}</Button>
          </footer>
        </form>
      </aside>
    </div>
  )
}
