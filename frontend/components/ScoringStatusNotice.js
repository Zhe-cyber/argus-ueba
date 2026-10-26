export default function ScoringStatusNotice({ status }) {
  if (!status) return null
  return (
    <section role="status" aria-label="Scoring readiness"
      className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <strong>{status.model_ready ? 'Provisional anomaly scoring' : 'Why risk is Unknown'}</strong>
      <p className="mt-1">{status.message}</p>
      {status.model_origin && <p className="mt-1 text-xs">Model source: {status.model_origin}.</p>}
      <p className="mt-1 text-xs">{status.next_step}</p>
      <p className="mt-1 text-xs">Unknown means unscored. Low risk requires an available model score.</p>
    </section>
  )
}
