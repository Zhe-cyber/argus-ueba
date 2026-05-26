import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { fetchUsers, fetchStats } from '@/lib/api'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const RISK_FILTERS = ['All', 'High', 'Medium', 'Low']

const RISK_STYLE = {
  High:   { badge: 'bg-red-100 text-red-700 ring-1 ring-red-300',   dot: 'bg-red-500'   },
  Medium: { badge: 'bg-amber-100 text-amber-700 ring-1 ring-amber-300', dot: 'bg-amber-500' },
  Low:    { badge: 'bg-green-100 text-green-700 ring-1 ring-green-300', dot: 'bg-green-500' },
}

const STAT_STYLE = {
  total:  { bg: 'bg-slate-50',  border: 'border-slate-200', label: 'text-slate-500', value: 'text-slate-800', pct: 'text-slate-400' },
  High:   { bg: 'bg-red-50',    border: 'border-red-200',   label: 'text-red-500',   value: 'text-red-700',   pct: 'text-red-400'   },
  Medium: { bg: 'bg-amber-50',  border: 'border-amber-200', label: 'text-amber-500', value: 'text-amber-700', pct: 'text-amber-400' },
  Low:    { bg: 'bg-green-50',  border: 'border-green-200', label: 'text-green-500', value: 'text-green-700', pct: 'text-green-400' },
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Spinner() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-24 text-slate-400">
      <svg className="animate-spin h-8 w-8" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      <span className="text-sm font-medium">Loading user data…</span>
    </div>
  )
}

function ErrorBanner({ message, onRetry }) {
  return (
    <div className="mx-4 mt-6 rounded-lg border border-red-200 bg-red-50 p-4 flex items-start gap-3">
      <svg className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" clipRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zm-.75-11.25a.75.75 0 011.5 0v4.5a.75.75 0 01-1.5 0v-4.5zm.75 7.5a.75.75 0 100-1.5.75.75 0 000 1.5z" />
      </svg>
      <div className="flex-1">
        <p className="text-sm font-semibold text-red-700">Unable to reach the API</p>
        <p className="mt-0.5 text-sm text-red-600">{message}</p>
        <p className="mt-1 text-xs text-red-500">
          Make sure the backend is running at{' '}
          <code className="font-mono">{process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}</code>
        </p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex-shrink-0 rounded-md bg-red-100 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-200 transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  )
}

function StatCard({ label, count, pct, styleKey }) {
  const s = STAT_STYLE[styleKey]
  return (
    <div className={`rounded-xl border ${s.border} ${s.bg} px-5 py-4 flex flex-col gap-1 shadow-sm`}>
      <span className={`text-xs font-semibold uppercase tracking-wider ${s.label}`}>{label}</span>
      <span className={`text-3xl font-bold tabular-nums ${s.value}`}>{count.toLocaleString()}</span>
      {pct !== undefined && (
        <span className={`text-xs ${s.pct}`}>{pct}% of total</span>
      )}
    </div>
  )
}

function RiskBadge({ level }) {
  const s = RISK_STYLE[level] ?? RISK_STYLE.Low
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${s.badge}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {level}
    </span>
  )
}

function ScenarioLabel({ scenario }) {
  if (!scenario || scenario === 0) {
    return <span className="text-slate-400 text-sm">—</span>
  }
  return (
    <span className="inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 ring-1 ring-slate-200">
      Sc{scenario}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Dashboard() {
  const router = useRouter()

  const [stats, setStats]       = useState(null)
  const [users, setUsers]       = useState([])
  const [filter, setFilter]     = useState('All')
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)

  // ── Data fetching ──────────────────────────────────────────────────────

  const loadData = useCallback(async (activeFilter) => {
    setLoading(true)
    setError(null)
    try {
      const risk = activeFilter === 'All' ? null : activeFilter
      const [statsData, usersData] = await Promise.all([
        fetchStats(),
        fetchUsers(risk, 500),   // load up to 500; table handles display
      ])
      setStats(statsData)
      setUsers(usersData)
    } catch (err) {
      setError(err.message ?? 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData(filter)
  }, [filter, loadData])

  // ── Derived values ─────────────────────────────────────────────────────

  const total = stats?.total_users ?? 0
  const pct   = (n) => total ? Math.round((n / total) * 100) : 0

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <>
      <Head>
        <title>Argus — Analyst Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

        <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-6">

          {/* ── Stats bar ── */}
          {stats && (
            <section aria-label="Risk summary">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <StatCard
                  label="Total Users"
                  count={stats.total_users}
                  styleKey="total"
                />
                <StatCard
                  label="High Risk"
                  count={stats.high_risk}
                  pct={pct(stats.high_risk)}
                  styleKey="High"
                />
                <StatCard
                  label="Medium Risk"
                  count={stats.medium_risk}
                  pct={pct(stats.medium_risk)}
                  styleKey="Medium"
                />
                <StatCard
                  label="Low Risk"
                  count={stats.low_risk}
                  pct={pct(stats.low_risk)}
                  styleKey="Low"
                />
              </div>
            </section>
          )}

          {/* ── Filter bar + table card ── */}
          <section aria-label="User risk table">
            <div className="rounded-xl bg-white shadow-sm border border-slate-200 overflow-hidden">

              {/* Card header with filters */}
              <div className="px-5 py-4 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-slate-700">User Risk Overview</h2>
                  {!loading && !error && (
                    <p className="text-xs text-slate-400 mt-0.5">
                      {users.length.toLocaleString()} user{users.length !== 1 ? 's' : ''} shown
                      {filter !== 'All' ? ` · filtered to ${filter}` : ''}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-1.5 rounded-lg bg-slate-100 p-1" role="group" aria-label="Risk filter">
                  {RISK_FILTERS.map((f) => (
                    <button
                      key={f}
                      onClick={() => setFilter(f)}
                      className={[
                        'rounded-md px-3 py-1.5 text-xs font-semibold transition-all duration-150',
                        filter === f
                          ? 'bg-white text-slate-800 shadow-sm ring-1 ring-slate-200'
                          : 'text-slate-500 hover:text-slate-700',
                      ].join(' ')}
                    >
                      {f}
                    </button>
                  ))}
                </div>
              </div>

              {/* Content */}
              {error ? (
                <ErrorBanner message={error} onRetry={() => loadData(filter)} />
              ) : loading ? (
                <Spinner />
              ) : users.length === 0 ? (
                <div className="py-16 text-center text-sm text-slate-400">
                  No users found for this filter.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 bg-slate-50">
                        <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 w-8">
                          #
                        </th>
                        <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                          User ID
                        </th>
                        <th className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-wider text-slate-500">
                          Risk Score
                        </th>
                        <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                          Risk Level
                        </th>
                        <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                          Scenario
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((user, idx) => (
                        <tr
                          key={user.user}
                          onClick={() => router.push(`/users/${encodeURIComponent(user.user)}`)}
                          className={[
                            'border-b border-slate-50 cursor-pointer transition-colors',
                            'hover:bg-indigo-50 hover:border-indigo-100',
                            idx % 2 === 0 ? 'bg-white' : 'bg-slate-50/60',
                          ].join(' ')}
                        >
                          <td className="px-5 py-3.5 text-slate-300 text-xs tabular-nums">
                            {idx + 1}
                          </td>
                          <td className="px-5 py-3.5 font-mono text-slate-700 font-medium">
                            {user.user}
                          </td>
                          <td className="px-5 py-3.5 text-right">
                            <ScoreBar score={user.ae_score} risk={user.risk_level} />
                          </td>
                          <td className="px-5 py-3.5">
                            <RiskBadge level={user.risk_level} />
                          </td>
                          <td className="px-5 py-3.5">
                            <ScenarioLabel scenario={user.scenario} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>

        </main>
    </>
  )
}

// ---------------------------------------------------------------------------
// ScoreBar — numeric score + mini progress bar, inline in the table cell
// ---------------------------------------------------------------------------

function ScoreBar({ score, risk }) {
  const pct = Math.round(score * 100)

  const trackColor =
    risk === 'High'   ? 'bg-red-400'
    : risk === 'Medium' ? 'bg-amber-400'
    : 'bg-green-400'

  return (
    <div className="inline-flex flex-col items-end gap-1 min-w-[80px]">
      <span className="font-mono text-xs font-semibold text-slate-700 tabular-nums">
        {score.toFixed(3)}
      </span>
      <div className="w-full h-1 rounded-full bg-slate-100 overflow-hidden">
        <div
          className={`h-full rounded-full ${trackColor} transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
