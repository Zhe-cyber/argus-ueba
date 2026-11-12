import { useEffect, useState } from 'react'
import { Frame, request } from '@/components/WorkspaceUI'

const SIGNALS = [['New action', '0.25', 'An action (per source) not seen in the account’s recent history.'], ['New resource', '0.25', 'A resource not seen before; skipped when the account touched none that day.'], ['Unusual hours', '0.20', 'Share of the day’s events outside the account’s usual hours (usual hour ±1 h, Malaysia time).'], ['Volume', '0.15', 'Events today against the account’s median day; 8× or more counts fully.'], ['Sensitive and new', '0.15', 'A new resource whose name matches a sensitive pattern (identity, keys, admin).']]
const LIMITS = [
  'The score is a heuristic and makes no validated accuracy claim: it was not trained or checked against labelled incidents, and its weights and tiers were fixed in advance, not tuned on observed data.',
  'The lab workloads are accounts used for the pilot, not people.',
  'A workload mapping is declared, not identity proof. Mappings require recorded approval, and an approved owner does not prove who performed an action.',
  'Only observed activity is shown; completeness is unknown. Event totals do not establish complete coverage.',
  'Rule severity is the severity recorded by the detection rule. Triage labels are display context only; recorded severity and detection are unchanged.',
  'A baseline finding describes an account-day compared with the account’s own history. Findings raised by older rules are not bound to the exact triggering events.',
  'The older autoencoder diagnostic stays hidden until its evaluation is finished; where shown it is experimental. The ML anomaly score below is a separate comparator.',
  'A case keeps the finding as it was when linked. Account activity added to a case is related context, not proof of attribution.'
]

function SensitivePatterns() {
  const [m, setM] = useState(null)
  useEffect(() => { let on = true; request('/workspace/method').then(v => { if (on) setM(v) }).catch(() => { if (on) setM({ error: true }) }); return () => { on = false } }, [])
  if (!m) return <p>Loading the active patterns…</p>
  if (m.error) return <p>The active pattern list is unavailable.</p>
  const deployed = Object.entries(m.sensitive.deployment || {}).filter(([, globs]) => globs.length)
  return <>
    <p>A resource counts as sensitive when its name contains a built-in pattern, or when it matches a pattern in this deployment’s list for that provider (<code>*</code> matches anything).{m.sensitive.deployment_file_loaded ? '' : ' The deployment list could not be read, so only the built-in patterns are active.'}</p>
    {deployed.length > 0 && <ul className="list-disc pl-5">{deployed.map(([provider, globs]) => <li key={provider}><b>{provider}</b>: {globs.map(g => <code key={g} className="mr-2">{g}</code>)}</li>)}</ul>}
    <p className="text-xs text-slate-500">Built-in: {m.sensitive.built_in.map(p => <code key={p} className="mr-2">{p}</code>)}</p>
    <p className="text-xs text-slate-500">Method {m.version}{m.method_sha256 ? ` · binding ${m.method_sha256.slice(0, 12)}` : ''}</p>
  </>
}

export default function About() {
  return <Frame title="Method & limits"><div className="max-w-3xl space-y-6 text-sm text-slate-700 leading-relaxed">
    <section className="bg-white rounded-xl border p-5 space-y-3"><h2 className="font-semibold text-base text-slate-900">How the risk score works</h2>
      <p>Each account gets a 0–100 score for each Malaysia calendar day (MYT), compared only with that account’s own previous 28 days. An account needs at least 5 earlier active days to be scored; until then it shows <b>Learning · n of 5 days</b>.</p>
      <table className="w-full text-left"><thead><tr><th className="py-1 pr-3">Signal</th><th className="py-1 pr-3">Weight</th><th className="py-1">What it looks at</th></tr></thead><tbody>{SIGNALS.map(([name, weight, text]) => <tr key={name} className="border-t align-top"><td className="py-1 pr-3 font-medium">{name}</td><td className="py-1 pr-3">{weight}</td><td className="py-1">{text}</td></tr>)}</tbody></table>
      <p>The score is the weighted average of the signals that apply. An account that regularly does new things has its novelty signals discounted, so routine variety does not look alarming.</p>
      <p><b>Tiers:</b> 60 and above is High, 30–59 Medium, below 30 Low. Each account-day scored Medium or High becomes a finding in the work queue.</p></section>
    <section className="bg-white rounded-xl border p-5 space-y-3"><h2 className="font-semibold text-base text-slate-900">ML anomaly score (autoencoder v2)</h2>
      <p>Beside the risk score, each lab persona account-day (the six AWS persona roles and the six Cloudflare persona service tokens) gets an ML anomaly score from a small unsupervised autoencoder (9-6-3-6-9, 168 weights). Its nine inputs compare the day with that account’s own previous active days (up to 28 days back, at least 5; before that the day shows Learning): number of events, distinct actions, distinct resources, share of activity outside the account’s usual hours, new actions, volume against a usual day, share of new resources, and how far the mix of actions and the hours of activity moved from the account’s history.</p>
      <p>It was trained on the persona accounts’ own days up to 12 November 2026: fitted on days up to 8 Nov, checkpoint chosen on 9–10 Nov, normal range set on 11–12 Nov. A day is <b>above the model’s normal range</b> when its score is higher than the threshold that at most 5% of those calibration days exceeded. The explanation shows which inputs contributed most of the reconstruction error. A second, quieter setting (the “5% setting”, declared on 13 November before any test scenario) uses the threshold that at most 5% of all 104 scored persona days up to 12 November exceeded; it is reported alongside the main setting and does not raise alerts either.</p>
      <p>It is shown for comparison only: it does not raise alerts, change the risk score or its tiers, and it was trained on machine workloads, not people. Other accounts show “not applicable”.</p></section>
    <section className="bg-white rounded-xl border p-5 space-y-3"><h2 className="font-semibold text-base text-slate-900">Sensitive resources</h2><SensitivePatterns /></section>
    <section className="bg-white rounded-xl border p-5 space-y-3"><h2 className="font-semibold text-base text-slate-900">Where the data comes from</h2>
      <p>Argus collects audit events from AWS CloudTrail, GitHub and Cloudflare Access, and refreshes this workspace about once a minute. The header shows <b>Live</b> while data is recent and the time of the last update otherwise. Accounts that belong to monitoring or provider plumbing are labelled infrastructure and ranked below workloads. Workload groups combine the accounts of one lab workload across providers (highest member score, plus 10 when two sources each score 30 or more).</p></section>
    <section className="bg-white rounded-xl border p-5 space-y-3"><h2 className="font-semibold text-base text-slate-900">What “provider-confirmed” means</h2>
      <p>An event is provider-confirmed when the cloud provider itself recorded it in its audit log, as opposed to something Argus inferred. Provider confirmation shows that the action happened, not who was behind the account.</p></section>
    <section className="bg-white rounded-xl border p-5 space-y-3"><h2 className="font-semibold text-base text-slate-900">Limits</h2>
      <ul className="list-disc pl-5 space-y-2">{LIMITS.map(text => <li key={text}>{text}</li>)}</ul></section>
  </div></Frame>
}
