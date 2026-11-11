import { useEffect, useState } from 'react'
import { display, request, useCommand, field, secondary, when } from '@/components/WorkspaceUI'

export function activityDay(timestamp) {
  if (!timestamp || !Number.isFinite(Date.parse(timestamp))) return ''
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kuala_Lumpur', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(timestamp))
  return ['year', 'month', 'day'].map(kind => parts.find(part => part.type === kind).value).join('-')
}

export default function DiagnosticPanel({ account, initialDay = '', caseContext = null }) {
  const [day, setDay] = useState(initialDay), [data, setData] = useState(null), [error, setError] = useState(null)
  const [analyst, setAnalyst] = useState(''), [reason, setReason] = useState('')
  const command = useCommand()
  const source = account?.source, scope = account?.source_account_id, key = account?.account_key
  useEffect(() => {
    let active = true
    setData(null); setError(null)
    if (!day || !source || !scope || !key) return () => { active = false }
    const query = new URLSearchParams({ source, scope, account: key, day })
    request('/workspace/diagnostic-availability?' + query).then(async value => {
      if (value.score_display_approved) {
        const scored = await request('/workspace/diagnostics?' + query)
        value = { ...scored, artifact_manifest_sha256: value.artifact_manifest_sha256 }
      }
      if (active) setData(value)
    })
      .catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [source, scope, key, day])
  const receipt = data?.receipt, history = data?.history_scopes
  return <section className="border-t pt-4 space-y-3" aria-label="Account-day model diagnostic">
    <h3 className="font-medium text-sm">Model diagnostic</h3>
    <label className="block text-xs text-slate-600">Activity day (MYT)<input type="date" className={field} value={day} onChange={e => setDay(e.target.value)} /></label>
    {error || command.error ? <p role="alert" className="text-sm text-red-700">{error || command.error}</p> : !day ? <p className="text-xs text-slate-500">Choose a closed day.</p> : !source || !scope || !key ? null : !data ? <p className="text-sm text-slate-500">Loading diagnostic…</p> : <>
      <p className="text-sm">{data.status === 'unavailable' ? data.reason : data.status === 'unscored' ? receipt.input.why_unscored : 'Experimental model output'}</p>
      {receipt && <>
        <p className="text-xs text-slate-500">{data.mode === 'recorded' ? 'Recorded diagnostic' : 'Live-source diagnostic'} · {when(data.cutoff_utc)}</p>
        <p className="text-xs text-slate-500">History: {history.expanding_history_days.length} accepted days for action novelty · {history.rolling_window_days.length} for recent behaviour.</p>
        {Object.entries(receipt.detectors).map(([name, detector]) => <details key={name} className="rounded-lg border p-3 text-sm">
          <summary className="cursor-pointer">{name} · raw reconstruction error {Number(detector.score_raw_mse).toPrecision(4)}</summary>
          <p className="mt-2 text-xs text-slate-500">Experimental; not validated for this live source.</p>
          <ul className="mt-2 space-y-1">{detector.terms.map(term => <li key={term.feature} className="text-xs">{display(term.text || term.feature)} · {(term.share_of_reconstruction_error * 100).toFixed(1)}% of reconstruction error</li>)}</ul>
        </details>)}
        {!!receipt.facts?.length && <details className="text-xs"><summary className="cursor-pointer">Behaviour facts</summary><ul className="mt-2 space-y-2">{receipt.facts.map((fact, i) => <li key={i}>{display(fact.text)}</li>)}</ul></details>}
        <details className="text-xs"><summary className="cursor-pointer">Coverage and provenance</summary><p className="mt-2">{receipt.coverage.policy_status} · {receipt.completeness}</p><p>Receipt {receipt.receipt_id.slice(0, 12)} · {receipt.schema}</p><p>Coverage concerns planned actions; other activity may be incomplete.</p></details>
        {caseContext?.open && <div data-write-action className="space-y-2 border-t pt-3">
          <label className="block text-xs">Analyst for diagnostic context<input className={field} maxLength={200} value={analyst} onChange={e => setAnalyst(e.target.value)} /></label>
          <label className="block text-xs">Reason for retaining context<input className={field} maxLength={2000} value={reason} onChange={e => setReason(e.target.value)} /></label>
          <button className={secondary} disabled={command.busy || !analyst.trim() || !reason.trim()} onClick={() => command.run(`/cases/${caseContext.id}/diagnostics`, {
            source, scope, account: key, day, actor: analyst, reason, expected_version: caseContext.version,
            receipt_id: receipt.receipt_id, artifact_manifest_sha256: data.artifact_manifest_sha256
          }, 'POST', value => { caseContext.onRetained(value); setReason('') })}>Retain diagnostic context</button>
        </div>}
      </>}
    </>}
  </section>
}
