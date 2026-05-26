import { useEffect, useState, useCallback } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import { fetchAlerts, fetchAlertStats, updateAlertStatus } from '@/lib/api'

// ---------------------------------------------------------------------------
// Style maps
// ---------------------------------------------------------------------------

const SEV_STYLE = {
  Critical: { bg: 'bg-red-100',    text: 'text-red-700',    ring: 'ring-red-300',    dot: 'bg-red-500',    bar: 'bg-red-500'    },
  High:     { bg: 'bg-orange-100', text: 'text-orange-700', ring: 'ring-orange-300', dot: 'bg-orange-500', bar: 'bg-orange-500' },
  Medium:   { bg: 'bg-amber-100',  text: 'text-amber-700',  ring: 'ring-amber-300',  dot: 'bg-amber-500',  bar: 'bg-amber-500'  },
  Low:      { bg: 'bg-slate-100',  text: 'text-slate-600',  ring: 'ring-slate-300',  dot: 'bg-slate-400',  bar: 'bg-slate-400'  },
}

const STATUS_STYLE = {
  'Open':           { bg: 'bg-red-50',    text: 'text-red-700',    ring: 'ring-red-200'    },
  'Acknowledged':   { bg: 'bg-amber-50',  text: 'text-amber-700',  ring: 'ring-amber-200'  },
  'Resolved':       { bg: 'bg-green-50',  text: 'text-green-700',  ring: 'ring-green-200'  },
  'False Positive': { bg: 'bg-slate-50',  text: 'text-slate-500',  ring: 'ring-slate-200'  },
}

const TYPE_LABELS = {
  rarity_spike:       'Rarity Spike',
  ae_critical:        'AE Anomaly',
  anomalous_behavior: 'Anomalous Behavior',
  new_user:           'New User',
}

const STATUS_FILTERS = ['All', 'Open', 'Acknowledged', 'Resolved', 'False Positive']

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(isoStr) {
  const diff = Date.now() - new Date(isoStr).getTime()
  const m = Math.floor(diff / 60_000)
  if (m < 1)  return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SeverityBadge({ severity }) {
  const s = SEV_STYLE[severity] ?? SEV_STYLE.Low
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold ring-1
                      ${s.bg} ${s.text} ${s.ring}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {severity}
    </span>
  )
}

function StatusPill({ status }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE['Open']
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-semibold ring-1
                      ${s.bg} ${s.text} ${s.ring}`}>
      {status}
    </span>
  )
}

function TypeChip({ type }) {
  return (
    <span className="inline-flex items-center rounded-md bg-indigo-50 px-2 py-0.5
                     text-[10px] font-semibold text-indigo-600 ring-1 ring-indigo-200">
      {TYPE_LABELS[type] ?? type}
    </span>
  )
}

function StatCard({ label, count, color, bg }) {
  return (
    <div className={`rounded-xl border px-5 py-4 shadow-sm ${bg}`}>
      <p className={`text-xs font-semibold uppercase tracking-wider ${color} opacity-70`}>{label}</p>
      <p className={`text-3xl font-bold tabular-nums mt-1 ${color}`}>{count.toLocaleString()}</p>
    </div>
  )
}

function AlertRow({ alert, onUserClick, onStatusUpdate, updating }) {
  const sev = SEV_STYLE[alert.severity] ?? SEV_STYLE.Low

  // Status → available next actions
  const actions = []
  if (alert.status === 'Open') {
    actions.push({ label: 'Acknowledge', next: 'Acknowledged', style: 'bg-amber-500 hover:bg-amber-600 text-white' })
    actions.push({ label: 'Resolve',     next: 'Resolved',     style: 'bg-green-600 hover:bg-green-700 text-white' })
    actions.push({ label: 'False +',     next: 'False Positive', style: 'bg-slate-500 hover:bg-slate-600 text-white' })
  } else if (alert.status === 'Acknowledged') {
    actions.push({ label: 'Resolve',     next: 'Resolved',     style: 'bg-green-600 hover:bg-green-700 text-white' })
    actions.push({ label: 'False +',     next: 'False Positive', style: 'bg-slate-500 hover:bg-slate-600 text-white' })
  } else {
    actions.push({ label: 'Re-open',     next: 'Open',         style: 'bg-red-500 hover:bg-red-600 text-white' })
  }

  return (
    <div className={`px-5 py-4 flex flex-col sm:flex-row sm:items-start gap-3 hover:bg-slate-50/70 transition-colors
                     ${alert.status !== 'Open' && alert.status !== 'Acknowledged' ? 'opacity-60' : ''}`}>

      {/* Left: severity bar */}
      <div className={`hidden sm:block w-1 self-stretch rounded-full flex-shrink-0 ${sev.bar}`} />

      {/* Content */}
      <div className="flex-1 min-w-0 space-y-1.5">

        {/* Top row: badges + title */}
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={alert.severity} />
          <TypeChip type={alert.alert_type} />
          <StatusPill status={alert.status} />
        </div>

        <p className="text-sm font-semibold text-slate-800 leading-snug">{alert.title}</p>

        {/* Meta row */}
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
          <button
            onClick={onUserClick}
            className="font-mono text-indigo-500 hover:text-indigo-700 hover:underline font-medium transition-colors"
          >
            {alert.user_id}
          </button>
          <span>·</span>
          <span>{timeAgo(alert.created_at)}</span>
          {alert.resolved_at && (
            <>
              <span>·</span>
              <span className="text-green-500">resolved {timeAgo(alert.resolved_at)}</span>
            </>
          )}
        </div>

        {/* Details — show key scores if present */}
        {alert.details && Object.keys(alert.details).length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-1">
            {Object.entries(alert.details)
              .filter(([, v]) => typeof v === 'number' || typeof v === 'string')
              .slice(0, 4)
              .map(([k, v]) => (
                <span key={k}
                  className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5
                             text-[10px] font-mono text-slate-600">
                  {k}: <span className="font-semibold text-slate-700">{
                    typeof v === 'number' ? v.toFixed(3) : String(v)
                  }</span>
                </span>
              ))}
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-1.5 flex-shrink-0">
        {updating ? (
          <svg className="animate-spin h-4 w-4 text-slate-400" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
          </svg>
        ) : (
          actions.map(({ label, next, style }) => (
            <button
              key={next}
              onClick={() => onStatusUpdate(next)}
              className={`rounded-md px-2.5 py-1 text-[10px] font-semibold transition-all ${style}`}
            >
              {label}
            </button>
          ))
        )}
      </div>

    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AlertsPage() {
  const router  = useRouter()
  const [alerts,   setAlerts]   = useState([])
  const [stats,    setStats]    = useState(null)
  const [filter,   setFilter]   = useState('Open')  // default to Open alerts
  const [loading,  setLoading]  = useState(true)
  const [updating, setUpdating] = useState(null)    // alert id being updated

  const load = useCallback(async (f) => {
    setLoading(true)
    try {
      const [alertsData, statsData] = await Promise.all([
        fetchAlerts(f === 'All' ? null : f, 100),
        fetchAlertStats(),
      ])
      setAlerts(alertsData)
      setStats(statsData)
    } catch (e) {
      console.error('Alerts load error:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load(filter) }, [filter, load])

  // Auto-refresh every 15 s
  useEffect(() => {
    const id = setInterval(() => load(filter), 15_000)
    return () => clearInterval(id)
  }, [filter, load])

  async function handleStatusUpdate(alertId, newStatus) {
    setUpdating(alertId)
    try {
      await updateAlertStatus(alertId, newStatus)
      await load(filter)
    } catch (e) {
      console.error('Status update failed:', e)
    } finally {
      setUpdating(null)
    }
  }

  return (
    <>
      <Head>
        <title>Alerts — Argus</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-5">

        {/* Page header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-slate-800">Security Alerts</h2>
            <p className="text-sm text-slate-500 mt-0.5">
              Auto-generated from the live ingestion pipeline · refreshes every 15 s
            </p>
          </div>
          <button
            onClick={() => load(filter)}
            className="flex-shrink-0 flex items-center gap-1.5 rounded-lg border border-slate-200
                       bg-white px-3 py-1.5 text-xs font-medium text-slate-500
                       hover:text-slate-700 hover:border-slate-300 transition-all"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" clipRule="evenodd"
                d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002
                   5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1
                   1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1
                   0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" />
            </svg>
            Refresh
          </button>
        </div>

        {/* Stats row */}
        {stats && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Open"          count={stats.open}           color="text-red-600"    bg="bg-red-50 border-red-200"    />
            <StatCard label="Acknowledged"  count={stats.acknowledged}   color="text-amber-600"  bg="bg-amber-50 border-amber-200"  />
            <StatCard label="Resolved"      count={stats.resolved}       color="text-green-600"  bg="bg-green-50 border-green-200"  />
            <StatCard label="False Positive" count={stats.false_positive} color="text-slate-500"  bg="bg-slate-50 border-slate-200"  />
          </div>
        )}

        {/* Filter + alert list */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">

          {/* Toolbar */}
          <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-1 rounded-lg bg-slate-100 p-1 flex-wrap">
              {STATUS_FILTERS.map(f => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={[
                    'relative rounded-md px-3 py-1.5 text-xs font-semibold transition-all',
                    filter === f
                      ? 'bg-white text-slate-800 shadow-sm ring-1 ring-slate-200'
                      : 'text-slate-500 hover:text-slate-700',
                  ].join(' ')}
                >
                  {f}
                  {f === 'Open' && stats?.open > 0 && (
                    <span className="ml-1.5 rounded-full bg-red-500 text-white text-[9px] font-bold px-1.5 py-0.5">
                      {stats.open}
                    </span>
                  )}
                </button>
              ))}
            </div>
            {!loading && (
              <p className="text-xs text-slate-400">
                {alerts.length} alert{alerts.length !== 1 ? 's' : ''}
              </p>
            )}
          </div>

          {/* Alert rows */}
          {loading ? (
            <div className="flex justify-center py-16">
              <svg className="animate-spin h-7 w-7 text-slate-300" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>
            </div>
          ) : alerts.length === 0 ? (
            <div className="py-16 text-center space-y-2">
              <div className="mx-auto rounded-full bg-slate-50 p-4 w-fit">
                <svg className="h-8 w-8 text-slate-300" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="1.5">
                  <path strokeLinecap="round" strokeLinejoin="round"
                    d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118
                       9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64
                       3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714
                       0a3 3 0 11-5.714 0" />
                </svg>
              </div>
              <p className="text-sm font-medium text-slate-500">
                No {filter !== 'All' ? filter.toLowerCase() : ''} alerts
              </p>
              {filter === 'Open' && (
                <p className="text-xs text-slate-400">
                  Ingest events in the{' '}
                  <button onClick={() => router.push('/demo')}
                    className="text-indigo-500 hover:underline font-medium">
                    Demo Lab
                  </button>
                  {' '}to trigger alerts automatically
                </p>
              )}
            </div>
          ) : (
            <div className="divide-y divide-slate-50">
              {alerts.map(alert => (
                <AlertRow
                  key={alert.id}
                  alert={alert}
                  updating={updating === alert.id}
                  onUserClick={() => router.push(`/users/${encodeURIComponent(alert.user_id)}`)}
                  onStatusUpdate={(status) => handleStatusUpdate(alert.id, status)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Empty state — no alerts at all */}
        {!loading && stats?.total === 0 && (
          <div className="rounded-xl border border-dashed border-slate-200 bg-white px-6 py-10 text-center">
            <p className="text-sm font-medium text-slate-600">No alerts have been generated yet</p>
            <p className="text-xs text-slate-400 mt-1.5 max-w-sm mx-auto">
              The system auto-creates alerts when events cross anomaly thresholds.
              Go to the{' '}
              <button onClick={() => router.push('/demo')}
                className="text-indigo-500 hover:underline font-medium">
                Demo Lab
              </button>
              {' '}and run a CERT file or device sample to see alerts appear here in real time.
            </p>
          </div>
        )}

      </main>
    </>
  )
}
