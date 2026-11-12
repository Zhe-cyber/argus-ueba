import { useEffect, useState } from 'react'
import { display, ErrorNotice, Info, request } from '@/components/WorkspaceUI'

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
    <p className="text-xs text-slate-500">ML anomaly score (autoencoder v2)<Info label="About the ML anomaly score">Unsupervised model for the lab persona accounts (AWS roles and Cloudflare service tokens), trained on their normal days up to 12 Nov; compares each day with that account’s own history; shown for comparison; does not raise alerts.</Info></p>
    {m.status === 'scored' ? <p><span className="font-semibold">{m.score.toFixed(3)}</span> · <span className={m.flagged ? 'text-rose-700' : 'text-emerald-700'}>{m.range} the model’s normal range</span>{m.top_features.length > 0 && <span className="text-xs text-slate-500"> · driven by {m.top_features.map(f => `${f.label} ${Math.round(f.share * 100)}%`).join(', ')}</span>}</p>
      : <p className="text-xs text-slate-500">{m.status === 'unavailable' ? 'ML score unavailable.' : m.status === 'not_applicable' ? 'Not applicable: ' + m.reason : 'Not scored: ' + m.reason}</p>}
  </div>
}

// `day` (YYYY-MM-DD, MYT) shows that account-day instead of the newest one; `compact` hides the 14-day bars.
export default function BaselinePanel({ account, day = '', compact = false }) {
  const [days, setDays] = useState(null), [error, setError] = useState(null)
  useEffect(() => {
    let active = true; setDays(null); setError(null)
    request('/workspace/baseline?days=' + (day ? 60 : 14) + '&account=' + encodeURIComponent(account)).then(v => { if (active) setDays(v) }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [account, day])
  const today = day ? days?.find(d => d.day === day) : days?.[0]
  return <section className="border rounded-lg p-4 space-y-3" aria-label="Baseline risk score">
    <p className="text-xs text-slate-500">Risk score · compared with this account's last 28 days<Info>Baseline risk score v1 — compared with this account's own last 28 days. Heuristic; not a validated accuracy claim.</Info></p>
    <ErrorNotice error={error} />
    {!days ? !error && <p className="text-sm">Loading baseline…</p> : !today ? <p className="text-sm">{day ? `No scored activity for this account on ${day}.` : 'No activity recorded for this account.'}</p> : <>
      <div className="flex items-baseline gap-3"><span className={'text-5xl font-semibold ' + TIER_TEXT[today.tier]}>{today.score ?? '–'}</span><span className={'rounded px-2 py-0.5 text-sm ' + TIER_STYLE[today.tier]}>{today.tier}</span><span className="text-xs text-slate-500">{today.day}{today.partial ? ' (day in progress)' : ''} · {today.events_today} events · {today.history_days} prior active days</span></div>
      <ul className="text-sm list-disc pl-5 space-y-1">{today.facts.length ? today.facts.map((f, i) => <li key={i}>{display(f)}</li>) : <li>Nothing unusual against this account's own history.</li>}</ul>
      <MlScoreRow account={account} day={today.day} />
      {!compact && <div><p className="text-xs text-slate-500 mb-1">Last 14 days (newest on the right)</p><div className="flex items-end gap-1 h-12">{slots(days).map(([day, d]) => d ? <div key={day} title={`${day}: ${d.score ?? 'Learning'} (${d.tier})`} className={'w-4 rounded-sm ' + TIER_STYLE[d.tier]} style={{ height: Math.max(6, d.score ?? 8) + '%' }} /> : <div key={day} title={day + ': no activity'} className="w-4 rounded-sm bg-slate-100" style={{ height: '6%' }} />)}</div></div>}
    </>}
  </section>
}
