import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/router'
import Link from 'next/link'
import DiagnosticPanel, { activityDay } from '@/components/DiagnosticPanel'
import { redactDiagnostic } from '@/lib/diagnosticPrivacy'
import { display, Frame, Drawer, Facts, ErrorNotice, FieldError, Info, request, useCommand, useSession, canChange, beforeSignIn, field, button, secondary, when } from '@/components/WorkspaceUI'

const RESOLUTIONS = ['Security incident confirmed', 'Expected or authorized activity', 'Detection false positive', 'Insufficient evidence']
function sourceOf(item) {
  try { return (typeof item.details === 'string' ? JSON.parse(item.details) : item.details)?.source } catch { return null }
}
export default function Case() {
  const router = useRouter(), id = router.query.id
  const [row, setRow] = useState(null), [timeline, setTimeline] = useState(null), [error, setError] = useState(null)
  const session = useSession()
  const [notes, setNotes] = useState(''), [owner, setOwner] = useState(''), [priority, setPriority] = useState('Medium'), [changeReason, setChangeReason] = useState('')
  const [resolution, setResolution] = useState(''), [closingReason, setClosingReason] = useState(''), [closing, setClosing] = useState(false)
  const [tried, setTried] = useState(false), [linkTried, setLinkTried] = useState(false), [alsoFindings, setAlsoFindings] = useState(true), [notice, setNotice] = useState(null)
  const provider = typeof router.query.provider === 'string' ? router.query.provider : ''
  const start = typeof router.query.start === 'string' ? router.query.start : ''
  const end = typeof router.query.end === 'string' ? router.query.end : ''
  const [event, setEvent] = useState(null)
  function timelineFilter(key, value) { router.replace({ pathname: '/cases/[id]', query: { ...router.query, [key]: value } }, undefined, { shallow: true, scroll: false }) }
  const setProvider = value => timelineFilter('provider', value)
  const setStart = value => timelineFilter('start', value)
  const setEnd = value => timelineFilter('end', value)
  const [kind, setKind] = useState('account'), [target, setTarget] = useState(''), [reason, setReason] = useState(''), [entities, setEntities] = useState([])
  const command = useCommand()
  const timelineRequest = useRef(0)
  async function load() {
    try { const value = await request('/cases/' + id); setRow(value); setNotes(value.notes); setOwner(value.owner); setPriority(value.priority); setChangeReason(''); setError(null) } catch (e) { setError(e.message) }
  }
  useEffect(() => { if (id) load() }, [id])
  async function loadTimeline(more = false) {
    const generation = ++timelineRequest.current
    const params = new URLSearchParams({ limit: '50' })
    if (provider) params.set('provider', provider)
    if (start) params.set('start', start + 'Z')
    if (end) params.set('end', end + 'Z')
    if (more && timeline?.next_cursor) { params.set('before_time', timeline.next_cursor[0]); params.set('before_id', timeline.next_cursor[1]) }
    try { const result = await request(`/cases/${id}/timeline?` + params); if (generation === timelineRequest.current) setTimeline(previous => more && previous ? { ...result, events: [...previous.events, ...result.events] } : result) } catch (e) { if (generation === timelineRequest.current) setError(e.message) }
  }
  useEffect(() => { if (id && row?.id === id) { setTimeline(null); loadTimeline() } return () => { timelineRequest.current++ } }, [id, row?.version, provider, start, end])
  useEffect(() => { let active = true; setTarget(''); request('/workspace/' + (kind === 'account' ? 'accounts' : 'people')).then(value => { if (active) setEntities(value) }).catch(e => { if (active) setError(e.message) }); return () => { active = false } }, [kind])
  // On close, linked Open/Acknowledged findings follow the case resolution through the same status path as the queue.
  async function updateFindings() {
    const status = resolution === 'Detection false positive' ? 'False Positive' : 'Resolved'
    const failures = []; let updated = 0
    for (const link of row.links.filter(item => item.kind === 'finding')) {
      try {
        const current = await request('/findings/' + link.target)
        if (!['Open', 'Acknowledged'].includes(current.status)) continue
        await request(`/findings/${link.target}/status`, { status, reason: `Case ${id.slice(0, 8)} closed: ${resolution}. ${closingReason}`.slice(0, 2000) })
        updated++
      } catch (e) { failures.push(`#${link.target}: ${e.message}`) }
    }
    setNotice(`${updated} linked finding${updated === 1 ? '' : 's'} set to ${status}.`)
    if (failures.length) setError('The case is closed, but some linked findings were not updated. ' + failures.join(' · '))
  }
  function edit(e) {
    e.preventDefault()
    setTried(true); setNotice(null)
    if ((priority !== row.priority && !changeReason.trim()) || (closing && (!resolution || !closingReason.trim()))) return
    const changes = { notes, owner, priority }
    if (priority !== row.priority) changes.change_reason = changeReason
    if (closing) Object.assign(changes, { status: 'Closed', resolution, closing_reason: closingReason })
    command.run('/cases/' + id, { expected_version: row.version, changes }, 'PATCH', async value => { if (closing && alsoFindings) await updateFindings(); setRow(value); setClosing(false); setTried(false) })
  }
  function linkEntity(e) { e.preventDefault(); setLinkTried(true); if (!target || !reason.trim()) return; command.run(`/cases/${id}/links`, { expected_version: row.version, kind, target, reason }, 'POST', value => { setRow(value); setReason(''); setLinkTried(false) }) }
  async function inspect(eventId) { try { setEvent(await request('/events/' + eventId)) } catch (e) { setError(e.message) } }
  if (!row || row.id !== id) return <Frame title="Case"><ErrorNotice error={error} />{!error && <p>Loading case…</p>}</Frame>
  const open = row.status !== 'Closed' && canChange(session)  // viewers see no change controls
  const markers = row.links.filter(link => link.kind === 'finding').map(link => ({ ...link.snapshot, marker: true, timestamp_utc: link.snapshot.created_at }))
    .filter(item => (!provider || sourceOf(item) === provider)
      && (!start || Date.parse(item.timestamp_utc) >= Date.parse(start + 'Z')) && (!end || Date.parse(item.timestamp_utc) < Date.parse(end + 'Z')))
  const items = [...(timeline?.events || []), ...markers].sort((a, b) => (Date.parse(b.timestamp_utc) || 0) - (Date.parse(a.timestamp_utc) || 0))
  return <Frame title={display(row.display_title || row.title)}><ErrorNotice error={error || command.error} />{notice && <p role="status" className="border border-emerald-200 bg-emerald-50 text-emerald-800 p-3 rounded-lg text-sm">{notice}</p>}<div className="flex flex-wrap gap-3 items-center text-sm"><span className="rounded bg-slate-200 px-2 py-1">{row.status}</span><span>{row.priority} priority</span><span>{display(row.owner || 'Unassigned')}</span><span className="text-xs text-slate-500">Case {id.slice(0, 8)} · version {row.version}</span><button className={secondary} disabled={command.busy} onClick={load}>Reload case (discards unsaved edits)</button></div>
    {row.legacy && <details className="bg-white border rounded-lg p-3 text-sm"><summary>Legacy investigation · original status: {display(row.legacy.record.status || '—')}</summary><Facts value={row.legacy} /></details>}
    <div className="grid lg:grid-cols-[2fr_1fr] gap-5 items-start"><section className="bg-white border rounded-xl p-5 space-y-4"><h2 className="text-lg font-semibold">Evidence timeline</h2><p className="text-xs text-slate-500">{timeline ? `${timeline.events.length} events shown${timeline.has_more ? ' · older activity available' : ''}` : ''}</p>
      <div className="flex flex-wrap gap-3"><label className="text-xs">Provider<select className={field} value={provider} onChange={e => setProvider(e.target.value)}><option value="">All providers</option>{['aws_cloudtrail', 'cloudflare_access', 'github_events'].map(value => <option key={value}>{value}</option>)}</select></label><label className="text-xs">From (UTC)<input type="datetime-local" className={field} value={start} onChange={e => setStart(e.target.value)} /></label><label className="text-xs">Until (UTC, exclusive)<input type="datetime-local" className={field} value={end} onChange={e => setEnd(e.target.value)} /></label></div>
      <Link className="text-xs text-indigo-700" href={{ pathname: '/connections', query: { case_id: id, provider, start, end } }}>Check collection context →</Link><p className="text-xs text-slate-500">Observed activity<Info label="About this timeline">Observed activity only; completeness is unknown.</Info> {timeline?.scan_capped && 'Scan capped; older activity may be omitted. '}{timeline?.invalid_timestamps > 0 && `${timeline.invalid_timestamps} invalid timestamps excluded.`}</p>
      {timeline?.mapping_provenance.map(mapping => <p key={mapping.link_id} className="text-xs text-slate-500">Identity mapping {mapping.link_id.slice(0, 8)}: approved when linked · currently {mapping.current_status}</p>)}
      {!timeline ? <p>Loading activity…</p> : !items.length ? <p>No activity in this scope. Add a related account or approved person to include their history.</p> : <ol className="space-y-3 max-h-[640px] overflow-y-auto pr-2">{items.map(item => <li key={(item.marker ? 'finding-' : 'event-') + item.id} className="border-l-2 border-indigo-200 pl-4 py-2"><p className="text-xs text-slate-500">{when(item.timestamp_utc)} · {item.marker ? 'Linked finding' : item.source}</p><p className="text-sm font-medium">{display(item.marker ? item.title : item.action)}</p>{!item.marker && <><p className="text-xs text-slate-500 break-all">{display(typeof item.resource_value === 'object' ? JSON.stringify(item.resource_value) : item.resource)} · {display(row.links.find(link => link.kind === 'account' && link.target === item.account_key)?.snapshot.account_label || item.account_key?.slice(0, 18))}</p><p className="text-xs text-slate-500">{item.evidence_relation === 'linked_evidence' ? 'Selected evidence' : 'Related account activity'}</p><button className="text-xs text-indigo-700 mt-1" onClick={() => inspect(item.id)}>Inspect event #{item.id}</button></>}{item.marker && <p className="text-xs text-slate-500">{item.severity} · linked finding<Info label="About linked findings">Retained finding snapshot: the finding as it was when linked to this case.</Info></p>}</li>)}</ol>}
      {timeline?.next_cursor && <button className={secondary} onClick={() => loadTimeline(true)}>Older activity</button>}
    </section><aside className="space-y-5"><section className="bg-white rounded-xl border p-5 space-y-3"><h2 className="font-semibold">Case scope</h2>{row.links.filter(link => ['account', 'person'].includes(link.kind)).map(link => <div key={link.kind + link.target} className="text-sm"><p className="font-medium break-all">{display(link.snapshot.display_name || link.snapshot.account_label || link.target)}</p><p className="text-xs text-slate-500">{link.kind === 'person' ? 'Approved identity mapping' : 'Related account'} · {display(link.reason)}</p></div>)}
      {open && <form noValidate onSubmit={linkEntity} className="space-y-2 border-t pt-3"><label className="block text-sm">Add context<select className={field} value={kind} onChange={e => setKind(e.target.value)}><option value="account">Related account</option><option value="person">Approved person</option></select></label><label className="block text-sm">Entity<select className={field} value={target} onChange={e => setTarget(e.target.value)}><option value="">Choose an entity</option>{entities.map(entity => <option key={entity.account_key || entity.id} value={entity.account_key || entity.id}>{display(entity.account_label || entity.display_name)}{entity.source ? ' · ' + entity.source : ''}</option>)}</select><FieldError show={linkTried && !target}>Choose an entity.</FieldError></label><label className="block text-sm">Reason<textarea maxLength={2000} className={field} value={reason} onChange={e => setReason(e.target.value)} /><FieldError show={linkTried && !reason.trim()}>Reason is required.</FieldError></label><button className={secondary} disabled={command.busy}>Add to case</button></form>}</section>
    <form noValidate data-readonly={!open ? 'true' : undefined} onSubmit={edit} className="bg-white rounded-xl border p-5 space-y-3"><h2 className="font-semibold">Decision & notes</h2>{open && <p className="text-xs text-slate-500">Recorded as {display(session?.user)}</p>}{open ? <><label className="block text-sm">Owner<input maxLength={200} className={field} value={owner} onChange={e => setOwner(e.target.value)} /></label><label className="block text-sm">Priority<select className={field} value={priority} onChange={e => setPriority(e.target.value)}>{['Low', 'Medium', 'High', 'Critical'].map(value => <option key={value}>{value}</option>)}</select></label>{priority !== row.priority && <label className="block text-sm">Priority change reason<input maxLength={2000} className={field} value={changeReason} onChange={e => setChangeReason(e.target.value)} /><FieldError show={tried && !changeReason.trim()}>A reason for the priority change is required.</FieldError></label>}<label className="block text-sm">Notes<textarea maxLength={20000} className={field} value={notes} onChange={e => setNotes(e.target.value)} /></label><label className="flex gap-2 text-sm"><input type="checkbox" checked={closing} onChange={e => setClosing(e.target.checked)} />Close this case</label>{closing && <><label className="block text-sm">Resolution<select aria-label="Resolution" className={field} value={resolution} onChange={e => setResolution(e.target.value)}><option value="">Choose a resolution</option>{RESOLUTIONS.map(value => <option key={value}>{value}</option>)}</select><FieldError show={tried && !resolution}>Choose a resolution.</FieldError></label><label className="block text-sm">Closing reason<textarea maxLength={2000} className={field} value={closingReason} onChange={e => setClosingReason(e.target.value)} /><FieldError show={tried && !closingReason.trim()}>Closing reason is required.</FieldError></label><label className="flex gap-2 text-sm"><input type="checkbox" checked={alsoFindings} onChange={e => setAlsoFindings(e.target.checked)} />Also update linked findings</label><p className="text-xs text-slate-500">Linked open or acknowledged findings become False Positive for “Detection false positive”, otherwise Resolved.</p></>}<button disabled={command.busy} className={button}>{command.busy ? 'Saving…' : closing ? 'Save decision and close' : 'Save notes'}</button></> : <Facts value={{ resolution: row.resolution, closing_reason: row.closing_reason, notes: row.notes }} />}</form></aside></div>
    {!!row.links.filter(link => link.kind === 'diagnostic').length && <section className="bg-white border rounded-xl p-5 space-y-3"><h2 className="font-semibold">Retained diagnostic context</h2>{row.links.filter(link => link.kind === 'diagnostic').map(link => <details key={link.target}><summary className="cursor-pointer text-sm">{link.snapshot.receipt.key.day} · {link.snapshot.receipt.key.source} · {link.snapshot.status}</summary><p className="text-xs text-slate-500">{display(link.reason)} · account-day context</p><Facts value={redactDiagnostic(link.snapshot)} /></details>)}</section>}
    <details className="bg-white border rounded-xl p-5"><summary className="font-semibold cursor-pointer">Case activity · {row.history.length} entries</summary><ol className="mt-3 space-y-3">{row.history.map(entry => <li key={entry.id} className="text-sm border-t pt-3"><p>{entry.action} · {display(entry.actor)}{beforeSignIn(session, entry.at_utc) && <span className="text-slate-500"> (recorded before sign-in)</span>} · {when(entry.at_utc)} · v{entry.version}</p><Facts value={entry.action === 'diagnostic_context_retained' ? redactDiagnostic(entry.detail) : entry.detail} /></li>)}</ol></details>
    {event && <Drawer title={'Event #' + event.id} close={() => setEvent(null)}><Facts value={event} /><p className="text-xs text-slate-500">Account-day context<Info label="About this event">Account-day context; no automatic attribution to this event.</Info></p><DiagnosticPanel key={event.id} account={event} initialDay={activityDay(event.timestamp)} caseContext={{ id, version: row.version, open, onRetained: setRow }} />{open && <button data-write-action disabled={command.busy} className={button} onClick={() => command.run(`/cases/${id}/links`, { expected_version: row.version, kind: 'event', target: String(event.id), reason: 'Selected by analyst from related case activity' }, 'POST', setRow)}>Retain as selected evidence</button>}</Drawer>}
  </Frame>
}
