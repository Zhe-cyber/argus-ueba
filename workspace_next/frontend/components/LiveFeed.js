import { useEffect, useState } from 'react'
import { display, Info, request, when } from '@/components/WorkspaceUI'

const SOURCES = [['aws_cloudtrail', 'AWS'], ['github_events', 'GitHub'], ['cloudflare_access', 'Cloudflare'], ['azure_ad', 'Microsoft Entra ID']]
// Freshness dot: green under 15 min, amber under 2 h, grey otherwise.
function dot(receivedUtc, now) {
  const age = (now - Date.parse(receivedUtc)) / 1000
  return !Number.isFinite(age) ? ['bg-slate-300', 'no data'] : age < 900 ? ['bg-emerald-500', 'fresh'] : age < 7200 ? ['bg-amber-400', 'delayed'] : ['bg-slate-300', 'quiet']
}
const ago = seconds => seconds < 60 ? seconds + 's' : seconds < 3600 ? Math.floor(seconds / 60) + 'm' : Math.floor(seconds / 3600) + 'h'

export default function LiveFeed() {
  const [feed, setFeed] = useState(null), [failed, setFailed] = useState(false), [tick, setTick] = useState(Date.now())
  useEffect(() => {
    let active = true
    const load = () => request('/workspace/live-feed').then(v => { if (active) { setFeed(v); setFailed(false); setTick(Date.now()) } }).catch(() => { if (active) setFailed(true) })
    load(); const timer = setInterval(load, 10000)
    return () => { active = false; clearInterval(timer) }
  }, [])
  if (failed && !feed) return <section className="bg-white rounded-xl border p-5"><h2 className="font-semibold">Live feed</h2><p className="text-sm mt-2">Could not load the feed. Retrying…</p></section>
  if (!feed) return <section className="bg-white rounded-xl border p-5"><h2 className="font-semibold">Live feed</h2><p className="text-sm mt-2">Loading feed…</p></section>
  const mirror = feed.mirror, collector = feed.collector
  return <section className="bg-white rounded-xl border p-5 space-y-3" aria-label="Live feed">
    <div className="flex flex-wrap justify-between gap-2"><h2 className="font-semibold">Live feed</h2>{failed && <span className="text-xs text-amber-700">Showing the last result; retrying.</span>}</div>
    <div className="grid md:grid-cols-4 gap-4">{SOURCES.map(([key, label]) => { const s = feed.sources[key] || {}, [color, word] = dot(s.last_received_utc, tick)
      if (key === 'azure_ad' && !s.last_received_utc) return <div key={key} className="border rounded-lg p-3"><p className="text-sm font-medium">{label} <span className="text-xs text-slate-500 font-normal">not connected</span></p></div>
      return <div key={key} className="border rounded-lg p-3 space-y-2"><p className="text-sm font-medium flex items-center gap-2"><span aria-label={word} className={'inline-block w-3 h-3 rounded-full ' + color} />{label}<span className="text-xs text-slate-500 font-normal">{word}</span></p>
        <p className="text-xs text-slate-500">{s.events_last_hour ?? 0} in the last hour · {s.events_today_myt ?? 0} today (MYT)</p>
        <ul className="text-xs divide-y">{(s.newest || []).map((e, i) => <li key={i} className={'py-1 break-words' + (e.infrastructure ? ' text-slate-400' : '')}><span className="text-slate-500">{when(e.time_myt).replace(' MYT', '')}</span> · {display(e.account_label)} · {display(e.action)}{e.count > 1 ? ` × ${e.count}` : ''}<span className="block text-slate-400">{e.count > 1 ? 'latest ' : ''}received {ago(e.received_seconds_ago)} ago</span></li>)}</ul>{!(s.newest || []).length && <p className="text-xs">No events yet.</p>}</div> })}</div>
    <p className="text-xs text-slate-500">{mirror?.last_pass_utc && `Last update ${when(mirror.last_pass_utc)} (+${mirror.events_added} events)`}{mirror?.guard_active && <Info label="About the study guard">Study guard on: events dated 14 Nov 2026 MYT or later are held back until 16 Nov 2026.</Info>}{collector?.last_tick_utc && ` · Collector checked ${when(collector.last_tick_utc)}${collector.ok ? '' : ' (reported a problem)'}`}</p>
  </section>
}
