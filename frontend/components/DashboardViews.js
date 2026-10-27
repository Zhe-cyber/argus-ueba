import Link from 'next/link'
import { useRouter } from 'next/router'
import { useEffect, useState } from 'react'
import { fetchStats } from '@/lib/api'

export default function DashboardViews() {
  const { pathname } = useRouter()
  const [stats, setStats] = useState(null)
  useEffect(() => { let active = true; fetchStats().then(s => { if (active) setStats(s) }).catch(() => {}); return () => { active = false } }, [])
  const connectedLabel = stats?.application_mode === 'live'
    ? `Connected sources — live${stats.scoring_status?.model_ready ? '' : ' (scoring pending)'}`
    : stats ? 'Existing dashboard — benchmark / demo' : 'Connected dashboard — checking mode'
  return (
    <nav aria-label="Dashboard data context" className="flex flex-col sm:flex-row gap-2 border-b border-slate-200 pb-3">
      {[['/', connectedLabel], ['/clue', 'CLUE benchmark replay — real model output']].map(([href, label]) => (
        <Link href={href} key={href} aria-current={pathname === href ? 'page' : undefined}
          className={`rounded-lg px-4 py-3 text-sm font-semibold ${pathname === href ? 'bg-indigo-700 text-white' : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50'}`}>
          {label}
        </Link>
      ))}
    </nav>
  )
}
