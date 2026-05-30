import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import Link from 'next/link'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ReferenceLine, ResponsiveContainer,
} from 'recharts'
import { fetchUser, fetchUserShap, fetchInvestigation, saveInvestigation, getAiSuggestion, fetchUserEvents, fetchLiveScore } from '@/lib/api'

// ---------------------------------------------------------------------------
// Constants & style maps
// ---------------------------------------------------------------------------

const RISK_STYLE = {
  High:   { badge: 'bg-red-100 text-red-700 ring-1 ring-red-300',   dot: 'bg-red-500',    score: 'text-red-600'   },
  Medium: { badge: 'bg-amber-100 text-amber-700 ring-1 ring-amber-300', dot: 'bg-amber-500',  score: 'text-amber-600' },
  Low:    { badge: 'bg-green-100 text-green-700 ring-1 ring-green-300', dot: 'bg-green-500',  score: 'text-green-600' },
}

const SCORE_CARDS = [
  { key: 'ae_score',   label: 'AE Score ★',   title: 'Autoencoder reconstruction error — the final detector', primary: true  },
  { key: 'wa_score',   label: 'Weighted Avg', title: 'Weighted IF + AE average (comparison baseline; underperforms AE)', primary: false },
  { key: 'if_score',   label: 'IF Score',     title: 'Isolation Forest (unsupervised baseline)',             primary: false },
  { key: 'rule_score', label: 'Rule Score',   title: 'Rule-based heuristic (static weights, baseline)',       primary: false },
]

const INV_STATUSES = ['Pending', 'Under Investigation', 'Cleared', 'Confirmed Insider']

const INV_STYLE = {
  'Pending':            { bg: 'bg-slate-100',  text: 'text-slate-600',  ring: 'ring-slate-300',  dot: 'bg-slate-400'  },
  'Under Investigation':{ bg: 'bg-amber-100',  text: 'text-amber-700',  ring: 'ring-amber-300',  dot: 'bg-amber-500'  },
  'Cleared':            { bg: 'bg-green-100',  text: 'text-green-700',  ring: 'ring-green-300',  dot: 'bg-green-500'  },
  'Confirmed Insider':  { bg: 'bg-red-100',    text: 'text-red-700',    ring: 'ring-red-300',    dot: 'bg-red-500'    },
}

// ---------------------------------------------------------------------------
// Small reusable components
// ---------------------------------------------------------------------------

function Spinner({ label = 'Loading…' }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-24 text-slate-400">
      <svg className="animate-spin h-8 w-8" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10"
          stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      <span className="text-sm font-medium">{label}</span>
    </div>
  )
}

function BackButton({ onClick }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium
                 text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors"
    >
      <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" clipRule="evenodd"
          d="M17 10a.75.75 0 01-.75.75H5.56l3.22 3.22a.75.75 0 11-1.06 1.06l-4.5-4.5a.75.75
             0 010-1.06l4.5-4.5a.75.75 0 011.06 1.06L5.56 9.25H16.25A.75.75 0 0117 10z" />
      </svg>
      All users
    </button>
  )
}

function RiskBadge({ level }) {
  const s = RISK_STYLE[level] ?? RISK_STYLE.Low
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1
                      text-sm font-semibold ${s.badge}`}>
      <span className={`h-2 w-2 rounded-full ${s.dot}`} />
      {level} Risk
    </span>
  )
}

function ScoreCard({ label, value, title, highlight = false }) {
  const formatted = typeof value === 'number' ? value.toFixed(4) : '—'
  return (
    <div
      title={title}
      className={`rounded-xl border px-5 py-4 flex flex-col gap-1 shadow-sm
        ${highlight
          ? 'border-indigo-200 bg-indigo-50'
          : 'border-slate-200 bg-white'
        }`}
    >
      <span className={`text-xs font-semibold uppercase tracking-wider
        ${highlight ? 'text-indigo-500' : 'text-slate-400'}`}>
        {label}
      </span>
      <span className={`text-2xl font-bold tabular-nums
        ${highlight ? 'text-indigo-700' : 'text-slate-700'}`}>
        {formatted}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SHAP bar chart
// ---------------------------------------------------------------------------

/** Truncate long feature names for the Y-axis label */
function truncate(str, n = 22) {
  return str.length > n ? str.slice(0, n - 1) + '…' : str
}

/** Custom tooltip shown on bar hover */
function ShapTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const dir = d.shap_value > 0 ? 'increases risk' : 'decreases risk'
  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-lg px-3 py-2 text-xs">
      <p className="font-semibold text-slate-700 mb-1">{d.feature}</p>
      <p className={d.shap_value > 0 ? 'text-red-600' : 'text-green-600'}>
        SHAP: {d.shap_value.toFixed(5)} &nbsp;·&nbsp; {dir}
      </p>
    </div>
  )
}

function ShapChart({ features }) {
  // Recharts needs the data sorted ascending (bottom → top for horizontal bar)
  const data = [...features].reverse()

  // Compute a symmetric domain so the reference line sits at the true centre
  const maxAbs = Math.max(...features.map(f => Math.abs(f.shap_value)), 0.001)
  const domain = [-maxAbs * 1.15, maxAbs * 1.15]

  // Dynamic height: 36px per bar, minimum 320px
  const chartHeight = Math.max(data.length * 36, 320)

  return (
    <ResponsiveContainer width="100%" height={chartHeight}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 32, bottom: 4, left: 8 }}
        barCategoryGap="28%"
      >
        <XAxis
          type="number"
          domain={domain}
          tickFormatter={v => v.toFixed(3)}
          tick={{ fontSize: 10, fill: '#94a3b8' }}
          axisLine={{ stroke: '#e2e8f0' }}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="feature"
          tickFormatter={truncate}
          width={160}
          tick={{ fontSize: 11, fill: '#475569', fontFamily: 'ui-monospace, monospace' }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip content={<ShapTooltip />} cursor={{ fill: '#f1f5f9' }} />
        <ReferenceLine x={0} stroke="#cbd5e1" strokeWidth={1.5} />
        <Bar dataKey="shap_value" radius={[0, 3, 3, 0]} maxBarSize={22}>
          {data.map((entry, i) => (
            <Cell
              key={i}
              fill={entry.shap_value > 0 ? '#f87171' : '#4ade80'}   // red-400 / green-400
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ---------------------------------------------------------------------------
// Peer group context panel (Gap 2 — behavioural baselines)
// ---------------------------------------------------------------------------

const RATIO_LABEL = {
  login_count_sum:        'Login count',
  files_accessed_sum:     'Files accessed',
  usb_events_sum:         'USB events',
  email_count_sum:        'Emails sent',
  external_emails_sum:    'External emails',
  n_bcc_email_sum:        'BCC emails',
  suspicious_http_sum:    'Suspicious HTTP',
  n_job_site_sum:         'Job-site visits',
  http_count_sum:         'HTTP requests',
  after_hours_count_sum:  'After-hours sessions',
  total_attachments_sum:  'Email attachments',
  n_cloud_storage_sum:    'Cloud storage',
  n_afterhours_email_sum: 'After-hours emails',
  n_afterhours_usb_sum:   'After-hours USB',
}

function RatioBar({ ratio }) {
  const clamped = Math.min(ratio, 5)
  const pct     = Math.min((clamped / 5) * 100, 100)
  const color   = ratio >= 2.0 ? 'bg-red-400' : ratio >= 1.3 ? 'bg-amber-400' : 'bg-green-400'
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-1.5 rounded-full bg-slate-100 overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-xs font-semibold tabular-nums w-10 text-right
        ${ratio >= 2.0 ? 'text-red-600' : ratio >= 1.3 ? 'text-amber-600' : 'text-green-600'}`}>
        {ratio.toFixed(2)}×
      </span>
    </div>
  )
}

function PeerContextPanel({ peerGroup, peerSize, peerDeviations }) {
  if (peerGroup == null) return null

  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-3">
        <div className="rounded-lg bg-violet-50 p-2">
          <svg className="h-5 w-5 text-violet-500" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94
                 4.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112
                 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016
                 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0
                 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0
                 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971
                 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6
                 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25
                 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-slate-700">Peer Group Context</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Cluster {peerGroup} — {peerSize} similar users &nbsp;·&nbsp;
            ratio = user value ÷ peer group mean
          </p>
        </div>
        <span className="rounded-full bg-violet-100 text-violet-700 ring-1 ring-violet-200
                          text-xs font-semibold px-2.5 py-1">
          Group {peerGroup}
        </span>
      </div>

      <div className="px-6 py-5">
        {/* Legend */}
        <div className="flex items-center gap-4 text-xs text-slate-400 mb-4">
          <span className="flex items-center gap-1.5"><span className="h-2 w-4 rounded bg-red-400 inline-block"/>≥ 2× elevated</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-4 rounded bg-amber-400 inline-block"/>1.3–2× elevated</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-4 rounded bg-green-400 inline-block"/>Within normal range</span>
        </div>

        <div className="space-y-3">
          {peerDeviations.map(d => (
            <div key={d.feature} className="grid grid-cols-[1fr_auto_160px] items-center gap-3">
              <div>
                <p className="text-xs font-medium text-slate-700">
                  {RATIO_LABEL[d.feature] ?? d.feature}
                </p>
                <p className="text-xs text-slate-400 tabular-nums">
                  {d.user_value.toFixed(0)} vs peer avg {d.peer_mean.toFixed(0)}
                </p>
              </div>
              <div className="w-px h-6 bg-slate-100" />
              <RatioBar ratio={d.ratio} />
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Live activity feed (events ingested via /ingest)
// ---------------------------------------------------------------------------

const SOURCE_STYLE = {
  cert_logon:        { bg: 'bg-blue-100',    text: 'text-blue-700',    label: 'Logon'      },
  cert_file:         { bg: 'bg-amber-100',   text: 'text-amber-700',   label: 'File'       },
  cert_device:       { bg: 'bg-purple-100',  text: 'text-purple-700',  label: 'Device'     },
  cert_email:        { bg: 'bg-green-100',   text: 'text-green-700',   label: 'Email'      },
  cert_http:         { bg: 'bg-slate-100',   text: 'text-slate-600',   label: 'HTTP'       },
  aws_cloudtrail:    { bg: 'bg-orange-100',  text: 'text-orange-700',  label: 'AWS'        },
  azure_ad:          { bg: 'bg-sky-100',     text: 'text-sky-700',     label: 'Azure'      },
  cloudflare_access: { bg: 'bg-yellow-100',  text: 'text-yellow-700',  label: 'Cloudflare' },
}

function SourceBadge({ source }) {
  const s = SOURCE_STYLE[source] ?? { bg: 'bg-slate-100', text: 'text-slate-500', label: source }
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${s.bg} ${s.text}`}>
      {s.label}
    </span>
  )
}

function LiveActivityFeed({ events, loading }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-3">
        <div className="rounded-lg bg-emerald-50 p-2">
          <svg className="h-5 w-5 text-emerald-500" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-slate-700">Live Activity Feed</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Events ingested via the normalisation pipeline · most recent first
          </p>
        </div>
        {!loading && events.length > 0 && (
          <span className="rounded-full bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200
                           text-xs font-semibold px-2.5 py-1">
            {events.length} event{events.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Body */}
      {loading ? (
        <div className="px-6 py-8 text-center text-sm text-slate-400">Loading events…</div>
      ) : events.length === 0 ? (
        <div className="px-6 py-10 flex flex-col items-center gap-3 text-center">
          <div className="rounded-full bg-slate-50 p-4">
            <svg className="h-8 w-8 text-slate-300" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="1.5">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium text-slate-500">No live events yet</p>
            <p className="text-xs text-slate-400 mt-1">
              Use the{' '}
              <Link href="/demo" className="text-indigo-500 hover:underline font-medium">
                Demo page
              </Link>{' '}
              to ingest events for this user via <code className="bg-slate-100 px-1 rounded font-mono">POST /ingest</code>
            </p>
          </div>
        </div>
      ) : (
        <div className="divide-y divide-slate-50">
          {events.map(ev => (
            <div key={ev.id}
              className="px-6 py-3 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4
                         hover:bg-slate-50 transition-colors">
              {/* Source badge */}
              <div className="flex-shrink-0 w-16">
                <SourceBadge source={ev.source} />
              </div>
              {/* Action + resource */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-700 truncate">
                  <span className="text-slate-500">{ev.action}</span>
                  {ev.resource && (
                    <>
                      <span className="mx-1.5 text-slate-300">·</span>
                      <span className="font-mono text-xs">{ev.resource}</span>
                    </>
                  )}
                </p>
                {ev.ip_address && (
                  <p className="text-xs text-slate-400 font-mono mt-0.5">{ev.ip_address}</p>
                )}
              </div>
              {/* Timestamp */}
              <div className="flex-shrink-0 text-right">
                <p className="text-xs text-slate-500 tabular-nums">
                  {new Date(ev.timestamp).toLocaleString()}
                </p>
                <p className="text-xs text-slate-300 tabular-nums mt-0.5">
                  stored {new Date(ev.ingested_at).toLocaleTimeString()}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// 404 view
// ---------------------------------------------------------------------------

function NotFound({ id, onBack }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
      <div className="rounded-full bg-slate-100 p-5">
        <svg className="h-10 w-10 text-slate-400" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.5">
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M15.75 15.75l-2.489-2.489m0 0a3.375 3.375 0 10-4.773-4.773
               3.375 3.375 0 004.774 4.774zM21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
      <div>
        <p className="text-lg font-semibold text-slate-700">User not found</p>
        <p className="mt-1 text-sm text-slate-400">
          No record for <code className="font-mono bg-slate-100 px-1.5 py-0.5 rounded">{id}</code>
        </p>
      </div>
      <button
        onClick={onBack}
        className="mt-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white
                   hover:bg-indigo-700 transition-colors"
      >
        Back to dashboard
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Investigation panel
// ---------------------------------------------------------------------------

function InvestigationPanel({ userId, initial }) {
  const [inv,        setInv]        = useState(initial)
  const [status,     setStatus]     = useState(initial?.status        ?? 'Pending')
  const [analyst,    setAnalyst]    = useState(initial?.analyst       ?? '')
  const [notes,      setNotes]      = useState(initial?.notes         ?? '')
  // suggestion: { final: string, sources: {label: string}, synthesized: bool } | null
  // On first load, ai_suggestion is the cached plain string — wrap it for display
  const [suggestion, setSuggestion] = useState(
    initial?.ai_suggestion
      ? { final: initial.ai_suggestion, sources: {}, synthesized: false }
      : null
  )
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const [saving,      setSaving]      = useState(false)
  const [saved,       setSaved]       = useState(false)
  const [suggesting,  setSuggesting]  = useState(false)
  const [err,         setErr]         = useState(null)

  async function handleSave() {
    if (!analyst.trim()) { setErr('Analyst name is required.'); return }
    setSaving(true); setErr(null); setSaved(false)
    try {
      const updated = await saveInvestigation(userId, { status, analyst: analyst.trim(), notes })
      setInv(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (e) {
      setErr(e.message ?? 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  async function handleSuggest() {
    setSuggesting(true); setErr(null); setSourcesOpen(false)
    try {
      const res = await getAiSuggestion(userId)
      // res = { user_id, suggestion, sources, synthesized }
      setSuggestion({ final: res.suggestion, sources: res.sources ?? {}, synthesized: res.synthesized ?? false })
      setInv(prev => prev ? { ...prev, ai_suggestion: res.suggestion } : prev)
    } catch (e) {
      setErr(e.message ?? 'AI suggestion failed.')
    } finally {
      setSuggesting(false)
    }
  }

  const s = INV_STYLE[status] ?? INV_STYLE['Pending']

  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">

      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-3">
        <div className="rounded-lg bg-slate-50 p-2">
          <svg className="h-5 w-5 text-slate-500" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0
                 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424
                 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664
                 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25
                 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012
                 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08
                 C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621
                 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125
                 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621
                 -.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12z
                 m0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-slate-700">SOC Investigation</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            {inv ? `Last updated ${new Date(inv.updated_at).toLocaleString()}` : 'No record yet'}
          </p>
        </div>
        {inv && (
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1
                            text-xs font-semibold ring-1 ${s.bg} ${s.text} ${s.ring}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
            {status}
          </span>
        )}
      </div>

      <div className="px-6 py-5 space-y-5">

        {/* Status selector */}
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
            Status
          </label>
          <div className="flex flex-wrap gap-2">
            {INV_STATUSES.map(s => {
              const st = INV_STYLE[s]
              const active = status === s
              return (
                <button
                  key={s}
                  onClick={() => setStatus(s)}
                  className={[
                    'rounded-full px-3 py-1.5 text-xs font-semibold ring-1 transition-all',
                    active
                      ? `${st.bg} ${st.text} ${st.ring} shadow-sm`
                      : 'bg-white text-slate-400 ring-slate-200 hover:ring-slate-300 hover:text-slate-600',
                  ].join(' ')}
                >
                  {s}
                </button>
              )
            })}
          </div>
        </div>

        {/* Analyst name */}
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
            Analyst
          </label>
          <input
            type="text"
            value={analyst}
            onChange={e => setAnalyst(e.target.value)}
            placeholder="Your name"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm
                       text-slate-700 placeholder-slate-300 focus:outline-none
                       focus:ring-2 focus:ring-indigo-300 focus:border-indigo-300"
          />
        </div>

        {/* Notes */}
        <div>
          <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
            Notes
          </label>
          <textarea
            value={notes}
            onChange={e => setNotes(e.target.value)}
            rows={4}
            placeholder="Describe findings, evidence reviewed, or reason for disposition…"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm
                       text-slate-700 placeholder-slate-300 focus:outline-none
                       focus:ring-2 focus:ring-indigo-300 focus:border-indigo-300 resize-y"
          />
        </div>

        {/* AI Ensemble Suggestion */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                AI Investigation Guide
              </label>
              {suggestion?.synthesized && (
                <span className="inline-flex items-center gap-1 rounded-full bg-violet-100 px-2 py-0.5
                                 text-[10px] font-semibold text-violet-700 ring-1 ring-violet-200">
                  <svg className="h-2.5 w-2.5" viewBox="0 0 20 20" fill="currentColor">
                    <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969
                             0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755
                             1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197
                             -1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588
                             -1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                  </svg>
                  Ensemble · {Object.keys(suggestion.sources).length} models
                </span>
              )}
            </div>
            <button
              onClick={handleSuggest}
              disabled={suggesting}
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5
                         text-xs font-semibold text-white hover:bg-indigo-700
                         disabled:opacity-50 transition-colors"
            >
              {suggesting ? (
                <>
                  <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                  </svg>
                  Querying {suggestion ? 'models' : 'AI models'}…
                </>
              ) : (
                <>
                  <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" clipRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0
                         00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06
                         1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" />
                  </svg>
                  {suggestion ? 'Regenerate' : 'Get AI Suggestion'}
                </>
              )}
            </button>
          </div>

          {suggestion ? (
            <div className="space-y-2">
              {/* Final synthesised answer */}
              <div className="rounded-lg border border-indigo-100 bg-indigo-50 px-4 py-3">
                <div className="prose prose-sm max-w-none text-slate-700 text-xs leading-relaxed whitespace-pre-wrap">
                  {suggestion.final}
                </div>
              </div>

              {/* Collapsible raw provider outputs */}
              {Object.keys(suggestion.sources).length > 0 && (
                <div className="rounded-lg border border-slate-200 overflow-hidden">
                  <button
                    onClick={() => setSourcesOpen(o => !o)}
                    className="w-full flex items-center justify-between px-3 py-2
                               bg-slate-50 hover:bg-slate-100 transition-colors text-left"
                  >
                    <span className="text-xs font-medium text-slate-500 flex items-center gap-1.5">
                      <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                        <path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0
                                 00.707-1.707L16 11.586V8a6 6 0 00-6-6zM10 18a3 3 0 01-3-3h6a3
                                 3 0 01-3 3z" />
                      </svg>
                      Raw provider outputs ({Object.keys(suggestion.sources).length} models)
                    </span>
                    <svg
                      className={`h-3.5 w-3.5 text-slate-400 transition-transform ${sourcesOpen ? 'rotate-180' : ''}`}
                      viewBox="0 0 20 20" fill="currentColor"
                    >
                      <path fillRule="evenodd" clipRule="evenodd"
                        d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414
                           1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" />
                    </svg>
                  </button>

                  {sourcesOpen && (
                    <div className="divide-y divide-slate-100">
                      {Object.entries(suggestion.sources).map(([label, text]) => (
                        <div key={label} className="px-3 py-3">
                          <div className="flex items-center gap-1.5 mb-1.5">
                            <span className="inline-block rounded-full bg-slate-200 px-2 py-0.5
                                             text-[10px] font-semibold text-slate-600">
                              {label}
                            </span>
                            {text.startsWith('[error:') && (
                              <span className="text-[10px] text-red-500 font-medium">failed</span>
                            )}
                          </div>
                          <p className="text-[11px] text-slate-600 leading-relaxed whitespace-pre-wrap">
                            {text.startsWith('[error:') ? text : text}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-slate-200 px-4 py-5
                            text-center text-xs text-slate-400">
              Click &quot;Get AI Suggestion&quot; to query multiple AI models in parallel
              and synthesise a unified investigation guide.
            </div>
          )}
        </div>

        {/* Error */}
        {err && (
          <p className="text-xs text-red-600 font-medium">{err}</p>
        )}

        {/* Save */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white
                       hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : inv ? 'Update record' : 'Open investigation'}
          </button>
          {saved && (
            <span className="text-xs text-green-600 font-medium">Saved</span>
          )}
        </div>

        {/* History */}
        {inv?.history?.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
              Activity history
            </p>
            <ol className="relative border-l border-slate-200 space-y-4 pl-5">
              {[...inv.history].reverse().map((h, i) => {
                const hst = INV_STYLE[h.status] ?? INV_STYLE['Pending']
                return (
                  <li key={i} className="relative">
                    <span className={`absolute -left-[1.35rem] mt-0.5 h-2.5 w-2.5
                                      rounded-full ring-2 ring-white ${hst.dot}`} />
                    <p className="text-xs text-slate-400">
                      {new Date(h.timestamp).toLocaleString()} · <span className="font-medium text-slate-600">{h.analyst}</span>
                    </p>
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs
                                      font-semibold ring-1 mt-0.5 ${hst.bg} ${hst.text} ${hst.ring}`}>
                      {h.status}
                    </span>
                    {h.note && (
                      <p className="mt-1 text-xs text-slate-500 whitespace-pre-wrap">{h.note}</p>
                    )}
                  </li>
                )
              })}
            </ol>
          </div>
        )}

      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function UserDetail() {
  const router = useRouter()
  const { id } = router.query

  const [user,          setUser]          = useState(null)
  const [shap,          setShap]          = useState(null)
  const [invRec,        setInvRec]        = useState(null)   // null = not loaded yet
  const [liveScore,     setLiveScore]     = useState(null)   // null = no live data yet
  const [events,        setEvents]        = useState([])
  const [eventsLoading, setEventsLoading] = useState(true)
  const [loading,       setLoading]       = useState(true)
  const [notFound,      setNotFound]      = useState(false)
  const [error,         setError]         = useState(null)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    setEventsLoading(true)
    setNotFound(false)
    setError(null)

    // Core data: user detail, SHAP, investigation (critical path)
    Promise.all([fetchUser(id), fetchUserShap(id), fetchInvestigation(id)])
      .then(([userData, shapData, invData]) => {
        setUser(userData)
        setShap(shapData)
        setInvRec(invData)   // null when no record exists yet — that's fine
      })
      .catch((err) => {
        if (err.message?.includes('404') || err.message?.toLowerCase().includes('not found')) {
          setNotFound(true)
        } else {
          setError(err.message ?? 'Unknown error')
        }
      })
      .finally(() => setLoading(false))

    // Live events: non-critical, loads independently so it never blocks the main render
    fetchUserEvents(id, 20)
      .then(data => setEvents(Array.isArray(data) ? data : []))
      .catch(() => setEvents([]))
      .finally(() => setEventsLoading(false))

    // Live score: non-critical, always 200 — null means no events ingested yet
    fetchLiveScore(id)
      .then(data => {
        // Only surface if user has actually had events ingested
        if (data && data.event_count > 0) setLiveScore(data)
      })
      .catch(() => {})
  }, [id])

  const goBack = () => router.push('/')

  const riskStyle = RISK_STYLE[user?.risk_level] ?? RISK_STYLE.Low

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <>
      <Head>
        <title>{id ? `${id} — Argus` : 'User Detail — Argus'}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

        <main className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 py-6 space-y-6">

          {/* ── Loading ── */}
          {loading && <Spinner label={`Loading user ${id ?? ''}…`} />}

          {/* ── 404 ── */}
          {!loading && notFound && <NotFound id={id} onBack={goBack} />}

          {/* ── Error ── */}
          {!loading && error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              <span className="font-semibold">API error: </span>{error}
            </div>
          )}

          {/* ── Main content ── */}
          {!loading && user && (
            <>
              {/* ── User header card ── */}
              <section className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                <div className="px-6 py-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">

                  {/* Left: back + identity */}
                  <div className="flex flex-col gap-3">
                    <BackButton onClick={goBack} />
                    <div className="flex items-center gap-3 flex-wrap">
                      <h2 className="font-mono text-2xl font-bold text-slate-800">
                        {user.user}
                      </h2>
                      <RiskBadge level={user.risk_level} />
                      {user.scenario > 0 && (
                        <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium
                                         text-slate-600 ring-1 ring-slate-200">
                          Scenario {user.scenario}
                        </span>
                      )}
                      {user.is_insider === 1 && (
                        <span className="rounded-md bg-rose-100 px-2 py-0.5 text-xs font-semibold
                                         text-rose-700 ring-1 ring-rose-300">
                          ⚑ Confirmed Insider
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Right: static AE score + optional live score */}
                  <div className="flex items-end gap-5">

                    {/* Live Score card — only shown when events have been ingested */}
                    {liveScore && (
                      <div className="flex flex-col items-start sm:items-end gap-1">
                        <div className="flex items-center gap-1.5">
                          {/* Pulsing green dot */}
                          <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                          </span>
                          <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600">
                            Live AE
                          </span>
                        </div>
                        <span className="text-4xl font-bold tabular-nums leading-none text-emerald-600">
                          {liveScore.ae_live != null ? liveScore.ae_live.toFixed(3) : '—'}
                        </span>
                        <div className="text-[10px] text-slate-400 text-right space-y-0.5">
                          {/* Arrow showing direction vs static */}
                          {liveScore.ae_live != null && (
                            <span className={`font-semibold ${
                              liveScore.ae_live > user.ae_score
                                ? 'text-red-500'
                                : liveScore.ae_live < user.ae_score
                                  ? 'text-green-500'
                                  : 'text-slate-400'
                            }`}>
                              {liveScore.ae_live > user.ae_score ? '↑ higher live risk'
                               : liveScore.ae_live < user.ae_score ? '↓ lower live risk'
                               : '= unchanged'}
                            </span>
                          )}
                          <p>{liveScore.event_count} events ingested</p>
                        </div>
                      </div>
                    )}

                    {/* Static AE score */}
                    <div className="flex flex-col items-start sm:items-end gap-1">
                      <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                        AE Score
                      </span>
                      <span className={`text-5xl font-bold tabular-nums leading-none ${riskStyle.score}`}>
                        {user.ae_score.toFixed(3)}
                      </span>
                      {/* Thin full-width score bar */}
                      <div className="w-40 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all
                            ${user.risk_level === 'High'
                              ? 'bg-red-400'
                              : user.risk_level === 'Medium'
                                ? 'bg-amber-400'
                                : 'bg-green-400'
                            }`}
                          style={{ width: `${Math.round(user.ae_score * 100)}%` }}
                        />
                      </div>
                    </div>

                  </div>

                </div>
              </section>

              {/* ── Score breakdown row ── */}
              <section aria-label="Score breakdown">
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
                  {SCORE_CARDS.map(({ key, label, title, primary }) => (
                    <ScoreCard
                      key={key}
                      label={label}
                      value={user[key]}
                      title={title}
                      highlight={primary}
                    />
                  ))}
                </div>
                <p className="mt-2 text-xs text-slate-400">
                  ★ AE Score = Autoencoder reconstruction error, the final detector.
                  Weighted-Avg, IF and Rule scores are shown for research comparison only.
                </p>
              </section>

              {/* ── SHAP panel ── */}
              {shap && (
                <section className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">

                  {/* Panel header */}
                  <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-3">
                    <div className="rounded-lg bg-indigo-50 p-2">
                      <svg className="h-5 w-5 text-indigo-500" viewBox="0 0 24 24" fill="none"
                        stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round"
                          d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504
                             1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125
                             1.125 0 013 19.875v-6.75zm6.75-9.75c0-.621.504-1.125
                             1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v16.5c0
                             .621-.504 1.125-1.125 1.125h-2.25A1.125 1.125 0 019.75
                             19.875V3.375zm6.75 7.5c0-.621.504-1.125 1.125-1.125h2.25
                             c.621 0 1.125.504 1.125 1.125v9c0 .621-.504 1.125-1.125
                             1.125h-2.25a1.125 1.125 0 01-1.125-1.125v-9z" />
                      </svg>
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-slate-700">SHAP Feature Importance</h3>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Top {shap.features.length} features driving this anomaly score
                      </p>
                    </div>
                  </div>

                  <div className="px-6 py-5 space-y-5">

                    {/* Plain-English reason */}
                    <div className="rounded-lg border border-indigo-100 bg-indigo-50 px-4 py-3
                                    flex items-start gap-3">
                      <svg className="mt-0.5 h-4 w-4 flex-shrink-0 text-indigo-400"
                        viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" clipRule="evenodd"
                          d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2
                             0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0
                             01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75
                             0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75
                             1.75 0 009.253 9H9z" />
                      </svg>
                      <p className="text-sm font-semibold text-indigo-800 leading-relaxed">
                        {shap.reason}
                      </p>
                    </div>

                    {/* Legend */}
                    <div className="flex items-center gap-5 text-xs text-slate-500">
                      <span className="flex items-center gap-1.5">
                        <span className="h-2.5 w-5 rounded bg-red-400 inline-block" />
                        Increases risk
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="h-2.5 w-5 rounded bg-green-400 inline-block" />
                        Decreases risk
                      </span>
                      <span className="ml-auto text-slate-300 hidden sm:block">
                        Sorted by |SHAP value| descending
                      </span>
                    </div>

                    {/* Chart */}
                    <div className="w-full">
                      <ShapChart features={shap.features} />
                    </div>

                  </div>
                </section>
              )}

              {/* No SHAP data fallback */}
              {!shap && !loading && (
                <div className="rounded-xl border border-slate-200 bg-white shadow-sm px-6 py-10
                                text-center text-sm text-slate-400">
                  SHAP values not available for this user.
                </div>
              )}

              {/* ── Peer group context (Gap 2) ── */}
              <PeerContextPanel
                peerGroup={user.peer_group}
                peerSize={user.peer_size}
                peerDeviations={user.peer_deviations ?? []}
              />

              {/* ── Live activity feed (Gap 1 — normalised pipeline output) ── */}
              <LiveActivityFeed events={events} loading={eventsLoading} />

              {/* ── Investigation panel ── */}
              <InvestigationPanel userId={id} initial={invRec} />

            </>
          )}

        </main>
    </>
  )
}
