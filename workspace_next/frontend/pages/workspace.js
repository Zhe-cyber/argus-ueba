import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import Link from 'next/link'
import DiagnosticPanel, { activityDay } from '@/components/DiagnosticPanel'
import { display, Frame, Drawer, Facts, ErrorNotice, request, useCommand, field, button, secondary, when } from '@/components/WorkspaceUI'
const TRIAGE = { review_first: 'Review first', automation_context: 'Context: automation or service account', office_hours_context: 'Context: inside Malaysian office hours' }

function FindingDrawer({ id, close }) {
  const router = useRouter()
  const [finding, setFinding] = useState(null), [error, setError] = useState(null)
  const [title, setTitle] = useState(''), [actor, setActor] = useState(''), [owner, setOwner] = useState('')
  const [reason, setReason] = useState(''), [includeAccount, setIncludeAccount] = useState(false)
  const [mode, setMode] = useState(null), [cases, setCases] = useState([]), [selected, setSelected] = useState(''), [cursor, setCursor] = useState(null)
  const command = useCommand()
  useEffect(() => { let active = true; request('/findings/' + id).then(row => { if (active) { setFinding(row); setTitle((row.display_title || row.title) + ' — ' + row.account_label) } }).catch(e => { if (active) setError(e.message) }); return () => { active = false } }, [id])
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
    const target = cases.find(row => row.id === selected)
    if (mode === 'existing' && !target) return
    command.run(mode === 'new' ? '/cases/from-finding' : `/cases/${selected}/links`, mode === 'new'
      ? { title, owner, actor, finding_id: Number(id), reason, include_account: includeAccount }
      : { actor, expected_version: target.version, kind: 'finding', target: String(id), reason }, 'POST', row => router.push('/cases/' + row.id))
  }
  return <Drawer title={'Finding #' + id} close={close}><ErrorNotice error={error || command.error} />{!finding ? <p>Loading evidence…</p> : <>
    <h3 className="font-semibold text-slate-900">{display(finding.display_title || finding.title)}</h3><p className="text-xs text-slate-500">{finding.severity} · {finding.origin} · {when(finding.created_at)}</p>
    <Facts value={{ account: finding.account_label, triage: TRIAGE[finding.triage], event_time_malaysia: finding.event_time_myt ? when(finding.event_time_myt) + (finding.in_myt_office_hours ? ' (inside office hours, Mon–Fri 08:00–18:00)' : ' (outside office hours, Mon–Fri 08:00–18:00)') : null, rule_window: finding.rule_window, event_time_utc: finding.rule_event_time_utc, ...finding.details }} />
    <p className="text-xs text-slate-500">{finding.entity_context === 'service_or_workload' ? 'Service/workload account. ' : ''}{finding.history_context === 'limited_observed_history' ? 'Limited observed history; novelty alone does not establish misuse. ' : ''}Exact triggering events are not bound to this legacy signal. Account activity added to a case is related context.</p>
    {finding.diagnostic_subject && <details className="border-t pt-3"><summary className="cursor-pointer text-sm">Account-day diagnostic context</summary><DiagnosticPanel key={id} account={finding.diagnostic_subject} initialDay={activityDay(finding.rule_event_time_utc)} /></details>}
    {!mode ? <div data-write-action className="flex gap-2"><button className={button} onClick={() => setMode('new')}>Create case</button><button className={secondary} onClick={() => { setMode('existing'); loadCases() }}>Add to case</button></div> : <form onSubmit={submit} className="border-t pt-4 space-y-3">
      <h3 className="font-semibold">{mode === 'new' ? 'New case' : 'Existing case'}</h3>
      {mode === 'new' ? <><label className="block text-sm">Title<input required maxLength={240} className={field} value={title} onChange={e => setTitle(e.target.value)} /></label><label className="block text-sm">Owner<input maxLength={200} className={field} value={owner} onChange={e => setOwner(e.target.value)} /></label><label className="flex gap-2 text-sm"><input type="checkbox" checked={includeAccount} onChange={e => setIncludeAccount(e.target.checked)} />Include this account’s activity as related context</label></> : <><label className="block text-sm">Case<select required className={field} value={selected} onChange={e => setSelected(e.target.value)}><option value="">Select an open case</option>{cases.filter(row => row.status !== 'Closed').map(row => <option key={row.id} value={row.id}>{display(row.display_title || row.title)}</option>)}</select></label><button type="button" className={secondary} onClick={() => loadCases(false)}>Refresh cases</button>{cursor && <button type="button" className={secondary} onClick={() => loadCases(true)}>Load more cases</button>}</>}
      <label className="block text-sm">Analyst<input required maxLength={200} className={field} value={actor} onChange={e => setActor(e.target.value)} /></label>
      <label className="block text-sm">Reason<textarea required maxLength={2000} className={field} value={reason} onChange={e => setReason(e.target.value)} /></label>
      <div className="flex gap-2"><button disabled={command.busy} className={button}>{command.busy ? 'Saving…' : mode === 'new' ? 'Create case with finding' : 'Link finding'}</button><button type="button" disabled={command.busy} className={secondary} onClick={() => setMode(null)}>Back</button></div>
    </form>}</>}</Drawer>
}

export default function WorkQueue() {
  const router = useRouter(), [data, setData] = useState(null), [error, setError] = useState(null)
  const category = router.query.category || 'security', status = router.query.status || 'Open'
  useEffect(() => {
    if (!router.isReady) return
    let active = true; setData(null); setError(null)
    const params = new URLSearchParams({ limit: '50', category, status })
    for (const key of ['provider', 'account', 'entity_context', 'triage', 'start', 'end', 'before_time', 'before_id']) if (router.query[key]) params.set(key, router.query[key])
    request('/findings?' + params).then(value => { if (active) setData(value) }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [router.isReady, router.asPath])
  function filter(key, value) { const query = { ...router.query, [key]: value }; delete query.before_time; delete query.before_id; delete query.finding; router.push({ pathname: '/workspace', query }) }
  function close() { const query = { ...router.query }; delete query.finding; router.push({ pathname: '/workspace', query }, undefined, { scroll: false }) }
  return <Frame title="Work queue"><ErrorNotice error={error} /><section className="bg-white rounded-xl border p-4 flex flex-wrap gap-3">
    <label className="text-sm">Category<select aria-label="Finding category" className={field} value={category} onChange={e => filter('category', e.target.value)}>{[['security', 'Security findings'], ['observation', 'Account observations'], ['unverified', 'Unverified origin']].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <label className="text-sm">Status<select className={field} value={status} onChange={e => filter('status', e.target.value)}>{['Open', 'Acknowledged', 'Resolved', 'False Positive', 'All'].map(value => <option key={value}>{value}</option>)}</select></label>
    <label className="text-sm">Account context<select aria-label="Account context" className={field} value={router.query.entity_context || ''} onChange={e => filter('entity_context', e.target.value)}><option value="">All accounts</option><option value="service_or_workload">Service / workload</option><option value="other_or_unclassified">Other / unclassified</option></select></label><label className="text-sm">Triage<select aria-label="Triage" className={field} value={router.query.triage || ''} onChange={e => filter('triage', e.target.value)}><option value="">All findings</option>{Object.entries(TRIAGE).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="text-sm">Provider<select className={field} value={router.query.provider || ''} onChange={e => filter('provider', e.target.value)}><option value="">All providers</option>{['aws_cloudtrail', 'cloudflare_access', 'github_events'].map(value => <option key={value}>{value}</option>)}</select></label>
    <label className="text-sm">From (UTC)<input className={field} type="datetime-local" value={router.query.start?.replace('Z', '') || ''} onChange={e => filter('start', e.target.value ? e.target.value + 'Z' : '')} /></label>
    <label className="text-sm">Until (UTC, exclusive)<input className={field} type="datetime-local" value={router.query.end?.replace('Z', '') || ''} onChange={e => filter('end', e.target.value ? e.target.value + 'Z' : '')} /></label>
  </section>{router.query.account && <p className="text-sm text-slate-500 break-all">Account filter: {display(router.query.account)} <button className="text-indigo-700 ml-2" onClick={() => filter('account', '')}>Clear account filter</button></p>}{!data ? !error && <p>Loading findings…</p> : <section className="rounded-xl border bg-white overflow-x-auto">
    <p className="p-4 text-xs text-slate-500">{data.matched_in_scan} matching findings{data.scan_capped ? ' within the capped scan; older signals may be omitted' : ''}{data.invalid_timestamps > 0 ? ` · ${data.invalid_timestamps} invalid timestamps excluded` : ''}</p>{data.triage_counts && <p className="px-4 pb-3 text-sm text-slate-700"><b>{data.triage_counts.review_first || 0}</b> to review first · {data.triage_counts.automation_context || 0} on automation or service accounts · {data.triage_counts.office_hours_context || 0} inside Malaysian office hours. <span className="text-xs text-slate-500">Triage is display context only; recorded severity and detection are unchanged.</span></p>}
    <table className="w-full text-sm text-left"><thead className="bg-slate-50"><tr>{['Finding', 'Account', 'Recorded severity', 'Created', 'Cases', ''].map(label => <th className="p-3" key={label}>{label}</th>)}</tr></thead><tbody>{data.findings.map(row => <tr key={row.id} className="border-t"><td className="p-3 max-w-sm">{display(row.display_title || row.title)}<p className="text-xs text-slate-500">#{row.id} · {row.origin}</p><p className="text-xs text-slate-500">{row.entity_context === 'service_or_workload' ? 'Service / workload' : 'Other / unclassified'}{row.history_context === 'limited_observed_history' ? ' · limited observed history' : ''}</p>{row.triage && <span className={'inline-block mt-1 rounded px-2 py-0.5 text-xs ' + (row.triage === 'review_first' ? 'bg-amber-100 text-amber-900' : 'bg-slate-100 text-slate-600')}>{TRIAGE[row.triage]}</span>}</td><td className="p-3 max-w-xs break-all text-xs">{display(row.account_label || row.user_id)}</td><td className="p-3">{row.severity}</td><td className="p-3 text-xs">{when(row.created_at)}</td><td className="p-3">{row.case_ids.map(id => <Link className="block text-indigo-700" key={id} href={'/cases/' + id}>{id.slice(0, 8)}</Link>)}</td><td className="p-3"><button className={secondary} onClick={() => router.push({ pathname: '/workspace', query: { ...router.query, finding: row.id } }, undefined, { scroll: false })}>Review #{row.id}</button></td></tr>)}</tbody></table>
    {!data.findings.length && <p className="p-5">No findings match these filters.</p>}
    <div className="p-4 flex gap-2">{router.query.before_id && <button className={secondary} onClick={() => filter('category', category)}>Newest</button>}{data.next_cursor && <button className={secondary} onClick={() => router.push({ pathname: '/workspace', query: { ...router.query, before_time: data.next_cursor[0], before_id: data.next_cursor[1] } })}>Older findings</button>}</div>
  </section>}{router.query.finding && <FindingDrawer key={router.query.finding} id={router.query.finding} close={close} />}</Frame>
}
