import Head from 'next/head'
import { useEffect, useMemo, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import DashboardViews from '@/components/DashboardViews'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const COLORS = { Low: '#0f766e', Medium: '#d97706', High: '#dc2626' }
const BADGES = { Low: 'bg-teal-50 text-teal-800', Medium: 'bg-amber-50 text-amber-800', High: 'bg-red-50 text-red-800' }
const number = value => Number(value).toPrecision(6)
const label = value => value.replaceAll('_', ' ')

async function read(path, signal) {
  const response = await fetch(`${API}/replay/clue/${path}`, { signal })
  if (!response.ok) throw new Error('The verified replay could not be loaded. Connected data is unchanged.')
  return response.json()
}

export default function ClueReplay() {
  const [meta, setMeta] = useState(null)
  const [rows, setRows] = useState([])
  const [split, setSplit] = useState('heldout')
  const [day, setDay] = useState('all')
  const [tier, setTier] = useState('all')
  const [selected, setSelected] = useState(null)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    read('metadata', controller.signal).then(setMeta).catch(e => { if (e.name !== 'AbortError') setError(e.message) })
    return () => controller.abort()
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setRows([]); setSelected(null); setDay('all'); setTier('all'); setPage(0); setError('')
    read(`rows?split=${split}`, controller.signal).then(data => setRows(data.rows)).catch(e => {
      if (e.name !== 'AbortError') setError(e.message)
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [split])
  const filtered = useMemo(() => rows.filter(r => (day === 'all' || r.day === day) && (tier === 'all' || r.review_priority === tier))
    .sort((a, b) => b.raw_mse - a.raw_mse || a.account.localeCompare(b.account)), [rows, day, tier])
  const daily = useMemo(() => [...new Set(rows.map(r => r.day))].sort().map(date => ({ day: date.slice(5),
    ...Object.fromEntries(Object.keys(COLORS).map(t => [t, rows.filter(r => r.day === date && r.review_priority === t).length])) })), [rows])
  const counts = Object.fromEntries(Object.keys(COLORS).map(t => [t, filtered.filter(r => r.review_priority === t).length]))
  const policy = meta?.policy

  return (<>
    <Head><title>CLUE benchmark replay — Argus</title></Head>
    <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <DashboardViews />
      <div>
        <p className="text-xs font-bold tracking-widest text-indigo-700 uppercase">Offline storage benchmark · read-only replay</p>
        <h1 className="mt-2 text-2xl font-bold text-slate-900">Real model output. Human review priorities.</h1>
        <p className="mt-2 text-sm text-slate-600">Normal benchmark data: few alerts are expected. High means unusual for this population, not confirmed compromise.</p>
      </div>
      {(error || meta?.available === false) && <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        {meta?.available === false ? meta.message : error} No sample scores are substituted.
      </div>}
      {meta?.available && <>
        <section aria-label="Replay partition" className="rounded-xl border border-slate-200 bg-white p-5">
          <div className="flex flex-wrap gap-3">
            {[['heldout', 'Held-out normal days'], ['calibration', 'Calibration diagnostics']].map(([value, title]) => (
              <button key={value} onClick={() => setSplit(value)} aria-pressed={split === value}
                className={`rounded-lg px-4 py-2 text-sm font-semibold ${split === value ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600'}`}>{title}</button>
            ))}
          </div>
          <p className="mt-3 text-sm text-slate-600">{split === 'heldout'
            ? 'Held out from this frozen model’s training and calibration. Previously inspected results are development evidence for later model revisions.'
            : 'These normal days set the thresholds. They are calibration diagnostics, not independent test results.'}</p>
          <p className="mt-2 text-xs text-slate-500">No training or validation rows. No account-switch scenarios. All counts below refer to active account-days, not people.</p>
        </section>
        <section aria-label="Review priority summary" className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {[['Account-days', filtered.length, null], ['Accounts', new Set(filtered.map(r => r.account)).size, null],
            ...Object.keys(COLORS).map(t => [`${t} priority`, counts[t], t])].map(([title, value, t]) => (
            <div key={title} className="rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-xs font-semibold text-slate-500">{title}</p>
              <p className="mt-2 text-3xl font-bold" style={{ color: t ? COLORS[t] : '#0f172a' }}>{loading ? '—' : value}</p>
            </div>
          ))}
        </section>
        {policy && <section aria-label="Frozen thresholds" className="rounded-xl border border-indigo-100 bg-indigo-50 p-4 text-sm text-indigo-950">
          <p><strong>Frozen High rule:</strong> raw MSE &gt; {number(policy.high_threshold)} (original 99th-percentile normal-calibration threshold).</p>
          <p className="mt-1"><strong>Medium:</strong> raw MSE &gt; {number(policy.medium_threshold)} and not High (calibration 95th percentile). Equality stays in the lower tier.</p>
          <p className="mt-2 text-xs">Raw reconstruction MSE is not a probability. Medium is a new review-priority policy; the AE and original High rule are unchanged.</p>
        </section>}
        <section aria-label="Daily priority distribution" className="rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="font-semibold text-slate-800">Account-days by review priority</h2>
          <p className="mt-1 text-xs text-slate-500">Full selected partition, grouped by UTC date. Table filters do not change this chart.</p>
          <div className="h-56 mt-3" role="img" aria-label={daily.map(d => `${d.day}: ${d.Low} Low, ${d.Medium} Medium, ${d.High} High`).join('; ')}>
            <ResponsiveContainer width="100%" height="100%"><BarChart data={daily}>
              <XAxis dataKey="day" /><YAxis allowDecimals={false} /><Tooltip /><Legend />
              {Object.keys(COLORS).map(t => <Bar key={t} dataKey={t} stackId="priority" fill={COLORS[t]} />)}
            </BarChart></ResponsiveContainer>
          </div>
        </section>
        <section aria-label="Scored account-days" className="rounded-xl border border-slate-200 bg-white overflow-hidden">
          <div className="p-5 flex flex-wrap gap-4 items-end">
            <div className="mr-auto"><h2 className="font-semibold text-slate-800">Scored account-days</h2><p className="text-xs text-slate-500 mt-1">Sorted by raw reconstruction error, highest first. Cohort aliases protect source identifiers.</p></div>
            <label className="text-xs text-slate-600">UTC date <select aria-label="UTC date" value={day} onChange={e => { setDay(e.target.value); setPage(0) }} className="block mt-1 rounded border p-2 bg-white">
              <option value="all">All dates</option>{meta.splits[split].dates.map(d => <option key={d}>{d}</option>)}
            </select></label>
            <label className="text-xs text-slate-600">Review priority <select aria-label="Review priority" value={tier} onChange={e => { setTier(e.target.value); setPage(0) }} className="block mt-1 rounded border p-2 bg-white">
              <option value="all">All priorities</option>{Object.keys(COLORS).map(t => <option key={t}>{t}</option>)}
            </select></label>
          </div>
          {loading ? <p role="status" className="p-8 text-slate-500">Loading frozen scores…</p> : <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr>{['Account alias', 'UTC day', 'Raw MSE', '× High threshold', 'Review priority', 'Evidence'].map(h => <th key={h} className="px-5 py-3">{h}</th>)}</tr></thead>
            <tbody>{filtered.slice(page * 20, (page + 1) * 20).map(r => <tr key={`${r.account}:${r.day}`} className="border-t border-slate-100">
              <td className="px-5 py-3 font-mono">{r.account}</td><td className="px-5 py-3">{r.day}</td><td className="px-5 py-3 font-mono">{number(r.raw_mse)}</td><td className="px-5 py-3">{r.threshold_multiple.toFixed(3)}</td>
              <td className="px-5 py-3"><span className={`rounded-full px-3 py-1 text-xs font-semibold ${BADGES[r.review_priority]}`}>{r.review_priority}</span></td>
              <td className="px-5 py-3"><button className="font-semibold text-indigo-700 hover:underline" onClick={() => setSelected(r)} aria-label={`Inspect ${r.account} on ${r.day}`}>Inspect</button></td>
            </tr>)}</tbody>
          </table>{filtered.length === 0 && <p className="p-6 text-slate-500">No account-days match these filters.</p>}</div>}
          <div className="p-4 border-t flex items-center gap-3 text-xs text-slate-500"><span className="mr-auto">{filtered.length} matching account-days</span>
            <button className="rounded border p-2 disabled:opacity-40" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Previous</button>
            <span>Page {page + 1}</span><button className="rounded border p-2 disabled:opacity-40" disabled={(page + 1) * 20 >= filtered.length} onClick={() => setPage(p => p + 1)}>Next</button>
          </div>
        </section>
        {selected && <section aria-label="Numerical reconstruction evidence" className="rounded-xl border border-slate-200 bg-white p-5">
          <div className="flex justify-between gap-3"><h2 className="font-semibold text-slate-800">{selected.account} · {selected.day} · {selected.review_priority} review priority</h2><button onClick={() => setSelected(null)} className="text-sm text-slate-500">Close</button></div>
          <p className="mt-2 text-sm text-slate-600">Feature reconstruction residuals explain the numerical MSE calculation. They are not SHAP attributions or proven causes.</p>
          <div className="mt-4 overflow-x-auto"><table className="w-full text-sm"><thead className="text-left text-xs text-slate-500"><tr><th className="py-2">Behavioural feature</th><th>Observed count</th><th>Contribution to raw MSE</th></tr></thead>
            <tbody>{Object.entries(selected.residuals).sort((a, b) => b[1] - a[1]).map(([f, contribution]) => <tr key={f} className="border-t border-slate-100"><td className="py-2">{label(f)}</td><td>{selected.features[f]}</td><td className="font-mono">{number(contribution)}</td></tr>)}</tbody>
          </table></div>
        </section>}
        <footer className="text-xs leading-relaxed text-slate-500">
          <p>{meta.attribution}. {meta.limitations}</p>
          <p className="mt-2 font-mono break-all">Model SHA256: {policy?.model_sha256}</p>
          <p>Replay is read-only. It does not create connected accounts, live alerts or investigations.</p>
        </footer>
      </>}
    </main>
  </>)
}
