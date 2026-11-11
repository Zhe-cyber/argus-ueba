import { Frame } from '@/components/WorkspaceUI'

const SIGNALS = [['New action', '0.25', 'An action (per source) not seen in the account’s recent history.'], ['New resource', '0.25', 'A resource not seen before; skipped when the account touched none that day.'], ['Unusual hours', '0.20', 'Share of the day’s events outside the account’s usual hours (usual hour ±1 h, Malaysia time).'], ['Volume', '0.15', 'Events today against the account’s median day; 8× or more counts fully.'], ['Sensitive and new', '0.15', 'A new resource whose name matches a sensitive pattern (identity, keys, admin).']]
const LIMITS = [
  'The score is a heuristic and makes no validated accuracy claim: it was not trained or checked against labelled incidents, and its weights and tiers were fixed in advance, not tuned on observed data.',
  'The lab workloads are accounts used for the pilot, not people.',
  'A workload mapping is declared, not identity proof. Mappings require recorded approval, and an approved owner does not prove who performed an action.',
  'Only observed activity is shown; completeness is unknown. Event totals do not establish complete coverage.',
  'Rule severity is the severity recorded by the detection rule. Triage labels are display context only; recorded severity and detection are unchanged.',
  'A baseline finding describes an account-day compared with the account’s own history. Findings raised by older rules are not bound to the exact triggering events.',
  'The autoencoder diagnostic stays hidden until its evaluation is finished; where shown it is experimental.',
  'A case keeps the finding as it was when linked. Account activity added to a case is related context, not proof of attribution.'
]

export default function About() {
  return <Frame title="Method & limits"><div className="max-w-3xl space-y-6 text-sm text-slate-700 leading-relaxed">
    <section className="bg-white rounded-xl border p-5 space-y-3"><h2 className="font-semibold text-base text-slate-900">How the risk score works</h2>
      <p>Each account gets a 0–100 score for each Malaysia calendar day (MYT), compared only with that account’s own previous 28 days. An account needs at least 5 earlier active days to be scored; until then it shows <b>Learning · n of 5 days</b>.</p>
      <table className="w-full text-left"><thead><tr><th className="py-1 pr-3">Signal</th><th className="py-1 pr-3">Weight</th><th className="py-1">What it looks at</th></tr></thead><tbody>{SIGNALS.map(([name, weight, text]) => <tr key={name} className="border-t align-top"><td className="py-1 pr-3 font-medium">{name}</td><td className="py-1 pr-3">{weight}</td><td className="py-1">{text}</td></tr>)}</tbody></table>
      <p>The score is the weighted average of the signals that apply. An account that regularly does new things has its novelty signals discounted, so routine variety does not look alarming.</p>
      <p><b>Tiers:</b> 60 and above is High, 30–59 Medium, below 30 Low. Each account-day scored Medium or High becomes a finding in the work queue.</p></section>
    <section className="bg-white rounded-xl border p-5 space-y-3"><h2 className="font-semibold text-base text-slate-900">Where the data comes from</h2>
      <p>Argus collects audit events from AWS CloudTrail, GitHub and Cloudflare Access, and refreshes this workspace about once a minute. The header shows <b>Live</b> while data is recent and the time of the last update otherwise. Accounts that belong to monitoring or provider plumbing are labelled infrastructure and ranked below workloads. Workload groups combine the accounts of one lab workload across providers (highest member score, plus 10 when two sources each score 30 or more).</p></section>
    <section className="bg-white rounded-xl border p-5 space-y-3"><h2 className="font-semibold text-base text-slate-900">What “provider-confirmed” means</h2>
      <p>An event is provider-confirmed when the cloud provider itself recorded it in its audit log, as opposed to something Argus inferred. Provider confirmation shows that the action happened, not who was behind the account.</p></section>
    <section className="bg-white rounded-xl border p-5 space-y-3"><h2 className="font-semibold text-base text-slate-900">Limits</h2>
      <ul className="list-disc pl-5 space-y-2">{LIMITS.map(text => <li key={text}>{text}</li>)}</ul></section>
  </div></Frame>
}
