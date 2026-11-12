import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { Frame, ErrorNotice, Info, request, when } from '@/components/WorkspaceUI'

const LABELS = { recent: 'Recent check', attention: 'Needs attention', stale: 'Stale', ended: 'Ended' }
function Check({ label, value }) {
  if (!value || (!LABELS[value.status] && !value.last_checked_at && value.attention_scope !== 'historical')) return null
  const historical = value.attention_scope === 'historical'
  const warn = !historical && ['attention', 'stale'].includes(value.status)
  return <section className="border-t pt-3 space-y-1"><p className="text-sm font-medium">{label} <span className={'ml-2 text-xs rounded px-2 py-1 ' + (warn ? 'bg-amber-50 text-amber-800' : 'bg-slate-100 text-slate-600')}>{historical ? 'Previous outcome unresolved' : label === 'Collector' && value.status === 'attention' ? 'Poll needs attention' : LABELS[value.status] || ''}</span></p>{value.last_checked_at && <p className="text-xs text-slate-500">Last check: {when(value.last_checked_at)}{Number.isInteger(value.age_seconds_at_capture) && ` · ${Math.floor(value.age_seconds_at_capture / 60)} min old at last refresh`}</p>}</section>
}
// Mirror view: last tick of the pilot collector, newest event received, and today's count for this source.
function Live({ feed, source }) {
  if (!feed) return null
  const s = feed.sources[source] || {}, tick = feed.collector
  return <section className="border-t pt-3 text-xs text-slate-600 space-y-1">{tick?.last_tick_utc && <p>Pilot collector: {tick.ok ? 'ok' : 'reported a problem'} · last check {when(tick.last_tick_utc)}</p>}<p>Last received: {s.last_received_utc ? when(s.last_received_utc) : 'nothing received'}</p><p>Events today (MYT): {s.events_today_myt ?? 0} · last hour: {s.events_last_hour ?? 0}</p></section>
}
function Activity({ source }) {
  const window = source.activity_window || {}, history = source.workload_history || {}
  const labels = { outside_hours: 'Outside activity hours', within_hours: 'Activity window open', not_started: 'Activity has not started', ended: 'Activity ended' }
  return <section className="border-t pt-3 text-xs text-slate-600 space-y-2">{labels[window.status] && <p className="font-medium">{labels[window.status]}{['outside_hours', 'within_hours'].includes(window.status) && ' · 08:00–20:00 MYT'}</p>}{history.available ? <><p>Recorded day ({history.day}): {history.today.verified} verified · {history.today.pending_receipts} pending · {history.today.unresolved} unresolved · {history.today.missed} missed</p>{(history.prior_days.unresolved > 0 || history.prior_days.missed > 0 || history.prior_days.pending_receipts > 0) && <p>Previous days: {history.prior_days.unresolved} unresolved · {history.prior_days.missed} missed · {history.prior_days.pending_receipts} pending</p>}</> : null}</section>
}
export default function Connections() {
  const router = useRouter()
  const [data, setData] = useState(null), [error, setError] = useState(null), [feed, setFeed] = useState(null), [drift, setDrift] = useState({})
  async function load() {
    try { setData(await request('/workspace/connections')); setError(null) } catch (e) { setError(e.message) }
    try { setFeed(await request('/workspace/live-feed')) } catch { setFeed(null) }
    try { setDrift((await request('/workspace/source-drift')).sources) } catch { setDrift({}) }
  }
  useEffect(() => { load(); const timer = setInterval(load, 60000); return () => clearInterval(timer) }, [])
  return <Frame title="Connections"><ErrorNotice error={error} />{router.query.case_id && <Link className="text-sm text-indigo-700" href={{ pathname: '/cases/' + encodeURIComponent(router.query.case_id), query: { provider: router.query.provider || '', start: router.query.start || '', end: router.query.end || '' } }}>← Return to case with timeline filters</Link>}<div className="flex flex-wrap gap-3 items-center">{data?.captured_at && <p className="text-sm text-slate-500">Last checked {when(data.captured_at)} · updates automatically every minute</p>}</div>{!data ? !error && <p>Loading connections…</p> : <><div className="grid md:grid-cols-3 gap-4">{data.sources.filter(source => !router.query.provider || source.source === router.query.provider).map(source => <article key={source.source} className="bg-white rounded-xl border p-5 space-y-4"><h2 className="text-lg font-semibold">{source.title}</h2><div className="flex gap-6"><div><p className="text-2xl font-semibold">{source.event_count}</p><p className="text-xs text-slate-500">Stored events</p></div><div><p className="text-2xl font-semibold">{source.account_count}</p><p className="text-xs text-slate-500">Observed accounts</p></div></div>{source.latest_observed_in_scan && <p className="text-xs text-slate-500">Latest activity: {when(source.latest_observed_in_scan)}</p>}{drift[source.source] && <section className="border-t pt-3 text-xs text-amber-800 space-y-1"><p className="font-medium">Source drift · observation ({drift[source.source].day})</p>{drift[source.source].facts.map((f, i) => <p key={i}>{f}</p>)}</section>}<Check label="Collector" value={source.collector} /><Live feed={feed} source={source.source} /><Check label="Controlled workload" value={source.workload} /><Activity source={source} /><Link className="inline-block text-sm text-indigo-700" href={{ pathname: '/workspace', query: { provider: source.source } }}>Review source findings →</Link></article>)}</div>{!data.sources.length && <p>No connected sources yet.</p>}<p className="text-xs text-slate-500">About these figures<Info label="About these figures">Idle outside activity hours is expected; log collection may continue overnight. Event totals do not establish complete coverage. Missing receipts remain unresolved; no action is retried here.{data.event_scan_capped && ' Latest-activity scan is capped at 10,000 rows.'}</Info></p></>}</Frame>
}
