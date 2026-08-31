import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { AssetIcon, HomeIcon, PrepareIcon, ReviewIcon, RunIcon, SearchIcon, SendIcon } from '../ui/icons'

const actions = [
  { to: '/', label: '打开工作台', detail: '查看当前运行与待处理事项', icon: HomeIcon },
  { to: '/publish', label: '新建发布', detail: '选择内容、账号与发布时间', icon: SendIcon },
  { to: '/assets', label: '打开素材中心', detail: '管理文案、图片与视频', icon: AssetIcon },
  { to: '/accounts', label: '打开准备', detail: '浏览器环境、账号与渠道', icon: PrepareIcon },
  { to: '/tasks', label: '查看运行', detail: '查看执行中的任务与历史', icon: RunIcon },
  { to: '/review', label: '查看需要处理', detail: '检查待确认和失败任务', icon: ReviewIcon },
]

export default function CommandPalette() {
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen((value) => !value)
      }
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  useEffect(() => {
    setOpen(false)
    setQuery('')
  }, [location.pathname])

  useEffect(() => {
    if (!open) return
    requestAnimationFrame(() => inputRef.current?.focus())
  }, [open])

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return actions
    return actions.filter((item) => `${item.label} ${item.detail}`.toLowerCase().includes(keyword))
  }, [query])

  return (
    <>
      <button className="sp-command-trigger" type="button" onClick={() => setOpen(true)} aria-label="打开命令面板">
        <SearchIcon />
        <span>搜索环境、账号、内容、任务…</span>
        <kbd>Ctrl K</kbd>
      </button>

      {open && (
        <div className="sp-command-backdrop" onMouseDown={() => setOpen(false)}>
          <section className="sp-command-dialog" role="dialog" aria-modal="true" aria-label="命令面板" onMouseDown={(event) => event.stopPropagation()}>
            <div className="sp-command-search">
              <SearchIcon />
              <input ref={inputRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入操作或页面名称…" />
              <kbd>Esc</kbd>
            </div>
            <div className="sp-command-results">
              {filtered.length === 0 ? (
                <div className="sp-command-empty">没有匹配的操作</div>
              ) : filtered.map((item) => {
                const Icon = item.icon
                return (
                  <Link key={item.to + item.label} to={item.to} className="sp-command-result">
                    <span className="sp-command-result-icon"><Icon /></span>
                    <span><strong>{item.label}</strong><small>{item.detail}</small></span>
                  </Link>
                )
              })}
            </div>
          </section>
        </div>
      )}
    </>
  )
}
