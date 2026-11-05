export default function ScoringStatusNotice({ status }) {
  if (!status) return null
  return <section role="status" aria-label="Scoring readiness" className="flex flex-wrap items-start gap-x-3 gap-y-2 rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600">
    <span className="font-semibold text-slate-800">Scoring</span>
    <span className="rounded bg-slate-100 px-2 py-0.5">{status.model_ready ? 'Provisional model' : 'Unavailable'}</span>
    <p className="flex-1 min-w-[200px]">{status.message || 'Scoring readiness details are unavailable.'}</p>
    <details className="max-w-xl"><summary className="cursor-pointer hover:text-slate-900">Details</summary>
      <div className="mt-3 space-y-2">{status.model_origin && <p>Model: {status.model_origin}</p>}{status.next_step && <p>{status.next_step}</p>}<p>Unknown means unscored.</p></div>
    </details>
  </section>
}
