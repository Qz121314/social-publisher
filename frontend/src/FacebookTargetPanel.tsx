import React, { useEffect, useMemo, useState } from 'react'

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

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `请求失败（HTTP ${response.status}）`
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // Keep the HTTP fallback.
    }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export default function FacebookTargetPanel() {
  const [profiles, setProfiles] = useState<BrowserProfile[]>([])
  const [targets, setTargets] = useState<PublishTarget[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  const targetByProfile = useMemo(
    () => new Map(targets.map((target) => [target.profile_id, target])),
    [targets],
  )

  const load = async () => {
    const [profileResponse, targetResponse] = await Promise.all([
      fetch('/api/browser-profiles'),
      fetch('/api/publish-targets?platform=facebook'),
    ])
    setProfiles(await readJson<BrowserProfile[]>(profileResponse))
    setTargets(await readJson<PublishTarget[]>(targetResponse))
  }

  useEffect(() => {
    load().catch((error: Error) => setMessage(error.message))
  }, [])

  const openProfile = async (profile: BrowserProfile) => {
    setBusyId(profile.profile_id)
    setMessage(null)
    try {
      await readJson(
        await fetch(`/api/browser-profiles/${profile.profile_id}/open`, { method: 'POST' }),
      )
      setMessage(`iX ${profile.name} 已打开。请在弹出的浏览器里进入正确的 Facebook 主页，然后回来点击“保存当前页”。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyId(null)
    }
  }

  const capture = async (profile: BrowserProfile, targetType: 'profile' | 'page') => {
    setBusyId(profile.profile_id)
    setMessage(null)
    try {
      const target = await readJson<PublishTarget>(
        await fetch(`/api/browser-profiles/${profile.profile_id}/facebook-target/capture`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_type: targetType }),
        }),
      )
      await load()
      setMessage(`iX ${profile.name} 的 Facebook 默认发布目标已设置为：${target.target_name}`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyId(null)
    }
  }

  const clearTarget = async (profile: BrowserProfile) => {
    if (!window.confirm(`确定清除 iX ${profile.name} 的 Facebook 默认发布目标吗？`)) return
    setBusyId(profile.profile_id)
    setMessage(null)
    try {
      const response = await fetch(`/api/browser-profiles/${profile.profile_id}/facebook-target`, {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error(`清除失败（HTTP ${response.status}）`)
      await load()
      setMessage(`iX ${profile.name} 的 Facebook 默认发布目标已清除。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyId(null)
    }
  }

  if (profiles.length === 0) return null

  return (
    <div className="target-shell">
      <section className="target-panel">
        <div className="target-heading">
          <div>
            <span className="target-kicker">Facebook 发布安全</span>
            <h2>每个 iX 的默认发布主页</h2>
            <p>先打开环境，在 iX 浏览器里进入正确的个人主页或公共主页，再回来保存当前页。发布前系统会再次校验目标，避免发错主页。</p>
          </div>
          <button className="target-refresh" onClick={() => load().catch((error: Error) => setMessage(error.message))}>
            刷新
          </button>
        </div>

        {message && <div className="target-notice">{message}</div>}

        <div className="target-list">
          {profiles.filter((profile) => profile.is_available).map((profile, index) => {
            const target = targetByProfile.get(profile.profile_id)
            const busy = busyId === profile.profile_id
            return (
              <div className="target-row" key={profile.profile_id}>
                <div className="target-profile">
                  <span className="target-index">{String(index + 1).padStart(3, '0')}</span>
                  <div>
                    <strong>{profile.name}</strong>
                    <small>iX #{profile.profile_id}{profile.group_name ? ` · ${profile.group_name}` : ''}</small>
                  </div>
                </div>

                <div className={`target-current ${target ? 'configured' : ''}`}>
                  {target ? (
                    <>
                      <strong>{target.target_name}</strong>
                      <small>{target.target_type === 'page' ? '公共主页' : '个人主页'} · {target.target_id}</small>
                      <a href={target.target_url} target="_blank" rel="noreferrer">查看目标</a>
                    </>
                  ) : (
                    <>
                      <strong>未设置默认主页</strong>
                      <small>未设置时 Facebook 发布任务不会执行</small>
                    </>
                  )}
                </div>

                <div className="target-actions">
                  <button disabled={busy} onClick={() => openProfile(profile)}>
                    {busy ? '处理中…' : '打开环境'}
                  </button>
                  <button disabled={busy} onClick={() => capture(profile, 'page')}>
                    保存当前页为公共主页
                  </button>
                  <button disabled={busy} onClick={() => capture(profile, 'profile')}>
                    保存当前页为个人主页
                  </button>
                  {target && (
                    <button className="target-danger" disabled={busy} onClick={() => clearTarget(profile)}>
                      清除
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </section>
    </div>
  )
}
