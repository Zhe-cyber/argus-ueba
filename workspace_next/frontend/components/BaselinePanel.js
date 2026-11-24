import { useEffect, useState } from 'react'
import { display, ErrorNotice, Info, request } from '@/components/WorkspaceUI'
import { scoreParts, shortFact } from '@/lib/factFormat.mjs'

export const TIER_STYLE = { High: 'bg-rose-600 text-white', Medium: 'bg-amber-400 text-slate-900', Low: 'bg-emerald-500 text-white', Learning: 'bg-slate-300 text-slate-700' }
const TIER_TEXT = { High: 'text-rose-700', Medium: 'text-amber-700', Low: 'text-emerald-700', Learning: 'text-slate-500' }

// 14 calendar slots ending at the newest scored day, oldest first; inactive days stay empty.
const slots = days => {
  const end = Date.parse(days[0].day + 'T00:00:00Z'), by = Object.fromEntries(days.map(d => [d.day, d]))
  return Array.from({ length: 14 }, (_, i) => { const day = new Date(end - (13 - i) * 864e5).toISOString().slice(0, 10); return [day, by[day]] })
}

// `days` = prior observed active days; shown for Learning accounts as "Learning · n of 5 days".
export function ScoreChip({ baseline, days }) {
  const tier = baseline?.tier || 'Learning'
  return <span className={'inline-block rounded px-2 py-0.5 text-xs font-medium ' + (TIER_STYLE[tier] || TIER_STYLE.Learning)}>{tier === 'Learning' ? (Number.isInteger(days) ? `Learning · ${Math.min(days, 5)} of 5 days` : 'Learning') : `${baseline?.score ?? '–'} · ${tier}`}</span>
}

// L10 comparator: the live autoencoder v2 score for one persona account-day. Display only; it never raises alerts.
export function MlScoreRow({ account, day }) {
  const [m, setM] = useState(null)
  useEffect(() => {
    let active = true; setM(null)
    request('/workspace/ml-score?account=' + encodeURIComponent(account) + '&day=' + day).then(v => { if (active) setM(v) }).catch(() => { if (active) setM({ status: 'unavailable' }) })
    return () => { active = false }
  }, [account, day])
  if (!m) return null
  return <div className="border-t pt-2 text-sm" data-testid="ml-score-row" aria-label="ML anomaly score">
    <p className="text-xs text-slate-500">Second opinion (autoencoder){m.status === 'scored' && <> · <span className="font-semibold text-slate-900">{m.score.toFixed(2)}</span> · <span className={m.flagged ? 'text-rose-700' : 'text-emerald-700'}>{m.flagged ? 'above normal' : 'within normal'}</span></>}<Info label="About the ML anomaly score">Unsupervised model for the lab persona accounts (AWS roles and Cloudflare service tokens), trained on their normal days up to 12 Nov; compares each day with that account’s own history; shown for comparison; does not raise alerts.</Info></p>
    {m.status === 'scored' ? <details className="text-xs text-slate-500"><summary className="cursor-pointer">Why</summary>{m.top_features.length > 0 && <p>driven by {m.top_features.map(f => `${f.label} ${Math.round(f.share * 100)}%`).join(', ')}</p>}
      {m.flagged_secondary != null && <p data-testid="ml-score-secondary">above the model’s normal range at the 5% setting: {m.flagged_secondary ? 'yes' : 'no'}</p>}</details>
      : <p className="text-xs text-slate-500">{m.status === 'unavailable' ? 'ML score unavailable.' : m.status === 'not_applicable' ? 'Not applicable: ' + m.reason : 'Not scored: ' + m.reason}</p>}
  </div>
}

const PART_COLOR = { new_action: 'bg-indigo-500', new_resource: 'bg-sky-500', unusual_hours: 'bg-amber-500', volume: 'bg-teal-500', sensitive_new: 'bg-rose-500' }

// How the five signals add up to the score: one segment per signal on a 0-100 bar, tier lines at 30 and 60.
export function ScoreBreakdown({ signals, score }) {
  const r = scoreParts(signals, score)
  if (!r) return null
  const shown = r.parts.filter(p => p.pts > 0)
  return <div data-testid="score-breakdown" aria-label="Score breakdown">
    <p className="text-xs font-medium text-slate-500 mb-1">How the score adds up<Info label="About the breakdown">Each signal is 0 to 1 and is multiplied by its weight (25/25/20/15/15); the parts add up to the score. Lines mark Medium (30) and High (60).</Info></p>
    <div className="relative h-5 w-full rounded bg-slate-100 flex overflow-hidden">
      {shown.map(p => <div key={p.key} className={PART_COLOR[p.key]} style={{ width: p.points + '%' }} title={`${p.label}: +${p.pts} of ${Math.round(p.max)}`} />)}
      {r.floor > 0 && <div className="bg-slate-400" style={{ width: r.floor + '%' }} title={`Sensitive minimum: +${r.floor}`} />}
      {[30, 60].map(t => <div key={t} className="absolute top-0 h-full border-l-2 border-slate-900" style={{ left: t + '%' }} />)}
    </div>
    <div className="relative h-4 text-[10px] text-slate-500">{[[30, 'Medium 30'], [60, 'High 60']].map(([t, l]) => <span key={t} className="absolute -translate-x-1/2" style={{ left: t + '%' }}>{l}</span>)}</div>
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-700">
      {shown.map(p => <li key={p.key} className="flex items-center gap-1.5"><span className={'inline-block h-2.5 w-2.5 rounded-sm ' + PART_COLOR[p.key]} />{p.label} <span className="font-semibold">+{p.pts}</span></li>)}
      {r.floor > 0 && <li className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-slate-400" />Sensitive minimum <span className="font-semibold">+{r.floor}</span></li>}
      {!shown.length && !r.floor && <li>No signal fired today.</li>}
    </ul>
  </div>
}

// On-demand AI suggestion (Gemini / DeepSeek / Groq). Advisory: never changes the score, tier or status.
export function AiSuggestion({ findingId }) {
  const [state, setState] = useState({})
  useEffect(() => setState({}), [findingId])
  const ask = () => { setState({ loading: true }); request(`/workspace/findings/${findingId}/ai-suggestion`, {}).then(r => setState({ r })).catch(e => setState({ error: e.message })) }
  const bold = line => line.split(/\*\*(.+?)\*\*/).map((t, i) => i % 2 ? <strong key={i}>{t}</strong> : t)
  return <section className="border rounded-lg p-4 space-y-2" aria-label="AI suggestion" data-testid="ai-suggestion">
    <div className="flex items-center justify-between gap-2"><p className="text-xs text-slate-500">AI suggestion · advisory only<Info label="About the AI suggestion">Sends only this finding's score, breakdown and facts (account ids, IPs and e-mails masked) to a language model, which suggests what to check. It never changes the score, tier or status; you decide.</Info></p>
      {!state.r && <button type="button" onClick={ask} disabled={state.loading} className="rounded border px-3 py-1 text-sm hover:bg-slate-50 disabled:opacity-60">{state.loading ? 'Thinking…' : 'Suggest next steps'}</button>}</div>
    {state.error && <p className="text-sm text-rose-700">{state.error}</p>}
    {state.r && <><div className="text-sm space-y-1">{state.r.text.split(/\r?\n/).filter(l => l.trim()).map((l, i) => <p key={i}>{bold(l.replace(/^\s*[*-]\s+/, '• ').replace(/`/g, ''))}</p>)}</div>
      <p className="text-xs text-slate-500">Generated by {state.r.model}. Check against the facts above before acting.</p></>}
  </section>
}

// `day` (YYYY-MM-DD, MYT) shows that account-day instead of the newest one; `compact` hides the 14-day bars.
export default function BaselinePanel({ account, day = '', compact = false }) {
  const [days, setDays] = useState(null), [error, setError] = useState(null), [drift, setDrift] = useState(null)
  useEffect(() => {
    let active = true; setDays(null); setError(null); setDrift(null)
    request('/workspace/drift?account=' + encodeURIComponent(account)).then(v => { if (active) setDrift(v.drift) }).catch(() => {})
    request('/workspace/baseline?days=' + (day ? 60 : 14) + '&account=' + encodeURIComponent(account)).then(v => { if (active) setDays(v) }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [account, day])
  const today = day ? days?.find(d => d.day === day) : days?.[0]
  return <section className="border rounded-lg p-4 space-y-3" aria-label="Baseline risk score">
    <p className="text-xs text-slate-500">Risk score · compared with this account's last 28 days<Info>Baseline risk score v1 — compared with this account's own last 28 days. Heuristic; not a validated accuracy claim.</Info></p>
    <ErrorNotice error={error} />
    {!days ? !error && <p className="text-sm">Loading baseline…</p> : !today ? <p className="text-sm">{day ? `No scored activity for this account on ${day}.` : 'No activity recorded for this account.'}</p> : <>
      <div className="flex items-baseline gap-3"><span className={'text-5xl font-semibold ' + TIER_TEXT[today.tier]}>{today.score ?? '–'}</span><span className={'rounded px-2 py-0.5 text-sm ' + TIER_STYLE[today.tier]}>{today.tier}</span><span className="text-xs text-slate-500">{today.day}{today.partial ? ' (day in progress)' : ''} · {today.events_today} events · {today.history_days} prior active days</span></div>
      <ScoreBreakdown signals={today.signals} score={today.score} />
      {today.facts.length ? <div className="text-sm space-y-2">{[['new', 'New in the last 28 days'], ['pattern', "Today's pattern"], ['rest', null]].map(([g, title]) => { const items = today.facts.map(f => shortFact(f)).filter(x => g === 'rest' ? x.group !== 'new' && x.group !== 'pattern' : x.group === g); return items.length > 0 && <div key={g}>{title && <p className="text-xs font-medium text-slate-500">{title}</p>}<ul className="list-disc pl-5 space-y-1">{items.map((x, i) => <li key={i}>{display(x.text)}</li>)}</ul></div> })}</div> : <ul className="text-sm list-disc pl-5 space-y-1"><li>Nothing unusual against this account's own history.</li></ul>}
      <MlScoreRow account={account} day={today.day} />
      <details className="text-sm"><summary className="cursor-pointer text-xs text-slate-600">More: drift and last 14 days</summary>
      {drift && <div className="text-xs text-slate-600 border-t pt-2" aria-label="Behaviour drift"><p className="font-medium">Behaviour drift · observation, not a risk score ({drift.day}){drift.monitoring_infrastructure ? ' · monitoring infrastructure' : ''}</p><ul className="list-disc pl-5">{drift.facts.map((f, i) => <li key={i}>{display(f)}</li>)}</ul></div>}
      {!compact && <div className="mt-2"><p className="text-xs text-slate-500 mb-1">Last 14 days (newest on the right)</p><div className="flex items-end gap-1 h-12">{slots(days).map(([day, d]) => d ? <div key={day} title={`${day}: ${d.score ?? 'Learning'} (${d.tier})`} className={'w-4 rounded-sm ' + TIER_STYLE[d.tier]} style={{ height: Math.max(6, d.score ?? 8) + '%' }} /> : <div key={day} title={day + ': no activity'} className="w-4 rounded-sm bg-slate-100" style={{ height: '6%' }} />)}</div></div>}
      </details>
    </>}
  </section>
}
