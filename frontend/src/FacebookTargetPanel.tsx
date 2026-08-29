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

type TargetConfirmation = {
  id: number
  profile_id: number
  platform: string
  target_id: string
  actor_id: string
  entry_signature_json: string
  confirmed_at: string
  updated_at: string
}

type ScanResult = {
  profile_id: number
  count: number
  items: TargetCandidate[]
}

type ConfirmResult = {
  profile_id: number
  target_id: string
  target_name: string
  confirmed: boolean
  actor_id: string
  editor_confirmed: boolean
  post_button_confirmed: boolean
  next_button_confirmed?: boolean
  primary_action?: string
  confirmed_at: string
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

function confirmationKey(profileId: number, targetId: string) {
  return `${profileId}:${targetId}`
}

export default function FacebookTargetPanel() {
  const [profiles, setProfiles] = useState<BrowserProfile[]>([])
  const [targets, setTargets] = useState<PublishTarget[]>([])
  const [candidates, setCandidates] = useState<TargetCandidate[]>([])
  const [confirmations, setConfirmations] = useState<TargetConfirmation[]>([])
  const [selectedCandidate, setSelectedCandidate] = useState<Record<number, number>>({})
  const [message, setMessage] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

  const targetByProfile = useMemo(
    () => new Map(targets.map((target) => [target.profile_id, target])),
    [targets],
  )

  const confirmationByTarget = useMemo(
    () => new Map(
      confirmations.map((item) => [confirmationKey(item.profile_id, item.target_id), item]),
    ),
    [confirmations],
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
    const [profileResponse, targetResponse, candidateResponse, confirmationResponse] = await Promise.all([
      fetch('/api/browser-profiles'),
      fetch('/api/publish-targets?platform=facebook'),
      fetch('/api/facebook-page-candidates'),
      fetch('/api/facebook-target-confirmations'),
    ])
    const loadedProfiles = await readJson<BrowserProfile[]>(profileResponse)
    const loadedTargets = await readJson<PublishTarget[]>(targetResponse)
    const loadedCandidates = await readJson<TargetCandidate[]>(candidateResponse)
    const loadedConfirmations = await readJson<TargetConfirmation[]>(confirmationResponse)
    setProfiles(loadedProfiles)
    setTargets(loadedTargets)
    setCandidates(loadedCandidates)
    setConfirmations(loadedConfirmations)

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
      setMessage(`iX ${profile.name} 已打开。需要登录或处理 Facebook 验证时，可直接在这个窗口中人工完成。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyId(null)
    }
  }

  const scanTargets = async (profile: BrowserProfile) => {
    setBusyId(profile.profile_id)
    setMessage(`正在扫描 iX ${profile.name} 的 Facebook 发布身份…`)
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
      setMessage(`iX ${profile.name} 扫描完成：发现 ${result.items.length} 个可用 Facebook 发布身份。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyId(null)
    }
  }

  const setDefault = async (profile: BrowserProfile) => {
    const candidateId = selectedCandidate[profile.profile_id]
    if (!candidateId) {
      setMessage(`请先扫描 iX ${profile.name}，并选择一个 Facebook 发布身份。`)
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
      setMessage(`iX ${profile.name} 的默认发布目标已设置为：${target.target_name}。发布时系统会强制校验 actor ID；如页面结构异常可运行“诊断发帖界面”。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyId(null)
    }
  }

  const confirmComposer = async (profile: BrowserProfile) => {
    const target = targetByProfile.get(profile.profile_id)
    if (!target) {
      setMessage(`iX ${profile.name} 尚未设置 Facebook 默认发布目标。`)
      return
    }

    setBusyId(profile.profile_id)
    setMessage(`正在诊断 iX ${profile.name} / ${target.target_name} 的 Facebook 发帖界面。不会输入内容，也不会点击最终发布…`)
    try {
      const result = await readJson<ConfirmResult>(
        await fetch(`/api/browser-profiles/${profile.profile_id}/facebook-composer/confirm`, {
          method: 'POST',
        }),
      )
      await load()
      const actionLabel = result.primary_action === 'next' ? '下一步' : '最终发布'
      setMessage(`发帖界面诊断成功：目标 ID ${result.target_id}，当前身份 ID ${result.actor_id}，编辑器和“${actionLabel}”动作均已识别。`)
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
            <span className="target-kicker">FACEBOOK TARGETS</span>
            <h2>Facebook 发布目标</h2>
            <p>个人主页和公共主页统一视为“发布身份”。页面名称只用于显示和导航，真正的发布门禁始终是 target ID：当前 Facebook actor ID 必须与目标 ID 完全一致。</p>
          </div>
          <button className="target-refresh" onClick={() => load().catch((error: Error) => setMessage(error.message))}>
            刷新数据
          </button>
        </div>

        {message && <div className="target-notice">{message}</div>}

        <div className="target-list">
          {profiles.filter((profile) => profile.is_available).map((profile, index) => {
            const target = targetByProfile.get(profile.profile_id)
            const confirmation = target
              ? confirmationByTarget.get(confirmationKey(profile.profile_id, target.target_id))
              : undefined
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
                      <small>{targetTypeLabel(target.target_type)} · ID {target.target_id}</small>
                      <small className={confirmation ? 'target-confirmed' : 'target-unconfirmed'}>
                        发帖界面：{confirmation ? '已诊断' : '未诊断'}
                      </small>
                      <a href={target.target_url} target="_blank" rel="noreferrer">查看目标</a>
                    </>
                  ) : (
                    <>
                      <span className="target-label">当前默认</span>
                      <strong>未设置</strong>
                      <small>未设置目标时 Facebook 发布任务不会执行</small>
                    </>
                  )}
                </div>

                <div className="target-discovery">
                  <div className="target-discovery-head">
                    <strong>扫描到的发布身份</strong>
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
                    {availableTargets.length === 0 && <option value="">请先扫描发布身份</option>}
                    {availableTargets.map((candidate) => (
                      <option key={candidate.id} value={candidate.id}>
                        {targetTypeLabel(candidate.target_type)} · {candidate.target_name} · {candidate.target_id}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="target-actions">
                  <button disabled={busy} onClick={() => scanTargets(profile)}>
                    {busy ? '处理中…' : '扫描发布身份'}
                  </button>
                  <button className="target-primary" disabled={busy || availableTargets.length === 0} onClick={() => setDefault(profile)}>
                    设为默认
                  </button>
                  {target && (
                    <button className="target-confirm" disabled={busy} onClick={() => confirmComposer(profile)}>
                      {confirmation ? '重新诊断' : '诊断发帖界面'}
                    </button>
                  )}
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
