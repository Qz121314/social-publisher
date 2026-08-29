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

type TargetCandidate = {
  id: number
  profile_id: number
  platform: string
  target_type: 'profile' | 'page'
  target_id: string
  target_name: string
  target_url: string
  source: string
  is_available: boolean
}

type ScanResult = {
  profile_id: number
  count: number
  items: TargetCandidate[]
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

function targetTypeLabel(value: string) {
  return value === 'profile' ? '个人主页' : '公共主页'
}

export default function FacebookTargetPanel() {
  const [profiles, setProfiles] = useState<BrowserProfile[]>([])
  const [targets, setTargets] = useState<PublishTarget[]>([])
  const [candidates, setCandidates] = useState<TargetCandidate[]>([])
  const [selectedCandidate, setSelectedCandidate] = useState<Record<number, number>>({})
  const [message, setMessage] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  const targetByProfile = useMemo(
    () => new Map(targets.map((target) => [target.profile_id, target])),
    [targets],
  )

  const candidatesByProfile = useMemo(() => {
    const result = new Map<number, TargetCandidate[]>()
    candidates.forEach((candidate) => {
      const list = result.get(candidate.profile_id) ?? []
      list.push(candidate)
      result.set(candidate.profile_id, list)
    })
    return result
  }, [candidates])

  const load = async () => {
    const [profileResponse, targetResponse, candidateResponse] = await Promise.all([
      fetch('/api/browser-profiles'),
      fetch('/api/publish-targets?platform=facebook'),
      fetch('/api/facebook-page-candidates'),
    ])
    const loadedProfiles = await readJson<BrowserProfile[]>(profileResponse)
    const loadedTargets = await readJson<PublishTarget[]>(targetResponse)
    const loadedCandidates = await readJson<TargetCandidate[]>(candidateResponse)
    setProfiles(loadedProfiles)
    setTargets(loadedTargets)
    setCandidates(loadedCandidates)

    setSelectedCandidate((current) => {
      const next = { ...current }
      loadedProfiles.forEach((profile) => {
        const availableTargets = loadedCandidates.filter((item) => item.profile_id === profile.profile_id)
        if (availableTargets.length === 0) {
          delete next[profile.profile_id]
          return
        }
        const currentTarget = loadedTargets.find((item) => item.profile_id === profile.profile_id)
        const targetMatch = currentTarget
          ? availableTargets.find((item) => item.target_id === currentTarget.target_id)
          : undefined
        const selectedStillExists = availableTargets.some((item) => item.id === next[profile.profile_id])
        if (!selectedStillExists) {
          next[profile.profile_id] = targetMatch?.id ?? availableTargets[0].id
        }
      })
      return next
    })
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
      setMessage(`iX ${profile.name} 已打开。需要登录或处理 Facebook 验证时，可以在这个窗口里人工完成。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyId(null)
    }
  }

  const scanTargets = async (profile: BrowserProfile) => {
    setBusyId(profile.profile_id)
    setMessage(`正在扫描 iX ${profile.name} 的 Facebook 个人主页和公共主页…`)
    try {
      const result = await readJson<ScanResult>(
        await fetch(`/api/browser-profiles/${profile.profile_id}/facebook-pages/scan`, {
          method: 'POST',
        }),
      )
      await load()
      if (result.items.length > 0) {
        const currentTarget = targetByProfile.get(profile.profile_id)
        const targetMatch = currentTarget
          ? result.items.find((item) => item.target_id === currentTarget.target_id)
          : undefined
        setSelectedCandidate((current) => ({
          ...current,
          [profile.profile_id]: targetMatch?.id ?? result.items[0].id,
        }))
      }
      const personalCount = result.items.filter((item) => item.target_type === 'profile').length
      const pageCount = result.items.filter((item) => item.target_type === 'page').length
      setMessage(`iX ${profile.name} 扫描完成：个人主页 ${personalCount} 个，公共主页 ${pageCount} 个。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyId(null)
    }
  }

  const setDefault = async (profile: BrowserProfile) => {
    const candidateId = selectedCandidate[profile.profile_id]
    if (!candidateId) {
      setMessage(`请先扫描 iX ${profile.name}，并选择一个 Facebook 个人主页或公共主页。`)
      return
    }

    setBusyId(profile.profile_id)
    setMessage(null)
    try {
      const target = await readJson<PublishTarget>(
        await fetch(
          `/api/browser-profiles/${profile.profile_id}/facebook-target/select/${candidateId}`,
          { method: 'POST' },
        ),
      )
      await load()
      setMessage(`iX ${profile.name} 的默认 Facebook 发布主页已设置为：${target.target_name}`)
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
            <p>系统只扫描两类真实发布身份：当前 Facebook 账号的个人主页，以及该账号可管理的公共主页。创建帖子、广告中心、消息等功能入口会被过滤。扫描结果不会自动改变发布目标，必须由你明确选择并设为默认。</p>
          </div>
          <button className="target-refresh" onClick={() => load().catch((error: Error) => setMessage(error.message))}>
            刷新
          </button>
        </div>

        {message && <div className="target-notice">{message}</div>}

        <div className="target-list">
          {profiles.filter((profile) => profile.is_available).map((profile, index) => {
            const target = targetByProfile.get(profile.profile_id)
            const availableTargets = candidatesByProfile.get(profile.profile_id) ?? []
            const busy = busyId === profile.profile_id
            const selectedId = selectedCandidate[profile.profile_id] ?? 0
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
                      <span className="target-label">当前默认</span>
                      <strong>{target.target_name}</strong>
                      <small>{targetTypeLabel(target.target_type)} · {target.target_id}</small>
                      <a href={target.target_url} target="_blank" rel="noreferrer">查看目标</a>
                    </>
                  ) : (
                    <>
                      <span className="target-label">当前默认</span>
                      <strong>未设置</strong>
                      <small>未设置时 Facebook 发布任务不会执行</small>
                    </>
                  )}
                </div>

                <div className="target-discovery">
                  <div className="target-discovery-head">
                    <strong>扫描到的发布主页</strong>
                    <span>{availableTargets.length > 0 ? `${availableTargets.length} 个` : '尚未扫描'}</span>
                  </div>
                  <select
                    value={selectedId || ''}
                    disabled={busy || availableTargets.length === 0}
                    onChange={(event) => setSelectedCandidate((current) => ({
                      ...current,
                      [profile.profile_id]: Number(event.target.value),
                    }))}
                  >
                    {availableTargets.length === 0 && <option value="">请先扫描发布主页</option>}
                    {availableTargets.map((candidate) => (
                      <option key={candidate.id} value={candidate.id}>
                        {targetTypeLabel(candidate.target_type)} · {candidate.target_name} · {candidate.target_id}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="target-actions">
                  <button disabled={busy} onClick={() => scanTargets(profile)}>
                    {busy ? '处理中…' : '扫描发布主页'}
                  </button>
                  <button className="target-primary" disabled={busy || availableTargets.length === 0} onClick={() => setDefault(profile)}>
                    设为默认
                  </button>
                  <button disabled={busy} onClick={() => openProfile(profile)}>
                    打开环境
                  </button>
                  {target && (
                    <button className="target-danger" disabled={busy} onClick={() => clearTarget(profile)}>
                      清除默认
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
