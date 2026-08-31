import React, { FormEvent, useEffect, useState } from 'react'

import { api } from '../../app/api'
import { Button, StatusChip } from '../../ui/components'

type AccountSummary = {
  id: number
  name: string
  platform: string
  ix_profile_id: number
  browser_profile: { name: string }
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
    const password = String(form.get('password') ?? '')
    const totpSecret = String(form.get('totp_secret') ?? '')
    const cookieJson = String(form.get('cookie_json') ?? '')

    const payload: Record<string, unknown> = {
      login_identifier: String(form.get('login_identifier') ?? '').trim(),
      allow_cookie_restore: form.get('allow_cookie_restore') === 'on',
      allow_password_login: form.get('allow_password_login') === 'on',
      allow_totp: form.get('allow_totp') === 'on',
      clear_password: form.get('clear_password') === 'on',
      clear_totp: form.get('clear_totp') === 'on',
      clear_cookies: form.get('clear_cookies') === 'on',
    }
    if (password) payload.password = password
    if (totpSecret) payload.totp_secret = totpSecret
    if (cookieJson.trim()) payload.cookie_json = cookieJson.trim()

    setBusy(true)
    setError(null)
    try {
      const next = await api<AuthConfig>(`/api/accounts/auth/${account.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      setConfig(next)
      onSaved?.(`账号“${account.name}”的登录配置已保存。`)
      onClose()
    } catch (next) {
      setError(next instanceof Error ? next.message : String(next))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="sp-modal-backdrop" role="presentation" onMouseDown={() => !busy && onClose()}>
      <div className="account-auth-drawer" role="dialog" aria-modal="true" aria-label="登录设置" onMouseDown={(event) => event.stopPropagation()}>
        <form onSubmit={save}>
          <header className="account-auth-header">
            <div>
              <span>登录设置</span>
              <h2>{account.name}</h2>
              <p>{account.browser_profile.name} · iX #{account.ix_profile_id}</p>
            </div>
            <button type="button" onClick={onClose} disabled={busy} aria-label="关闭">×</button>
          </header>

          <div className="account-auth-body">
            {error && <div className="prepare-message is-error">{error}</div>}
            {!config ? (
              <div className="account-auth-loading">正在读取登录配置…</div>
            ) : (
              <>
                {!config.vault_supported && (
                  <div className="account-auth-warning">当前系统未启用 Windows DPAPI 安全存储，因此不能保存密码、Cookie 或 TOTP 密钥。</div>
                )}

                <section className="account-auth-section">
                  <div className="account-auth-section-title">
                    <div><strong>自动恢复顺序</strong><span>系统只在前一步无效时继续下一步。</span></div>
                  </div>
                  <div className="account-auth-plan">
                    {config.login_plan.map((step, index) => (
                      <React.Fragment key={step}>
                        {index > 0 && <span>→</span>}
                        <StatusChip tone={step === 'manual_takeover' ? 'warning' : 'neutral'}>{planLabels[step] ?? step}</StatusChip>
                      </React.Fragment>
                    ))}
                  </div>
                </section>

                <section className="account-auth-section">
                  <div className="account-auth-section-title"><div><strong>账号密码</strong><span>仅作为现有 Session / Cookie 无效后的备用方式。</span></div></div>
                  <label><span>登录账号</span><input name="login_identifier" defaultValue={config.login_identifier ?? ''} placeholder="邮箱、手机号或平台用户名" /></label>
                  <label><span>密码</span><input name="password" type="password" autoComplete="new-password" placeholder={config.password_configured ? '已安全保存；留空表示不修改' : '输入后使用 Windows DPAPI 加密保存'} disabled={!config.vault_supported} /></label>
                  <label className="account-auth-check"><input name="allow_password_login" type="checkbox" defaultChecked={config.allow_password_login} /><span>允许在必要时使用账号密码恢复登录</span></label>
                  {config.password_configured && <label className="account-auth-check danger"><input name="clear_password" type="checkbox" /><span>清除已保存密码</span></label>}
                </section>

                <section className="account-auth-section">
                  <div className="account-auth-section-title"><div><strong>Cookie 登录</strong><span>{config.cookie_configured ? `已保存 ${config.cookie_count} 条平台 Cookie。` : '尚未配置 Cookie。'}</span></div></div>
                  <textarea name="cookie_json" rows={6} placeholder="粘贴 Cookie JSON；已保存内容不会再次显示" disabled={!config.vault_supported} />
                  <label className="account-auth-check"><input name="allow_cookie_restore" type="checkbox" defaultChecked={config.allow_cookie_restore} /><span>允许优先使用 Cookie 恢复登录</span></label>
                  {config.cookie_configured && <label className="account-auth-check danger"><input name="clear_cookies" type="checkbox" /><span>清除已保存 Cookie</span></label>}
                </section>

                <section className="account-auth-section">
                  <div className="account-auth-section-title"><div><strong>TOTP 二次验证</strong><span>仅处理你自己账号的 Authenticator Base32 密钥；短信、邮件、App 确认和安全检查仍转人工。</span></div></div>
                  <label><span>TOTP 密钥</span><input name="totp_secret" type="password" autoComplete="off" placeholder={config.totp_configured ? '已安全保存；留空表示不修改' : 'Base32 密钥'} disabled={!config.vault_supported} /></label>
                  <label className="account-auth-check"><input name="allow_totp" type="checkbox" defaultChecked={config.allow_totp} /><span>遇到标准 TOTP 验证时允许自动生成验证码</span></label>
                  {config.totp_configured && <label className="account-auth-check danger"><input name="clear_totp" type="checkbox" /><span>清除已保存 TOTP 密钥</span></label>}
                </section>

                <div className="account-auth-note">所有实际登录仍发生在该账号绑定的真实 iXBrowser 窗口中。安全检查、Checkpoint 和未知验证不会自动绕过。</div>
              </>
            )}
          </div>

          <footer className="account-auth-footer">
            <Button type="button" onClick={onClose} disabled={busy}>取消</Button>
            <Button type="submit" variant="primary" disabled={busy || !config}>{busy ? '保存中…' : '保存登录设置'}</Button>
          </footer>
        </form>
      </div>
    </div>
  )
}
