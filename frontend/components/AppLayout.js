/**
 * AppLayout.js — Shared navigation + layout wrapper for all Argus pages.
 *
 * Provides:
 *  - Sticky top nav bar with logo, page links, live pulse indicator
 *  - Red badge on Alerts nav item showing open alert count (polls /alerts/summary every 15s)
 *  - Common bg-slate-100 background and footer
 */

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/router'

// ---------------------------------------------------------------------------
// Nav config
// ---------------------------------------------------------------------------

const NAV = [
  {
    href: '/',
    label: 'Dashboard',
    exact: true,
    icon: (
      <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
        <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zm6-4a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zm6-3a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" />
      </svg>
    ),
  },
  {
    href: '/alerts',
    label: 'Alerts',
    exact: false,
    badge: true,
    icon: (
      <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
        <path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zM10 18a3 3 0 01-3-3h6a3 3 0 01-3 3z" />
      </svg>
    ),
  },
  {
    href: '/investigations',
    label: 'Investigations',
    exact: false,
    icon: (
      <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" clipRule="evenodd"
          d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116
             7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1
             0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" />
      </svg>
    ),
  },
  {
    href: '/demo',
    label: 'Demo Lab',
    exact: false,
    icon: (
      <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" clipRule="evenodd"
          d="M7 2a1 1 0 00-.707 1.707L7 4.414v3.758a1 1 0 01-.293.707l-4
             4C.817 14.769 2.156 18 4.828 18h10.343c2.673 0
             4.012-3.231 2.122-5.121l-4-4A1 1 0 0113 8.172V4.414l.707-.707A1
             1 0 0013 2H7zm2 6.172V4h2v4.172a3 3 0 00.879 2.12l1.027
             1.028a4 4 0 00-2.171.102l-.47.156a4 4 0 01-2.53 0l-.563-.187a1.993
             1.993 0 00-.114-.035l1.063-1.063A3 3 0 009 8.172z" />
      </svg>
    ),
  },
]

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AppLayout({ children }) {
  const router = useRouter()
  const [openAlerts, setOpenAlerts] = useState(0)

  const pollAlerts = useCallback(async () => {
    try {
      const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const res = await fetch(`${API}/alerts/summary`)
      if (res.ok) {
        const data = await res.json()
        setOpenAlerts(data.open ?? 0)
      }
    } catch {
      // ignore — backend may not be running
    }
  }, [])

  useEffect(() => {
    pollAlerts()
    const id = setInterval(pollAlerts, 15_000)
    return () => clearInterval(id)
  }, [pollAlerts])

  return (
    <div className="min-h-screen bg-slate-100 font-sans flex flex-col">

      {/* ── Top nav bar ── */}
      <header className="bg-slate-900 shadow-md sticky top-0 z-40">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between gap-4">

          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 group flex-shrink-0">
            <svg className="h-6 w-6 text-indigo-400 group-hover:text-indigo-300 transition-colors"
              viewBox="0 0 24 24" fill="currentColor">
              <path fillRule="evenodd" clipRule="evenodd"
                d="M12 1.5l8.485 3.182A1 1 0 0121 5.62v5.38c0 4.418-3.582 8.49-9
                   9.38C6.582 19.49 3 15.418 3 11V5.62a1 1 0 01.515-.938L12 1.5z" />
            </svg>
            <div className="hidden sm:block leading-none">
              <p className="text-sm font-bold text-white">Argus</p>
              <p className="text-[9px] text-slate-500 mt-0.5">UEBA Platform</p>
            </div>
          </Link>

          {/* Nav links */}
          <nav className="flex items-center gap-0.5">
            {NAV.map(({ href, label, exact, badge, icon }) => {
              const active = exact
                ? router.pathname === href
                : router.pathname.startsWith(href)
              return (
                <Link
                  key={href}
                  href={href}
                  className={[
                    'relative flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition-all',
                    active
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-400 hover:text-white hover:bg-slate-800',
                  ].join(' ')}
                >
                  {icon}
                  <span className="hidden sm:inline">{label}</span>
                  {badge && openAlerts > 0 && (
                    <span className="absolute -top-1 -right-1 flex h-4 min-w-[16px] items-center
                                     justify-center rounded-full bg-red-500 px-1
                                     text-[9px] font-bold text-white leading-none">
                      {openAlerts > 99 ? '99+' : openAlerts}
                    </span>
                  )}
                </Link>
              )
            })}
          </nav>

          {/* Live indicator */}
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <span className="text-xs text-emerald-500 font-medium hidden sm:inline">Live</span>
          </div>

        </div>
      </header>

      {/* ── Page content ── */}
      <div className="flex-1">
        {children}
      </div>

      {/* ── Footer ── */}
      <footer className="mt-6 pb-6 text-center text-xs text-slate-400">
        Argus · Multi-Cloud UEBA Platform
      </footer>

    </div>
  )
}
