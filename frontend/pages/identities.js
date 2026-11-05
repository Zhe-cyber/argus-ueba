import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import { fetchIdentities, fetchIdentityAccounts, fetchIdentityTimeline, createIdentity, approveIdentityLink, revokeIdentityLink } from '@/lib/api'

const SOURCES = { github_events: 'GitHub', cloudflare_access: 'Cloudflare', aws_cloudtrail: 'AWS' }
const when = value => value ? new Date(value).toLocaleString('en-GB', { timeZone: 'Asia/Kuala_Lumpur' }) : '—'
const input = 'w-full rounded-lg border border-slate-200 px-3 py-2 text-sm bg-white text-slate-700'
const button = 'rounded-lg bg-indigo-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50'

export default function Identities() {
  const [people, setPeople] = useState([])
  const [accounts, setAccounts] = useState([])
  const [selected, setSelected] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [form, setForm] = useState(null)
  const [revoke, setRevoke] = useState(null)
  const [revision, setRevision] = useState(0)
  const [timelineSource, setTimelineSource] = useState('all')
  const [recorder, setRecorder] = useState('Local analyst')
  const load = useCallback(async () => {
    const [identities, observed] = await Promise.all([fetchIdentities(), fetchIdentityAccounts()])
    setPeople(identities); setAccounts(observed)
    setSelected(current => identities.some(person => person.id === current) ? current : identities[0]?.id || null)
    setRevision(value => value + 1)
  }, [])
  useEffect(() => { load().catch(e => setError(e.message)).finally(() => setLoading(false)) }, [load])
  useEffect(() => {
    if (!selected) { setTimeline(null); return }
    let active = true; setTimeline(null); setTimelineSource('all')
    fetchIdentityTimeline(selected).then(value => { if (active) setTimeline(value) }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [selected, revision])
  const person = people.find(row => row.id === selected)
  const visibleEvents = (timeline?.events || []).filter(event => timelineSource === 'all' || event.source === timelineSource)
  const assigned = new Set(people.flatMap(row => row.links.filter(link => link.effective_status === 'approved').map(link => link.account_key)))
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(null)
    const values = new FormData(event.currentTarget)
    try {
      if (form === 'person') {
        const result = await createIdentity({ display_name: values.get('name'), recorded_by: recorder })
        await load(); setSelected(result.id)
      } else if (revoke) {
        await revokeIdentityLink(revoke, { recorded_by: recorder, reason: values.get('evidence') }); await load()
      } else {
        const expiry = values.get('expires')
        await approveIdentityLink(selected, { account_key: values.get('account'), recorded_by: recorder,
          evidence: values.get('evidence'), expires_at: expiry ? new Date(expiry).toISOString() : null })
        await load()
      }
      setForm(null); setRevoke(null)
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }
  return <>
    <Head><title>Identities — Argus</title></Head>
    <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8 space-y-5">
      <div className="flex items-center justify-between gap-3"><h1 className="text-2xl font-semibold text-slate-900">Identities</h1><div className="flex gap-2">
        <button onClick={() => load().catch(e => setError(e.message))} className="rounded-lg border bg-white px-3 py-2 text-xs text-slate-600">Refresh</button>
        <button onClick={() => { setForm('person'); setRevoke(null) }} className={button}>New identity</button></div></div>
      {error && <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
      {(form || revoke) && <form onSubmit={submit} className="rounded-xl border border-indigo-200 bg-white p-5 space-y-3">
        <h2 className="font-semibold text-slate-800">{form === 'person' ? 'Create identity' : revoke ? 'Revoke account link' : 'Approve account link'}</h2>
        {form === 'person' ? <label className="block text-xs text-slate-500">Display name<input name="name" required maxLength={100} className={input + ' mt-1'} /></label> : !revoke && <label className="block text-xs text-slate-500">Observed account<select name="account" required className={input + ' mt-1'} defaultValue=""><option value="" disabled>Select account</option>{accounts.map(account => <option key={account.account_key} value={account.account_key} disabled={assigned.has(account.account_key)}>{SOURCES[account.source]} · {account.account_label}{assigned.has(account.account_key) ? ' (linked)' : ''}</option>)}</select></label>}
        <div className="grid sm:grid-cols-2 gap-3"><label className="block text-xs text-slate-500">Recorded by<input value={recorder} onChange={e => setRecorder(e.target.value)} required maxLength={100} className={input + ' mt-1'} /></label>{form === 'link' && <label className="block text-xs text-slate-500">Expiry (optional, local time)<input name="expires" type="datetime-local" className={input + ' mt-1'} /></label>}</div>
        {form !== 'person' && <label className="block text-xs text-slate-500">{revoke ? 'Reason' : 'Ownership evidence'}<textarea name="evidence" required maxLength={2000} className={input + ' mt-1'} placeholder={revoke ? 'Why is this link being removed?' : 'Owner confirmation or evidence reviewed'} /></label>}
        <div className="flex gap-2"><button disabled={busy} className={button}>{busy ? 'Saving…' : form === 'person' ? 'Create' : revoke ? 'Revoke link' : 'Approve link'}</button><button type="button" disabled={busy} onClick={() => { setForm(null); setRevoke(null) }} className="rounded-lg border px-3 py-2 text-xs text-slate-600">Cancel</button></div>
      </form>}
      {loading ? <p className="text-sm text-slate-500">Loading identities…</p> : <div className="grid lg:grid-cols-[240px_1fr] gap-5">
        <aside className="rounded-xl border border-slate-200 bg-white p-2 self-start" aria-label="Identity directory">
          {people.length === 0 && <p className="p-4 text-xs text-slate-500">No identities yet.</p>}
          {people.map(row => <button key={row.id} onClick={() => { setSelected(row.id); setForm(null); setRevoke(null) }} aria-pressed={selected === row.id} className={'w-full rounded-lg px-3 py-3 text-left ' + (selected === row.id ? 'bg-indigo-50 text-indigo-800' : 'hover:bg-slate-50 text-slate-700')}><span className="text-sm font-semibold">{row.display_name}</span><span className="block text-xs text-slate-500 mt-1">{row.active_links} linked accounts</span></button>)}
        </aside>
        {person && <div className="space-y-5">
          <section aria-label="Linked accounts" className="rounded-xl border border-slate-200 bg-white overflow-hidden">
            <div className="px-5 py-4 border-b flex items-center justify-between gap-3"><div><h2 className="font-semibold text-slate-900">{person.display_name}</h2><p className="text-xs text-slate-500 mt-1">{person.active_links} approved account links</p></div><button onClick={() => { setForm('link'); setRevoke(null) }} className={button}>Link account</button></div>
            {person.links.length === 0 ? <p className="p-5 text-sm text-slate-500">No linked accounts.</p> : person.links.map(link => <div key={link.id} className="px-5 py-4 border-b last:border-0 border-slate-100">
              <div className="flex flex-wrap items-center justify-between gap-3"><div className="flex flex-wrap items-center gap-3"><span className="text-xs text-slate-500">{SOURCES[link.account?.source] || 'Unavailable'}</span><Link href={'/users/' + encodeURIComponent(link.account_key)} className="text-sm font-medium text-indigo-700 hover:underline">{link.account?.account_label || 'Account unavailable'}</Link><span className={'rounded-full px-2 py-0.5 text-[10px] font-semibold ' + (link.effective_status === 'approved' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500')}>{link.effective_status}</span></div>{link.effective_status === 'approved' && <button onClick={() => { setRevoke(link.id); setForm(null) }} className="text-xs text-slate-500 hover:text-rose-700">Revoke</button>}</div>
              <details className="mt-2 text-xs text-slate-500"><summary className="cursor-pointer">Approval details</summary><dl className="mt-2 space-y-1 break-words"><div>Recorded by: {link.approved_by}</div><div>Approved: {when(link.approved_at)} MY</div><div>Expires: {link.expires_at ? when(link.expires_at) + ' MY' : 'No expiry'}</div><div>Evidence: {link.evidence}</div><div className="font-mono break-all">{link.account_key}</div></dl></details>
            </div>)}
          </section>
          <section aria-label="Cross-provider timeline" className="rounded-xl border border-slate-200 bg-white overflow-hidden">
            <div className="px-5 py-4 border-b"><div className="flex justify-between items-center gap-3"><h2 className="font-semibold text-slate-800">Activity timeline</h2><select aria-label="Timeline source" value={timelineSource} onChange={event => setTimelineSource(event.target.value)} className="rounded-md border text-xs px-2 py-1.5 text-slate-600"><option value="all">All sources</option>{timeline?.linked_sources.map(source => <option key={source} value={source}>{SOURCES[source]}</option>)}</select></div><div className="flex flex-wrap gap-2 mt-2 text-[10px]">{timeline?.linked_sources.map(source => <span key={source} className="rounded-full bg-indigo-50 text-indigo-700 px-2 py-1">{SOURCES[source]} linked</span>)}{timeline?.unlinked_sources.map(source => <span key={source} className="rounded-full bg-slate-100 text-slate-500 px-2 py-1">{SOURCES[source]} not linked</span>)}</div></div>
            {!timeline ? <p className="p-5 text-sm text-slate-500">Loading timeline…</p> : timeline.events.length === 0 ? <p className="p-5 text-sm text-slate-500">No activity through active approved links.</p> : <div className="overflow-x-auto"><table className="w-full text-xs text-left"><thead className="bg-slate-50 text-slate-500"><tr>{['Time (MY)', 'Source', 'Account', 'Action', 'Resource'].map(label => <th key={label} className="px-4 py-3 font-medium">{label}</th>)}</tr></thead><tbody>{visibleEvents.map(event => <tr key={event.id} className="border-t border-slate-100"><td className="px-4 py-3 whitespace-nowrap text-slate-500">{when(event.timestamp_utc)}</td><td className="px-4 py-3 text-slate-600">{SOURCES[event.source]}</td><td className="px-4 py-3"><Link className="text-indigo-700 hover:underline" href={'/users/' + encodeURIComponent(event.account_key)}>{event.account_label}</Link></td><td className="px-4 py-3 text-slate-700">{event.action}</td><td className="px-4 py-3 text-slate-500 break-all">{event.resource || '—'}</td></tr>)}</tbody></table></div>}
            {timeline && <p className="px-5 py-3 border-t text-[10px] text-slate-400">{visibleEvents.length} events shown{timeline.has_more ? ' · more available' : ''} · coverage unverified{timeline.invalid_timestamps > 0 ? ` · ${timeline.invalid_timestamps} invalid timestamps excluded` : ''}</p>}
          </section>
          <details className="text-xs text-slate-500"><summary className="cursor-pointer">Mapping history</summary><div className="mt-3 space-y-2">{person.audit.map(entry => <p key={entry.id}>{when(entry.at_utc)} MY · {entry.action.replaceAll('_', ' ')} · {entry.recorded_by}<span className="block text-slate-400 mt-1">{entry.note}</span></p>)}</div></details>
        </div>}
      </div>}
    </main>
  </>
}
