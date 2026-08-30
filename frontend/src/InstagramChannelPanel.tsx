import React, { useEffect, useMemo, useState } from 'react'

import { api } from './app/api'

type BrowserProfile = {
  profile_id: number
  name: string
  group_name?: string | null
  is_available: boolean
}

type PublishTarget = {
  id: number
  profile_id: number
  platform: string
  target_type: string
  target_id: string
  target_name: string
  target_url: string
}

export default function InstagramChannelPanel() {
  const [profiles, setProfiles] = useState<BrowserProfile[]>([])
  const [targets, setTargets] = useState<PublishTarget[]>([])
  const [busyId, setBusyId] = useState<number | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const targetByProfile = useMemo(
    () => new Map(targets.map((target) => [target.profile_id, target])),
    [targets],
  )

  const load = async () => {
    const [profileItems, targetItems] = await Promise.all([
      api<BrowserProfile[]>('/api/browser-profiles'),
      api<PublishTarget[]>('/api/publish-targets?platform=instagram'),
    ])
    setProfiles(profileItems)
    setTargets(targetItems)
  }

  useEffect(() => {
    load().catch((error) => setMessage(error instanceof Error ? error.message : String(error)))
  }, [])

  const openProfile = async (profile: BrowserProfile) => {
    setBusyId(profile.profile_id)
    setMessage(null)
    try {
      await api(`/api/browser-profiles/${profile.profile_id}/open`, { method: 'POST' })
      setMessage(`iX ${profile.name} 已打开。请在该窗口登录 Instagram；登录、安全验证必须人工完成。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyId(null)
    }
  }

  const capture = async (profile: BrowserProfile) => {
    setBusyId(profile.profile_id)
    setMessage(`正在识别 iX ${profile.name} 当前登录的 Instagram 账号…`)
    try {
      const target = await api<PublishTarget>(
        `/api/browser-profiles/${profile.profile_id}/instagram-channel/capture`,
        { method: 'POST' },
      )
      await load()
      setMessage(
        `Instagram Channel 已保存：@${target.target_name}。发布授权将校验稳定 ds_user_id，不依赖用户名字符串。`,
      )
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyId(null)
    }
  }

  const clearTarget = async (profile: BrowserProfile) => {
    if (!window.confirm(`确定清除 iX ${profile.name} 的 Instagram Channel？`)) return
    setBusyId(profile.profile_id)
    setMessage(null)
    try {
      await api(`/api/browser-profiles/${profile.profile_id}/instagram-channel`, { method: 'DELETE' })
      await load()
      setMessage(`iX ${profile.name} 的 Instagram Channel 已清除。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="v1-panel">
      <div className="v1-panel-heading">
        <div>
          <h2>Instagram Channel 配置</h2>
          <p>打开 iX → 人工登录 Instagram → 捕获当前账号。target_id 使用稳定 ds_user_id。</p>
        </div>
        <span className="v1-muted">Phase 8A · Feed Post</span>
      </div>

      {message && <div className="notice">{message}</div>}

      <div className="table-wrap">
        <table>
          <thead><tr><th>iX 环境</th><th>分组</th><th>当前 Instagram Channel</th><th>身份门禁</th><th>操作</th></tr></thead>
          <tbody>
            {profiles.length === 0 ? (
              <tr><td colSpan={5}><div className="empty-state compact-empty"><strong>暂无 iX 环境</strong><span>先同步 iXBrowser 环境。</span></div></td></tr>
            ) : profiles.map((profile) => {
              const target = targetByProfile.get(profile.profile_id)
              const busy = busyId === profile.profile_id
              return (
                <tr key={profile.profile_id}>
                  <td><strong>{profile.name}</strong><br /><small>#{profile.profile_id}</small></td>
                  <td>{profile.group_name || '未分组'}</td>
                  <td>{target ? <><strong>@{target.target_name}</strong><br /><small>{target.target_url}</small></> : <span className="v1-muted">未配置</span>}</td>
                  <td>{target ? <><strong>ds_user_id</strong><br /><small>{target.target_id}</small></> : '—'}</td>
                  <td>
                    <div className="v1-plan-actions">
                      <button type="button" className="compact-button" disabled={busy} onClick={() => openProfile(profile)}>打开 iX</button>
                      <button type="button" className="compact-button" disabled={busy || !profile.is_available} onClick={() => capture(profile)}>{busy ? '处理中…' : target ? '重新识别' : '捕获账号'}</button>
                      {target && <button type="button" className="compact-button danger-outline" disabled={busy} onClick={() => clearTarget(profile)}>清除</button>}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="v1-inline-note">如果 Instagram 出现登录、2FA、Challenge 或其他安全验证，系统不会绕过；请在 iXBrowser 中人工完成后再捕获或发布。</p>
    </section>
  )
}
