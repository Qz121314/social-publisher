import React from 'react'
import { NavLink } from 'react-router-dom'

const items = [
  { to: '/prepare', label: '概览', end: true },
  { to: '/prepare/environments', label: '浏览器环境' },
  { to: '/prepare/network', label: '网络 / IP' },
  { to: '/prepare/accounts', label: '社交账号' },
  { to: '/assets', label: '素材中心' },
  { to: '/flows', label: '自动化流程' },
]

export default function PrepareNav() {
  return (
    <nav className="prepare-subnav" aria-label="准备工作区导航">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => `prepare-subnav-item ${isActive ? 'is-active' : ''}`}
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}
