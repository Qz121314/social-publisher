import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { AccountIcon, AssetIcon, BrowserIcon, HomeIcon, NetworkIcon, PrepareIcon, ReviewIcon, RunIcon, SearchIcon, SendIcon } from '../ui/icons'

const actions = [
  { to: '/', label: '打开工作台', detail: '查看当前运行与待处理事项', icon: HomeIcon },
  { to: '/publish', label: '新建发布', detail: '选择内容、账号分组与发布时间', icon: SendIcon },
  { to: '/prepare', label: '打开准备', detail: '查看 IP池、账号池、素材池和流程', icon: PrepareIcon },
  { to: '/prepare/proxies', label: '打开 IP池', detail: '批量导入和管理 SOCKS5', icon: NetworkIcon },
  { to: '/prepare/accounts', label: '打开账号池', detail: '批量导入账号、分组和分配 IP', icon: AccountIcon },
  { to: '/assets', label: '打开素材池', detail: '管理文案、图片、视频与内容组合', icon: AssetIcon },
  { to: '/prepare/environments', label: '高级：浏览器环境', detail: '查看 iXBrowser Profile 与会话诊断', icon: BrowserIcon },
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
        <span>搜索账号、IP、素材、任务…</span>
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
