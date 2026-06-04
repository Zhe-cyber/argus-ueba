import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { fetchUsers, fetchStats } from '@/lib/api'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE      = 50
const RISK_FILTERS   = ['All', 'High', 'Medium', 'Low']
const SOURCE_FILTERS = ['All', 'CERT', 'Cloud']

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

function SourceBadge({ source }) {
  if (source === 'cloud') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700 ring-1 ring-indigo-200">
        <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
        Cloud
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600 ring-1 ring-slate-200">
      <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
      CERT
    </span>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Dashboard() {
  const router = useRouter()

  const [stats, setStats]               = useState(null)
  const [users, setUsers]               = useState([])
  const [total, setTotal]               = useState(0)
  const [filter, setFilter]             = useState('All')
  const [sourceFilter, setSourceFilter] = useState('All')
  const [searchInput, setSearchInput]   = useState('')
  const [query, setQuery]               = useState('')
  const [offset, setOffset]             = useState(0)
  const [loading, setLoading]           = useState(true)
  const [error, setError]               = useState(null)

  const sourceParam =
    sourceFilter === 'All' ? 'all' : sourceFilter === 'Cloud' ? 'cloud' : 'cert'

  // ── Load aggregate stats once (it is the slowest call) ──────────────────
  useEffect(() => {
    fetchStats().then(setStats).catch(() => { /* badge degrades gracefully */ })
  }, [])

  // ── Debounce the search box into the query that drives fetching ─────────
  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(searchInput.trim())
      setOffset(0)
    }, 300)
    return () => clearTimeout(t)
  }, [searchInput])

  // ── Reset to first page whenever a filter changes ───────────────────────
  useEffect(() => { setOffset(0) }, [filter, sourceFilter])

  // ── Fetch the current page of users (server-side filter/search/sort) ────
  const loadUsers = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const risk = filter === 'All' ? null : filter
      const data = await fetchUsers({
        risk, source: sourceParam, q: query, limit: PAGE_SIZE, offset,
      })
      setUsers(data.users ?? [])
      setTotal(data.total ?? 0)
    } catch (err) {
      setError(err.message ?? 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [filter, sourceParam, query, offset])

  useEffect(() => { loadUsers() }, [loadUsers])

  // ── Derived values ─────────────────────────────────────────────────────
  const totalUsers = stats?.total_users ?? 0
  const pct = (n) => totalUsers ? Math.round((n / totalUsers) * 100) : 0

  const from    = total === 0 ? 0 : offset + 1
  const to      = Math.min(offset + PAGE_SIZE, total)
  const canPrev = offset > 0
  const canNext = offset + PAGE_SIZE < total
  const filtered = filter !== 'All' || sourceFilter !== 'All' || query !== ''

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
                <StatCard label="Total Users" count={stats.total_users} styleKey="total" />
                <StatCard label="High Risk"   count={stats.high_risk}   pct={pct(stats.high_risk)}   styleKey="High" />
                <StatCard label="Medium Risk" count={stats.medium_risk} pct={pct(stats.medium_risk)} styleKey="Medium" />
                <StatCard label="Low Risk"    count={stats.low_risk}    pct={pct(stats.low_risk)}    styleKey="Low" />
              </div>
            </section>
          )}

          {/* ── Filter bar + table card ── */}
          <section aria-label="User risk table">
            <div className="rounded-xl bg-white shadow-sm border border-slate-200 overflow-hidden">

              {/* Card header with search + filters */}
              <div className="px-5 py-4 border-b border-slate-100 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-slate-700">
                    {filtered ? 'User Risk Overview' : `Top ${PAGE_SIZE} Highest-Risk Users`}
                  </h2>
                  {!loading && !error && (
                    <p className="text-xs text-slate-400 mt-0.5">
                      {total > 0
                        ? <>Showing <span className="tabular-nums">{from.toLocaleString()}–{to.toLocaleString()}</span> of <span className="tabular-nums">{total.toLocaleString()}</span></>
                        : 'No matching users'}
                      {filter !== 'All' ? ` · ${filter} risk` : ''}
                      {sourceFilter !== 'All' ? ` · ${sourceFilter}` : ''}
                      {query ? ` · “${query}”` : ''}
                    </p>
                  )}
                </div>

                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                  {/* Search box */}
                  <div className="relative">
                    <svg className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" clipRule="evenodd" d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z" />
                    </svg>
                    <input
                      type="text"
                      value={searchInput}
                      onChange={(e) => setSearchInput(e.target.value)}
                      placeholder="Search user ID…"
                      className="w-full sm:w-52 rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-7 py-1.5 text-sm text-slate-700 placeholder:text-slate-400 focus:bg-white focus:border-indigo-300 focus:outline-none focus:ring-1 focus:ring-indigo-200"
                    />
                    {searchInput && (
                      <button
                        onClick={() => setSearchInput('')}
                        aria-label="Clear search"
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                      >
                        ×
                      </button>
                    )}
                  </div>

                  {/* Source filter */}
                  <div className="flex items-center gap-1 rounded-lg bg-slate-100 p-1" role="group" aria-label="Source filter">
                    {SOURCE_FILTERS.map((s) => (
                      <button
                        key={s}
                        onClick={() => setSourceFilter(s)}
                        className={[
                          'rounded-md px-2.5 py-1 text-xs font-semibold transition-all duration-150',
                          sourceFilter === s
                            ? s === 'Cloud'
                              ? 'bg-indigo-600 text-white shadow-sm'
                              : 'bg-white text-slate-800 shadow-sm ring-1 ring-slate-200'
                            : 'text-slate-500 hover:text-slate-700',
                        ].join(' ')}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                  {/* Risk filter */}
                  <div className="flex items-center gap-1 rounded-lg bg-slate-100 p-1" role="group" aria-label="Risk filter">
                    {RISK_FILTERS.map((f) => (
                      <button
                        key={f}
                        onClick={() => setFilter(f)}
                        className={[
                          'rounded-md px-2.5 py-1 text-xs font-semibold transition-all duration-150',
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
              </div>

              {/* Content */}
              {error ? (
                <ErrorBanner message={error} onRetry={loadUsers} />
              ) : loading ? (
                <Spinner />
              ) : users.length === 0 ? (
                <div className="py-16 text-center text-sm text-slate-400">
                  No users found for this filter.
                </div>
              ) : (
                <>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-slate-100 bg-slate-50">
                          <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 w-12">#</th>
                          <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">User ID</th>
                          <th className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-wider text-slate-500"
                              title="Raw autoencoder reconstruction error. Scale differs by detector (CERT vs Cloud), so compare by Risk Level, not raw score.">
                            Risk Score
                          </th>
                          <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500"
                              title="Calibrated per detector — CERT High threshold ≈ 0.066, Cloud High ≈ 0.70. This is the comparable signal across sources.">
                            Risk Level
                          </th>
                          <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">Source</th>
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
                              {offset + idx + 1}
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
                              <SourceBadge source={user.data_source} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Pagination footer */}
                  <div className="flex items-center justify-between gap-3 px-5 py-3 border-t border-slate-100 bg-slate-50/40">
                    <span className="text-xs text-slate-400 tabular-nums">
                      Showing {from.toLocaleString()}–{to.toLocaleString()} of {total.toLocaleString()}
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                        disabled={!canPrev}
                        className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        ← Prev
                      </button>
                      <button
                        onClick={() => setOffset((o) => o + PAGE_SIZE)}
                        disabled={!canNext}
                        className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        Next →
                      </button>
                    </div>
                  </div>
                </>
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
