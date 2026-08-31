import React from 'react'
import { NavLink } from 'react-router-dom'

const items = [
  { to: '/prepare', label: '概览', end: true },
  { to: '/prepare/proxies', label: 'IP池' },
  { to: '/prepare/accounts', label: '账号池' },
  { to: '/assets', label: '素材池' },
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
