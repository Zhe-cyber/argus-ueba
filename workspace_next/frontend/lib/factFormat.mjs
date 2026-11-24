// Presentation-only shortening of the fixed fact strings from backend/baseline_scorer.py (frozen).
// Unknown strings pass through verbatim; never edit backend text to make a rule match.
const RULES = [
  [/^(\d+) action kind\(s\) never seen in the last \d+ days: (.*)$/s, 'new', (n, x) => `${n} new action(s): ${x}`],
  [/^(\d+) resource\(s\) never seen in the last \d+ days: (.*)$/s, 'new', (n, x) => `${n} new resource(s): ${x}`],
  [/^(\d+) sensitive resource\(s\) not seen before: (.*)$/s, 'new', (n, x) => `${n} new sensitive resource(s): ${x}`],
  [/^(\d+)% of today's events fall outside this account's usual hours \(MYT\)$/, 'pattern', p => `${p}% outside usual hours`],
  [/^(\d+) events today; median active day is (\S+) \(([\d.]+)[x×]\)$/, 'pattern', (n, m, r) => `${n} events · ${r}× a usual day (median ${m})`],
  [/^This account showed new (.+) on (\d+) of (\d+) recent active days, so novelty is discounted\.$/, 'note', (l, h, n) => `Novelty discounted: new ${l} on ${h} of ${n} recent days`],
]

export function shortFact(text) {
  for (const [re, group, fmt] of RULES) { const m = re.exec(text); if (m) return { group, text: fmt(...m.slice(1)) } }
  return { group: 'other', text }
}

const SOURCES = { aws_cloudtrail: 'AWS', cloudflare_access: 'Cloudflare', github_audit: 'GitHub' }
export function sourceTag(text) {
  const m = /^\[([^\]]+)\] (.*)$/s.exec(text)
  return m ? { source: SOURCES[m[1]] || m[1], text: m[2] } : { source: null, text }
}

// Score breakdown: each signal's share of the 0-100 score, the same sum backend/baseline_scorer.py score_day() uses
// (weights renormalise over available signals). ponytail: weights copied from the frozen v1.2 scorer; fetch them from
// /workspace/method if the weights ever change.
const WEIGHTS = { new_action: 25, new_resource: 25, unusual_hours: 20, volume: 15, sensitive_new: 15 }
const LABELS = { new_action: 'New actions', new_resource: 'New resources', unusual_hours: 'Unusual hours', volume: 'Volume', sensitive_new: 'New sensitive resource' }
export function scoreParts(signals, score) {
  const avail = Object.keys(WEIGHTS).filter(k => signals?.[k] != null)
  const total = avail.reduce((s, k) => s + WEIGHTS[k], 0)
  if (!total) return null
  const parts = avail.map(k => ({ key: k, label: LABELS[k], points: 100 * WEIGHTS[k] * signals[k] / total, max: 100 * WEIGHTS[k] / total }))
  const sum = parts.reduce((s, p) => s + p.points, 0)
  const floor = score != null && (signals.sensitive_new ?? 0) >= 0.5 && score > Math.round(sum) ? score - Math.round(sum) : 0
  // whole-number points that add up exactly to the stored score (largest remainder; stored signals are rounded to
  // 3 decimals, so their own sum can be 1 off), so the legend always sums to the number shown
  let left = (score != null ? score - floor : Math.round(sum)) - parts.reduce((s, p) => s + Math.floor(p.points), 0)
  parts.forEach(p => { p.pts = Math.floor(p.points) })
  ;[...parts].sort((a, b) => (b.points % 1) - (a.points % 1)).forEach(p => { if (left > 0) { p.pts++; left-- } else if (left < 0 && p.pts > 0) { p.pts--; left++ } })
  return { parts, floor }
}

// Suggested MITRE ATT&CK techniques for a finding, from its own title and details text. Display only: a hint for the
// analyst in industry vocabulary, never used for scoring. ponytail: keyword rules; extend the table when new facts appear.
const ATTACK = [
  [/outside (this account's )?(business|office|usual) hours|first-time action|ConsoleLogin|AssumeRole/i, 'T1078.004', 'Valid Accounts: Cloud Accounts'],
  [/ListObjects|ListBuckets|HeadObject|HeadBucket|GetBucket[A-Za-z]*/, 'T1619', 'Cloud Storage Object Discovery'],
  [/Describe[A-Z][A-Za-z]*|ListRoles|ListUsers|ListPolicies|GetAccountAuthorizationDetails/, 'T1580', 'Cloud Infrastructure Discovery'],
  [/\bGetObject\b/, 'T1530', 'Data from Cloud Storage'],
]
export function attackTags(finding) {
  const text = [finding?.title, finding?.display_title, JSON.stringify(finding?.details ?? {})].join(' ')
  return ATTACK.filter(([re]) => re.test(text)).map(([, id, name]) => ({ id, name }))
}
