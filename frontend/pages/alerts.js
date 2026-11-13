import { useCallback, useEffect, useRef, useState } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import { fetchAlerts, fetchAlertStats, updateAlertStatus, escalateAlert } from '@/lib/api'

const STATUSES = ['All', 'Open', 'Acknowledged', 'Resolved', 'False Positive']
const LABELS = { rarity_spike: 'Rarity rules', anomalous_behavior: 'Timing and novelty rule', new_user: 'New account observation', ae_critical: 'AE threshold alert' }
const SOURCE_LABELS = { aws_cloudtrail: 'AWS CloudTrail', cloudflare_access: 'Cloudflare Access', github_events: 'GitHub Events', cert: 'CERT benchmark' }
function origin(type) {
  return ['rarity_spike', 'anomalous_behavior'].includes(type) ? 'Rule signal' : type === 'new_user' ? 'Observation' : type === 'ae_critical' ? 'AE detection' : 'Unverified origin'
}
const pill = 'inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 '
const severityColor = value => ['Critical', 'High'].includes(value) ? 'bg-rose-50 text-rose-700 ring-rose-200' : value === 'Medium' ? 'bg-amber-50 text-amber-800 ring-amber-200' : 'bg-slate-100 text-slate-600 ring-slate-200'

export default function AlertsPage() {
  const [alerts, setAlerts] = useState([])
  const [stats, setStats] = useState(null)
  const [filter, setFilter] = useState('Open')
  const [kind, setKind] = useState('Security findings')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [updating, setUpdating] = useState(null)
  const [pending, setPending] = useState(null)
  const [success, setSuccess] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const requestId = useRef(0)
  const load = useCallback(async () => {
    const id = ++requestId.current
    try {
      const [rows, counts] = await Promise.all([fetchAlerts(filter === 'All' ? null : filter, 100), fetchAlertStats()])
      if (id === requestId.current) { setAlerts(rows); setStats(counts); setError(null) }
    } catch (e) { if (id === requestId.current) setError(e.message || 'Unable to load alerts') }
    finally { if (id === requestId.current) setLoading(false) }
  }, [filter])
  useEffect(() => { setLoading(true); load(); const timer = setInterval(load, 15000); return () => { clearInterval(timer); requestId.current++ } }, [load])
  async function changeStatus(alert, status) {
    setUpdating(alert.id); setError(null)
    try { await updateAlertStatus(alert.id, status); setSuccess({ message: `Alert #${alert.id} marked ${status}.` }); await load() }
    catch (e) { setError(e.message || 'Status update failed') }
    finally { setUpdating(null) }
  }
  async function confirmEscalation() {
    const alert = pending
    setUpdating(alert.id); setError(null)
    try {
      const result = await escalateAlert(alert.id)
      setPending(null)
      setSuccess({ message: `Alert #${alert.id} linked to an investigation.`, user: result.user_id })
      await load()
    } catch (e) { setError(e.message || 'Escalation failed. No success has been assumed.') }
    finally { setUpdating(null) }
  }
  const visible = alerts.filter(alert => kind === 'Security findings' ? ['Rule signal', 'AE detection'].includes(origin(alert.alert_type)) : origin(alert.alert_type) === kind)
  return <>
    <Head><title>Alert review — Argus</title></Head>
    <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8 space-y-5">
      <div className="flex justify-between items-start gap-4">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Alert review</h1>
        <button onClick={load} className="rounded-lg border bg-white px-4 py-2 text-sm text-slate-700">Refresh</button>
      </div>
      {error && <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</div>}
      {success && <div role="status" className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-sm text-indigo-900 flex flex-wrap gap-3"><span>{success.message}</span>{success.user && <Link className="font-semibold underline" href={'/users/' + encodeURIComponent(success.user)}>Open account investigation →</Link>}</div>}
      {stats && <p className="text-xs text-slate-500">Status totals include security findings and account observations.</p>}
      {stats && <section aria-label="All signal status summary" className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[['Open', stats.open], ['Acknowledged', stats.acknowledged], ['Resolved', stats.resolved], ['False Positive', stats.false_positive]].map(([label, value]) => <button key={label} onClick={() => setFilter(label)} className="rounded-xl border border-slate-200 bg-white text-left p-4 hover:border-indigo-300"><span className="text-xs text-slate-500">{label}</span><p className="text-3xl font-bold text-slate-800 mt-1">{value}</p></button>)}
      </section>}
      {pending && <section aria-label="Confirm investigation" className="rounded-xl border border-indigo-300 bg-indigo-50 p-5 space-y-3">
        <h2 className="font-semibold text-slate-900">Investigate alert #{pending.id}?</h2>
        <p className="text-sm text-slate-700 break-words">{pending.title}</p>
        <p className="text-xs text-slate-600">Creates or links a case and acknowledges this alert. Existing notes and owner are retained.</p>
        <div className="flex gap-2"><button disabled={updating !== null} onClick={confirmEscalation} className="rounded-lg bg-indigo-700 text-white px-4 py-2 text-sm font-semibold disabled:opacity-50">{updating === pending.id ? 'Creating…' : 'Create or link case'}</button><button disabled={updating !== null} onClick={() => setPending(null)} className="rounded-lg bg-white border px-4 py-2 text-sm">Cancel</button></div>
      </section>}
      <section aria-label="Alert queue" className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm">
        <div className="p-4 border-b border-slate-100 space-y-3">
          <div className="flex flex-wrap gap-1" aria-label="Alert status filters">{STATUSES.map(status => <button key={status} onClick={() => setFilter(status)} aria-pressed={filter === status} className={'rounded-lg px-3 py-1.5 text-xs font-semibold ' + (filter === status ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600')}>{status}</button>)}</div>
          <div className="flex flex-wrap items-center justify-between gap-3"><label className="text-xs text-slate-500">Category <select aria-label="Signal origin" className="ml-2 rounded-lg border p-1.5 text-slate-700" value={kind} onChange={e => setKind(e.target.value)}>{['Security findings', 'Observation', 'Unverified origin'].map(value => <option key={value} value={value}>{value === 'Observation' ? 'Account observations' : value}</option>)}</select></label><span className="text-xs text-slate-400">{visible.length} shown · category filtered from up to 100 newest signals</span></div>
        </div>
        {loading ? <p className="p-12 text-center text-sm text-slate-500">Loading alerts…</p> : visible.length === 0 ? <div className="p-12 text-center"><h2 className="font-semibold text-slate-700">No alerts in this view</h2><p className="text-sm text-slate-500 mt-2">Try another status or origin.</p><Link href="/" className="inline-block mt-4 text-sm font-semibold text-indigo-700">View connected activity →</Link></div> : <div className="overflow-x-auto">
          <table className="w-full min-w-[1100px] table-fixed text-sm text-left"><colgroup>{[10, 28, 18, 12, 15, 17].map((width, index) => <col key={index} style={{ width: width + '%' }} />)}</colgroup><thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500"><tr>
            {['Severity', 'Signal', 'Account', 'Created', 'Status', ''].map((label, index) => <th key={index} className="px-4 py-3 font-semibold">{label}</th>)}
          </tr></thead>
          {visible.map(alert => {
            const active = ['Open', 'Acknowledged'].includes(alert.status)
            const busy = updating !== null
            return <tbody key={alert.id} className="border-t border-slate-100">
              <tr data-testid="alert-row" className="hover:bg-slate-50/70 align-top">
                <td className="px-4 py-4"><span className={pill + severityColor(alert.severity)}>{alert.severity}</span></td>
                <td className="px-4 py-4 max-w-sm"><p className="font-medium text-slate-800 text-xs leading-5 break-words line-clamp-2">{alert.title}</p><p className="text-[11px] text-slate-400 mt-1">#{alert.id} · {origin(alert.alert_type)}{alert.details?.source ? ' · ' + (SOURCE_LABELS[alert.details.source] || alert.details.source) : ''}</p></td>
                <td className="px-4 py-4 max-w-[210px]">{alert.user_id ? <Link href={'/users/' + encodeURIComponent(alert.user_id)} className="font-mono text-xs text-indigo-700 hover:underline break-all">{alert.display_name || alert.user_id}</Link> : <span className="text-xs text-slate-400">Unresolved identity</span>}</td>
                <td className="px-4 py-4 text-xs text-slate-500 whitespace-nowrap">{new Date(alert.created_at).toLocaleString('en-GB', { timeZone: 'Asia/Kuala_Lumpur', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                <td className="px-4 py-3"><select aria-label={'Status for alert ' + alert.id} disabled={busy} value={alert.status} onChange={e => changeStatus(alert, e.target.value)} className="rounded-md border border-slate-200 bg-white text-xs px-2 py-1.5 text-slate-600 disabled:opacity-50">{STATUSES.filter(value => value !== 'All').map(value => <option key={value}>{value}</option>)}</select></td>
                <td className="px-4 py-3"><div className="flex items-center gap-2">{active && <button disabled={busy || !alert.user_id} title={alert.user_id ? 'Open investigation' : 'Identity needs review'} onClick={() => { setPending(alert); setSuccess(null) }} className="rounded-md bg-indigo-700 text-white px-3 py-1.5 text-xs font-semibold disabled:opacity-50 whitespace-nowrap">Investigate →</button>}
                  <button aria-expanded={expanded === alert.id} aria-label={'Evidence for alert ' + alert.id} onClick={() => setExpanded(expanded === alert.id ? null : alert.id)} className="rounded-md border border-slate-200 px-2 py-1.5 text-xs text-slate-600">Details</button></div>{updating === alert.id && <span role="status" className="text-xs text-slate-400">Saving…</span>}</td>
              </tr>
              {expanded === alert.id && <tr><td colSpan={6} className="px-5 py-4 bg-slate-50"><div className="flex flex-wrap gap-3 items-start"><div className="flex-1"><p className="text-xs font-semibold text-slate-700">{LABELS[alert.alert_type] || alert.alert_type}</p><pre className="text-xs text-slate-600 whitespace-pre-wrap break-all mt-2 max-h-60 overflow-auto">{JSON.stringify(alert.details || {}, null, 2)}</pre></div><Link href={'/users/' + encodeURIComponent(alert.user_id)} className="text-xs text-indigo-700 font-semibold">Open account →</Link></div></td></tr>}
            </tbody>
          })}
          </table>
        </div>}

      </section>
      <details className="text-xs text-slate-500"><summary className="cursor-pointer">About signals</summary><p className="mt-2 max-w-2xl">Rule signals, account observations and AE detections have separate origins. Severity is a review cue, not a compromise probability. Escalation opens an internal case; it sends no external notification or cloud action.</p></details>
    </main>
  </>
}
