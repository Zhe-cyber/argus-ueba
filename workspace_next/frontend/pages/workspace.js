import { Fragment, useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import Link from 'next/link'
import DiagnosticPanel, { activityDay } from '@/components/DiagnosticPanel'
import BaselinePanel, { ScoreChip } from '@/components/BaselinePanel'
import { display, Frame, Drawer, Facts, ErrorNotice, FieldError, Info, request, useCommand, useSession, canChange, field, button, secondary, when } from '@/components/WorkspaceUI'
const TRIAGE = { review_first: 'Review first', automation_context: 'Automation account', office_hours_context: 'Office hours', infrastructure_context: 'Monitoring infrastructure' }
// The date filters are typed in Malaysia time (MYT, UTC+8) and sent to the API as UTC.
const mytToUtc = value => { const t = Date.parse((value.length === 16 ? value + ':00' : value) + '+08:00'); return Number.isFinite(t) ? new Date(t).toISOString() : '' }
const ACTIONS = [['Acknowledged', 'Acknowledge'], ['Resolved', 'Resolve'], ['False Positive', 'False positive'], ['Open', 'Reopen']]

function StatusActions({ id, finding, onDone }) {
  const [reason, setReason] = useState(''), [busy, setBusy] = useState(false), session = useSession()
  const [error, setError] = useState(null), [tried, setTried] = useState(false)
  async function change(status) {
    setTried(true); setError(null)
    if (!reason.trim()) return
    setBusy(true)
    try { await request(`/findings/${id}/status`, { status, reason: reason.trim() }); setTried(false); setReason(''); await onDone() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  if (!canChange(session)) return <section className="border-t pt-3" aria-label="Finding status"><h3 className="text-sm font-semibold">Status: {finding.status}</h3></section>
  return <section className="border-t pt-3 space-y-2" aria-label="Finding status"><h3 className="text-sm font-semibold">Status: {finding.status}</h3><ErrorNotice error={error} />
    <label className="block text-sm">Reason<input maxLength={2000} className={field} value={reason} onChange={e => setReason(e.target.value)} /><FieldError show={tried && !reason.trim()}>Reason is required.</FieldError></label>
    <div className="flex flex-wrap gap-2">{ACTIONS.map(([status, label]) => <button key={status} className={secondary} disabled={busy || finding.status === status} onClick={() => change(status)}>{label}</button>)}</div></section>
}

// The model diagnostic only appears when a reviewed artifact is configured.
function Diagnostic({ finding, id }) {
  const [configured, setConfigured] = useState(false)
  const subject = finding.diagnostic_subject, day = activityDay(finding.rule_event_time_utc || finding.created_at)
  useEffect(() => {
    let active = true
    if (!subject || !day) return () => { active = false }
    const query = new URLSearchParams({ source: subject.source, scope: subject.source_account_id, account: subject.account_key, day })
    request('/workspace/diagnostic-availability?' + query).then(v => { if (active) setConfigured(!(v.status === 'unavailable' && !v.reason_code)) }).catch(() => { if (active) setConfigured(false) })
    return () => { active = false }
  }, [id])
  return configured ? <details className="border-t pt-3"><summary className="cursor-pointer text-sm">Account-day diagnostic context</summary><DiagnosticPanel key={id} account={subject} initialDay={activityDay(finding.rule_event_time_utc)} /></details> : null
}

function FindingDrawer({ id, close, changed }) {
  const router = useRouter()
  const [finding, setFinding] = useState(null), [error, setError] = useState(null)
  const [title, setTitle] = useState(''), [owner, setOwner] = useState(''), session = useSession()
  const [reason, setReason] = useState(''), [includeAccount, setIncludeAccount] = useState(true), [tried, setTried] = useState(false)
  const [mode, setMode] = useState(null), [cases, setCases] = useState([]), [selected, setSelected] = useState(''), [cursor, setCursor] = useState(null)
  const command = useCommand()
  const reload = () => request('/findings/' + id).then(row => { setFinding(row); return row })
  useEffect(() => { let active = true; request('/findings/' + id).then(row => { if (active) { setFinding(row); setTitle(display((row.display_title || row.title) + ' — ' + row.account_label)) } }).catch(e => { if (active) setError(e.message) }); return () => { active = false } }, [id])
  async function loadCases(more = false) {
    try {
      const params = new URLSearchParams({ limit: '50' })
      if (more && cursor) { params.set('before_time', cursor[0]); params.set('before_id', cursor[1]) }
      const result = await request('/cases?' + params)
      setCases(previous => more ? [...previous, ...result.cases] : result.cases); setCursor(result.next_cursor)
    } catch (e) { setError(e.message) }
  }
  function submit(event) {
    event.preventDefault()
    setTried(true)
    const target = cases.find(row => row.id === selected)
    if (!reason.trim() || (mode === 'new' && !title.trim()) || (mode === 'existing' && !target)) return
    command.run(mode === 'new' ? '/cases/from-finding' : `/cases/${selected}/links`, mode === 'new'
      ? { title, owner, finding_id: Number(id), reason, include_account: includeAccount }
      : { expected_version: target.version, kind: 'finding', target: String(id), reason }, 'POST', row => router.push('/cases/' + row.id))
  }
  const day = finding && (finding.origin === 'baseline' ? finding.details?.day : activityDay(finding.rule_event_time_utc || finding.created_at))
  return <Drawer title={'Finding #' + id} close={close}><ErrorNotice error={error || command.error} />{!finding ? <p>Loading evidence…</p> : <>
    <h3 className="font-semibold text-slate-900">{display(finding.display_title || finding.title)}</h3><p className="text-xs text-slate-500">{finding.severity} · {finding.origin} · {finding.status} · {when(finding.created_at)}</p>
    <StatusActions id={id} finding={finding} onDone={async () => { await reload(); changed() }} />
    {day && <BaselinePanel key={'b' + id} account={finding.user_id} day={day} compact />}
    <Facts value={{ account: finding.account_label, triage: TRIAGE[finding.triage], event_time_malaysia: finding.event_time_myt ? when(finding.event_time_myt) + (finding.in_myt_office_hours ? ' (inside office hours, Mon–Fri 08:00–18:00)' : ' (outside office hours, Mon–Fri 08:00–18:00)') : null, rule_window: finding.rule_window, event_time_utc: finding.rule_event_time_utc, ...finding.details }} />
    <p className="text-xs text-slate-500">{finding.entity_context === 'service_or_workload' ? 'Service/workload account. ' : ''}{finding.history_context === 'limited_observed_history' ? 'Limited observed history. ' : ''}{finding.origin === 'baseline' ? 'Compared with this account’s own history.' : 'Rule-based finding.'}<Info label="About this finding">{finding.history_context === 'limited_observed_history' ? 'Limited observed history; novelty alone does not establish misuse. ' : ''}{finding.origin === 'baseline' ? 'A baseline finding describes this account-day compared with the account’s own history. ' : 'Exact triggering events are not bound to this legacy signal. '}Account activity added to a case is related context. Triage is display context only; recorded severity and detection are unchanged.</Info></p>
    <Diagnostic finding={finding} id={id} />
    {!canChange(session) ? null : !mode ? <div data-write-action className="flex gap-2"><button className={button} onClick={() => setMode('new')}>Create case</button><button className={secondary} onClick={() => { setMode('existing'); loadCases() }}>Add to case</button></div> : <form noValidate onSubmit={submit} className="border-t pt-4 space-y-3">
      <h3 className="font-semibold">{mode === 'new' ? 'New case' : 'Existing case'}</h3>
      {mode === 'new' ? <><label className="block text-sm">Title<input maxLength={240} className={field} value={title} onChange={e => setTitle(e.target.value)} /><FieldError show={tried && !title.trim()}>Title is required.</FieldError></label><label className="block text-sm">Owner<input maxLength={200} className={field} value={owner} onChange={e => setOwner(e.target.value)} /></label><label className="flex gap-2 text-sm"><input type="checkbox" checked={includeAccount} onChange={e => setIncludeAccount(e.target.checked)} />Include this account’s activity as related context</label></> : <><label className="block text-sm">Case<select className={field} value={selected} onChange={e => setSelected(e.target.value)}><option value="">Select an open case</option>{cases.filter(row => row.status !== 'Closed').map(row => <option key={row.id} value={row.id}>{display(row.display_title || row.title)}</option>)}</select><FieldError show={tried && !selected}>Choose a case.</FieldError></label><button type="button" className={secondary} onClick={() => loadCases(false)}>Refresh cases</button>{cursor && <button type="button" className={secondary} onClick={() => loadCases(true)}>Load more cases</button>}</>}
      <label className="block text-sm">Reason<textarea maxLength={2000} className={field} value={reason} onChange={e => setReason(e.target.value)} /><FieldError show={tried && !reason.trim()}>Reason is required.</FieldError></label>
      <div className="flex gap-2"><button disabled={command.busy} className={button}>{command.busy ? 'Saving…' : mode === 'new' ? 'Create case with finding' : 'Link finding'}</button><button type="button" disabled={command.busy} className={secondary} onClick={() => { setMode(null); setTried(false) }}>Back</button></div>
    </form>}</>}</Drawer>
}

function Title({ row }) {
  const action = row.details?.action || (row.origin === 'baseline' ? row.details?.facts?.[0] : null)
  return <>{display(row.display_title || row.title)}{action && <p className="text-xs text-slate-700 mt-1">{display(String(action))}</p>}<p className="text-xs text-slate-500">#{row.id} · {row.origin} · {row.status}</p><p className="text-xs text-slate-500">{row.entity_context === 'service_or_workload' ? 'Service / workload' : 'Other / unclassified'}{row.history_context === 'limited_observed_history' ? ' · limited observed history' : ''}</p>{row.triage && <span className={'inline-block mt-1 rounded px-2 py-0.5 text-xs ' + (row.triage === 'review_first' ? 'bg-amber-100 text-amber-900' : 'bg-slate-100 text-slate-600')}>{TRIAGE[row.triage]}</span>}</>
}

export default function WorkQueue() {
  const router = useRouter(), [data, setData] = useState(null), [error, setError] = useState(null)
  const [tier, setTier] = useState(''), [grouped, setGrouped] = useState(true), [expanded, setExpanded] = useState({}), [reloads, setReloads] = useState(0)
  const learningView = router.query.learning === 'only' ? 'only' : 'exclude'
  const category = router.query.category || 'security', status = router.query.status || 'Open'
  useEffect(() => {
    if (!router.isReady) return
    let active = true; setData(null); setError(null)
    const params = new URLSearchParams({ limit: '500', category, status, learning: learningView })
    for (const key of ['provider', 'account', 'entity_context', 'triage', 'before_time', 'before_id']) if (router.query[key]) params.set(key, router.query[key])
    for (const key of ['start', 'end']) if (router.query[key] && mytToUtc(router.query[key])) params.set(key, mytToUtc(router.query[key]))
    request('/findings?' + params).then(value => { if (active) setData(value) }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [router.isReady, router.asPath, reloads])
  // Baseline score sort/filter cover the loaded page of up to 500 findings (the API pages by time beyond that).
  const rows = (data?.findings || []).filter(r => !tier || (r.baseline?.tier || 'Learning') === tier)
    .sort((a, b) => (a.infrastructure ? 1 : 0) - (b.infrastructure ? 1 : 0) || (b.baseline?.score ?? -1) - (a.baseline?.score ?? -1) || Date.parse(b.created_at) - Date.parse(a.created_at))
  const buckets = {}
  for (const row of rows) (buckets[row.user_id + '|' + row.alert_type] ||= []).push(row)
  const groups = Object.entries(buckets).map(([key, list]) => ({ key, list, top: list[0], latest: list.reduce((a, b) => Date.parse(b.created_at) > Date.parse(a.created_at) ? b : a).created_at }))
  function filter(key, value) { const query = { ...router.query, [key]: value }; delete query.before_time; delete query.before_id; delete query.finding; router.push({ pathname: '/workspace', query }) }
  function close() { const query = { ...router.query }; delete query.finding; router.push({ pathname: '/workspace', query }, undefined, { scroll: false }) }
  const review = row => <button className={secondary} onClick={() => router.push({ pathname: '/workspace', query: { ...router.query, finding: row.id } }, undefined, { scroll: false })}>Review #{row.id}</button>
  const plain = (row, nested) => <tr key={row.id} className={'border-t' + (nested ? ' bg-slate-50' : '')}><td className={'p-3 max-w-sm' + (nested ? ' pl-8' : '')}><Title row={row} /></td><td className="p-3 max-w-xs break-all text-xs">{display(row.account_label || row.user_id)}</td><td className="p-3"><ScoreChip baseline={row.baseline} days={row.prior_observed_active_days} /><p className="text-xs text-slate-500 mt-1">rule severity: {row.severity}</p></td><td className="p-3 text-xs">{when(row.created_at)}</td><td className="p-3">{(row.case_ids || []).map(id => <Link className="block text-indigo-700" key={id} href={'/cases/' + id}>{id.slice(0, 8)}</Link>)}</td><td className="p-3">{review(row)}</td></tr>
  const folded = group => { const { key, list, top } = group, open = !!expanded[key]; return <Fragment key={key}><tr className="border-t"><td className="p-3 max-w-sm"><Title row={top} /><button className="mt-2 text-xs text-indigo-700 underline" aria-expanded={open} onClick={() => setExpanded({ ...expanded, [key]: !open })}>{open ? 'Hide' : 'Show'} all {list.length} findings</button></td><td className="p-3 max-w-xs break-all text-xs">{display(top.account_label || top.user_id)}</td><td className="p-3"><ScoreChip baseline={top.baseline} days={top.prior_observed_active_days} /><p className="text-xs text-slate-500 mt-1">highest of {list.length} · rule severity: {top.severity}</p></td><td className="p-3 text-xs">{when(group.latest)}<p className="text-slate-500">latest of {list.length}</p></td><td className="p-3 text-xs"><b>{list.length}</b> similar</td><td className="p-3">{review(top)}</td></tr>{open && list.map(row => plain(row, true))}</Fragment> }
  return <Frame title="Work queue"><ErrorNotice error={error} /><section className="bg-white rounded-xl border p-4 flex flex-wrap gap-3">
    <label className="text-sm">Category<select aria-label="Finding category" className={field} value={category} onChange={e => filter('category', e.target.value)}>{[['security', 'Security findings'], ['observation', 'Account observations'], ['unverified', 'Unverified origin']].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <label className="text-sm">Status<select className={field} value={status} onChange={e => filter('status', e.target.value)}>{['Open', 'Acknowledged', 'Resolved', 'False Positive', 'All'].map(value => <option key={value}>{value}</option>)}</select></label>
    <label className="text-sm">Account context<select aria-label="Account context" className={field} value={router.query.entity_context || ''} onChange={e => filter('entity_context', e.target.value)}><option value="">All accounts</option><option value="service_or_workload">Service / workload</option><option value="other_or_unclassified">Other / unclassified</option></select></label><label className="text-sm">Triage<select aria-label="Triage" className={field} value={router.query.triage || ''} onChange={e => filter('triage', e.target.value)}><option value="">All findings</option>{Object.entries(TRIAGE).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="text-sm">Baseline tier<select aria-label="Baseline tier" className={field} value={tier} onChange={e => setTier(e.target.value)}><option value="">All</option>{['High', 'Medium', 'Low', 'Learning'].map(value => <option key={value}>{value}</option>)}</select></label><label className="text-sm">Provider<select className={field} value={router.query.provider || ''} onChange={e => filter('provider', e.target.value)}><option value="">All providers</option>{['aws_cloudtrail', 'cloudflare_access', 'github_events'].map(value => <option key={value}>{value}</option>)}</select></label>
    <label className="text-sm">From (MYT, UTC+8)<input className={field} type="datetime-local" value={router.query.start || ''} onChange={e => filter('start', e.target.value)} /></label>
    <label className="text-sm">Until (MYT, UTC+8, exclusive)<input className={field} type="datetime-local" value={router.query.end || ''} onChange={e => filter('end', e.target.value)} /></label>
    <label className="text-sm flex items-end gap-2 pb-2"><input type="checkbox" aria-label="Learning period" checked={learningView === 'only'} onChange={e => filter('learning', e.target.checked ? 'only' : '')} />Learning period{data ? ` (${data.learning_count})` : ''}</label>
    <label className="text-sm flex items-end gap-2 pb-2"><input type="checkbox" checked={grouped} onChange={e => setGrouped(e.target.checked)} />Group similar</label>
  </section>{router.query.account && <p className="text-sm text-slate-500 break-all">Account filter: {display(router.query.account)} <button className="text-indigo-700 ml-2" onClick={() => filter('account', '')}>Clear account filter</button></p>}{!data ? !error && <p>Loading findings…</p> : <section className="rounded-xl border bg-white overflow-x-auto">
    <p className="p-4 text-xs text-slate-500">{data.matched_in_scan} matching findings{grouped ? ` · ${groups.length} groups` : ''}{(data.scan_capped || data.invalid_timestamps > 0) && <Info label="About this list">{data.scan_capped ? 'Within the capped scan; older signals may be omitted. ' : ''}{data.invalid_timestamps > 0 ? `${data.invalid_timestamps} invalid timestamps excluded.` : ''}</Info>}</p>{data.triage_counts && <p className="px-4 pb-3 text-sm text-slate-700"><b>{data.triage_counts.review_first || 0}</b> to review first · {data.triage_counts.automation_context || 0} on automation or service accounts · {data.triage_counts.office_hours_context || 0} inside Malaysian office hours · {data.triage_counts.infrastructure_context || 0} on monitoring infrastructure{learningView === 'exclude' && data.learning_count > 0 ? ` · ${data.learning_count} from the learning period` : ''}. <Info label="About triage">Triage is display context only; recorded severity and detection are unchanged.</Info></p>}
    <table className="w-full text-sm text-left"><thead className="bg-slate-50"><tr>{['Finding', 'Account', 'Baseline score', 'Created', 'Cases', ''].map(label => <th className="p-3" key={label}>{label}</th>)}</tr></thead><tbody>{grouped ? groups.map(group => group.list.length === 1 ? plain(group.top, false) : folded(group)) : rows.map(row => plain(row, false))}</tbody></table>
    {!rows.length && (learningView === 'exclude' && !tier && !router.query.triage && !router.query.account && !router.query.entity_context && !router.query.provider && !router.query.start && !router.query.end ? <p className="p-5">Nothing needs review. <button className="text-indigo-700 underline" onClick={() => filter('learning', 'only')}>{data.learning_count} findings from the learning period</button> · <button className="text-indigo-700 underline" onClick={() => filter('triage', 'infrastructure_context')}>{data.triage_counts?.infrastructure_context || 0} on monitoring infrastructure</button></p> : <p className="p-5">No findings match these filters.</p>)}
    <div className="p-4 flex gap-2">{router.query.before_id && <button className={secondary} onClick={() => filter('category', category)}>Newest</button>}{data.next_cursor && <button className={secondary} onClick={() => router.push({ pathname: '/workspace', query: { ...router.query, before_time: data.next_cursor[0], before_id: data.next_cursor[1] } })}>Older findings</button>}</div>
  </section>}{router.query.finding && <FindingDrawer key={router.query.finding} id={router.query.finding} close={close} changed={() => setReloads(n => n + 1)} />}</Frame>
}
