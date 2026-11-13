import { useEffect, useState } from 'react'
import Link from 'next/link'
import { fetchMonitoringOverview } from '@/lib/api'

const SOURCES = [
  ['aws_cloudtrail', 'AWS CloudTrail', 'Cloud API activity', 'bg-orange-500'],
  ['cloudflare_access', 'Cloudflare Access', 'Protected application access', 'bg-amber-500'],
  ['github_events', 'GitHub', 'Repository activity', 'bg-slate-700'],
]
const date = value => value ? new Date(value).toLocaleString('en-GB', { timeZone: 'Asia/Kuala_Lumpur' }) + ' MY' : '—'
const CHECK_LABELS = { recent: 'Recent check', attention: 'Needs review', stale: 'Stale check', unavailable: 'No status', ended: 'Ended' }

function CollectorCheck({ label, value }) {
  if (!value) return null
  const attention = value.status === 'attention' || value.status === 'stale'
  return <p className={'text-xs mt-2 ' + (attention ? 'text-amber-700' : 'text-slate-500')} title={'Last check: ' + date(value.last_checked_at)}>
    {label} <span className="font-medium">{CHECK_LABELS[value.status] || 'No status'}</span>
    {value.unresolved > 0 && <span> · {value.unresolved} unresolved</span>}
    {value.missed > 0 && <span> · {value.missed} missed</span>}
    {value.pending_receipts > 0 && <span> · {value.pending_receipts} awaiting receipt</span>}
  </p>
}

export default function SourceActivity() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    let active = true
    const load = () => fetchMonitoringOverview().then(value => {
      if (active) { setData(value); setError(null) }
    }).catch(() => { if (active) setError('Source activity could not be refreshed. Last displayed values may be stale.') })
    load(); const timer = setInterval(load, 30000)
    return () => { active = false; clearInterval(timer) }
  }, [])
  const origins = data?.active_alerts_by_origin
  return <section aria-label="Source activity" className="space-y-4">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Overview</h1>
      <Link href="/alerts" className="rounded-lg bg-slate-900 text-white px-4 py-2 text-sm font-semibold hover:bg-slate-700">View alerts →</Link>
    </div>
    {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
    <div className="grid md:grid-cols-3 gap-4">
      {SOURCES.map(([key, title, description, color]) => {
        const source = data?.sources.find(row => row.source === key)
        return <article key={key} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-2"><h2 className="font-semibold text-slate-800 flex items-center gap-2"><span className={'w-2 h-2 rounded-full ' + color} />{title}</h2>
            <span className="text-[10px] font-semibold rounded-full bg-slate-100 text-slate-600 px-2 py-1">{data ? source ? 'Observed' : 'No events' : 'Loading'}</span></div>

          <p className="text-3xl font-bold text-slate-900 mt-4 tabular-nums">{data ? (source?.event_count ?? 0).toLocaleString() : '—'} <span className="text-xs font-normal text-slate-500">events</span></p>
          <p className="text-xs text-slate-500 mt-2">{source ? source.account_references : data ? 0 : '—'} account reference(s)</p>
          <CollectorCheck label="Collector" value={data?.collector_status?.[key]?.collector} />
          <CollectorCheck label="Workload" value={data?.collector_status?.[key]?.workload} />
          <p className="mt-4 pt-3 border-t border-slate-100 text-xs text-slate-500">Received <span className="text-slate-700">{date(source?.latest_ingested_at)}</span></p>
        </article>
      })}
    </div>
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-500">
      <span className="font-semibold text-slate-700">Active signals</span>
      {origins ? <><span>Rules <strong className="text-slate-800 ml-1">{origins.rule}</strong></span><span>Observations <strong className="text-slate-800 ml-1">{origins.observation}</strong></span><span>AE <strong className="text-slate-800 ml-1">{origins.model}</strong></span>{origins.unverified > 0 && <span>Unverified {origins.unverified}</span>}</> : <span>Loading…</span>}
      <details className="ml-auto"><summary className="cursor-pointer text-slate-500 hover:text-slate-800">Source details</summary><div className="mt-2 rounded-lg border bg-white p-3 max-w-xl space-y-2">
        <p>Stored event counts; coverage and collector health are not inferred. Account references can include workloads.</p>
        {data?.sources.map(source => <p key={source.source}>{SOURCES.find(item => item[0] === source.source)?.[1] || source.source}: latest event {date(source.latest_event_at)}</p>)}
      </div></details>
    </div>
  </section>
}
