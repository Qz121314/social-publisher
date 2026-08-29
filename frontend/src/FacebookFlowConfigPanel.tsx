import React, { useEffect, useMemo, useState } from 'react'

type FlowConfig = {
  entry_keywords: string[]
  surface_titles: string[]
  media_keywords: string[]
  next_keywords: string[]
  post_keywords: string[]
  upload_busy_keywords: string[]
  success_keywords: string[]
}

type FlowResponse = {
  config: FlowConfig
  source: 'default' | 'runtime'
  runtime_path?: string
}

type FieldKey = keyof FlowConfig

type FieldDefinition = {
  key: FieldKey
  step: string
  title: string
  description: string
  placeholder: string
  tone: 'primary' | 'neutral' | 'warning' | 'success'
}

const fieldDefinitions: FieldDefinition[] = [
  {
    key: 'entry_keywords',
    step: '01',
    title: '发帖入口',
    description: '用于定位页面上的“分享新鲜事”等可见入口，并触发 Facebook Composer。',
    placeholder: '例如：分享新鲜事',
    tone: 'primary',
  },
  {
    key: 'surface_titles',
    step: '02',
    title: 'Composer 标题',
    description: '用于确认已经进入真实的“创建帖子 / 发帖”界面。',
    placeholder: '例如：创建帖子',
    tone: 'neutral',
  },
  {
    key: 'media_keywords',
    step: '03',
    title: '照片 / 视频',
    description: '需要上传图片或视频时，用这些关键词定位媒体入口。',
    placeholder: '例如：照片/视频',
    tone: 'neutral',
  },
  {
    key: 'next_keywords',
    step: '04',
    title: '流程推进',
    description: 'Facebook 出现分步发布时，识别“下一页 / 下一步 / 继续”等中间动作。',
    placeholder: '例如：下一页',
    tone: 'warning',
  },
  {
    key: 'post_keywords',
    step: '05',
    title: '最终发布',
    description: '只有当前 actor ID 与目标 ID 一致时，系统才允许点击这些最终发布动作。',
    placeholder: '例如：发帖',
    tone: 'primary',
  },
  {
    key: 'upload_busy_keywords',
    step: '06',
    title: '媒体处理中',
    description: '检测 Facebook 仍在上传或处理媒体，避免过早进入下一步。',
    placeholder: '例如：正在上传',
    tone: 'warning',
  },
  {
    key: 'success_keywords',
    step: '07',
    title: '发布成功',
    description: '发布动作完成后，用于辅助确认 Facebook 已接受帖子。',
    placeholder: '例如：帖子已发布',
    tone: 'success',
  },
]

function toTextarea(values: string[]) {
  return values.join('\n')
}

function fromTextarea(value: string) {
  const unique: string[] = []
  value.split(/\r?\n/).forEach((item) => {
    const normalized = item.trim().replace(/\s+/g, ' ')
    if (normalized && !unique.includes(normalized)) unique.push(normalized)
  })
  return unique
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`
    try {
      const body = await response.json()
      message = body.detail ?? message
    } catch {
      // Keep HTTP fallback.
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export default function FacebookFlowConfigPanel() {
  const [config, setConfig] = useState<FlowConfig | null>(null)
  const [initialConfig, setInitialConfig] = useState<FlowConfig | null>(null)
  const [source, setSource] = useState<'default' | 'runtime'>('default')
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = async () => {
    const result = await readJson<FlowResponse>(await fetch('/api/facebook-flow-config'))
    setConfig(result.config)
    setInitialConfig(result.config)
    setSource(result.source)
  }

  useEffect(() => {
    load().catch((error: Error) => setMessage(error.message))
  }, [])

  const dirty = useMemo(
    () => Boolean(config && initialConfig && JSON.stringify(config) !== JSON.stringify(initialConfig)),
    [config, initialConfig],
  )

  const keywordCount = useMemo(
    () => config ? Object.values(config).reduce((sum, values) => sum + values.length, 0) : 0,
    [config],
  )

  const updateField = (key: FieldKey, value: string) => {
    setConfig((current) => current ? { ...current, [key]: fromTextarea(value) } : current)
  }

  const save = async () => {
    if (!config) return
    for (const definition of fieldDefinitions) {
      if (config[definition.key].length === 0) {
        setMessage(`“${definition.title}”至少保留 1 个关键词。`)
        return
      }
    }

    setBusy(true)
    setMessage(null)
    try {
      const result = await readJson<FlowResponse>(
        await fetch('/api/facebook-flow-config', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(config),
        }),
      )
      setConfig(result.config)
      setInitialConfig(result.config)
      setSource('runtime')
      setMessage('Facebook 流程关键词已保存到本机，后续发布任务立即使用新配置。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const reset = async () => {
    if (!window.confirm('确定恢复 Facebook 默认流程关键词吗？本机自定义配置将被清除。')) return
    setBusy(true)
    setMessage(null)
    try {
      const result = await readJson<FlowResponse>(
        await fetch('/api/facebook-flow-config/reset', { method: 'POST' }),
      )
      setConfig(result.config)
      setInitialConfig(result.config)
      setSource('default')
      setMessage('已恢复系统默认 Facebook 流程关键词。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  if (!config) {
    return (
      <section className="flow-panel admin-panel">
        <div className="panel-loading">正在读取 Facebook 流程配置…</div>
      </section>
    )
  }

  return (
    <section className="flow-panel admin-panel">
      <div className="flow-header">
        <div>
          <div className="section-kicker">AUTOMATION FLOW</div>
          <h2>Facebook 流程关键词</h2>
          <p>
            页面动作由关键词驱动，执行器负责点击、输入、上传和状态推进。身份校验始终由 target ID / actor ID 强制控制，不能通过关键词配置绕过。
          </p>
        </div>
        <div className="flow-header-actions">
          <span className={`config-source ${source}`}>{source === 'runtime' ? '本机自定义' : '系统默认'}</span>
          <button className="secondary-button" type="button" onClick={reset} disabled={busy}>恢复默认</button>
          <button className="primary" type="button" onClick={save} disabled={busy || !dirty}>
            {busy ? '保存中…' : dirty ? '保存配置' : '已保存'}
          </button>
        </div>
      </div>

      {message && <div className="flow-notice" role="status">{message}</div>}

      <div className="flow-overview">
        <div className="flow-metric">
          <span>配置来源</span>
          <strong>{source === 'runtime' ? '本机运行时' : '代码默认值'}</strong>
          <small>本机配置不会被 GitHub 自动镜像覆盖</small>
        </div>
        <div className="flow-metric">
          <span>关键词总数</span>
          <strong>{keywordCount}</strong>
          <small>覆盖中文与英文 Facebook UI</small>
        </div>
        <div className="flow-metric safe">
          <span>安全门禁</span>
          <strong>Actor ID</strong>
          <small>最终发布前必须与 target ID 完全一致</small>
        </div>
      </div>

      <div className="flow-map" aria-label="Facebook 发布流程">
        <div className="flow-node locked">
          <span>安全</span>
          <strong>校验身份 ID</strong>
          <small>系统固定</small>
        </div>
        <div className="flow-arrow">→</div>
        <div className="flow-node"><span>01</span><strong>点击入口</strong><small>关键词</small></div>
        <div className="flow-arrow">→</div>
        <div className="flow-node locked"><span>02</span><strong>输入正文</strong><small>结构识别</small></div>
        <div className="flow-arrow">→</div>
        <div className="flow-node"><span>03</span><strong>上传媒体</strong><small>关键词</small></div>
        <div className="flow-arrow">→</div>
        <div className="flow-node"><span>04</span><strong>推进步骤</strong><small>关键词</small></div>
        <div className="flow-arrow">→</div>
        <div className="flow-node locked"><span>安全</span><strong>再次校验 ID</strong><small>系统固定</small></div>
        <div className="flow-arrow">→</div>
        <div className="flow-node final"><span>05</span><strong>最终发布</strong><small>关键词</small></div>
      </div>

      <div className="flow-grid">
        {fieldDefinitions.map((definition) => (
          <article className={`flow-field tone-${definition.tone}`} key={definition.key}>
            <div className="flow-field-head">
              <div className="step-index">{definition.step}</div>
              <div>
                <h3>{definition.title}</h3>
                <p>{definition.description}</p>
              </div>
              <span className="keyword-count">{config[definition.key].length} 个</span>
            </div>
            <textarea
              value={toTextarea(config[definition.key])}
              onChange={(event) => updateField(definition.key, event.target.value)}
              placeholder={definition.placeholder}
              spellCheck={false}
              aria-label={`${definition.title}关键词，一行一个`}
            />
            <div className="field-hint">一行一个关键词 · 自动去重 · 最多 50 个</div>
          </article>
        ))}
      </div>

      <div className="flow-footer-note">
        <strong>配置原则</strong>
        <span>只配置 Facebook 页面上真实可见的文字。不要把账号名、主页名或随机内容加入流程关键词。</span>
      </div>
    </section>
  )
}
