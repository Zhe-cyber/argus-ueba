import { useEffect, useState } from 'react'
import Link from 'next/link'
import { display, Frame, ErrorNotice, request, secondary, when } from '@/components/WorkspaceUI'

export default function Cases() {
  const [rows, setRows] = useState([]), [cursor, setCursor] = useState(null), [error, setError] = useState(null), [busy, setBusy] = useState(false)
  async function load(more = false) {
    setBusy(true); setError(null)
    try {
      const params = new URLSearchParams({ limit: '50' })
      if (more && cursor) { params.set('before_time', cursor[0]); params.set('before_id', cursor[1]) }
      const result = await request('/cases?' + params)
      setRows(previous => more ? [...previous, ...result.cases] : result.cases); setCursor(result.next_cursor)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  useEffect(() => { load() }, [])
  return <Frame title="Cases"><ErrorNotice error={error} /><div><button className={secondary} disabled={busy} onClick={() => load()}>Refresh cases</button></div><section className="rounded-xl bg-white border overflow-x-auto"><table className="w-full text-sm text-left"><thead className="bg-slate-50"><tr>{['Case', 'Status', 'Priority', 'Owner', 'Updated'].map(label => <th key={label} className="p-4">{label}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.id} className="border-t"><td className="p-4"><Link className="text-indigo-700 font-medium" href={'/cases/' + row.id}>{display(row.display_title || row.title)}</Link><p className="text-xs text-slate-400">{row.id.slice(0, 8)}{row.legacy ? ' · imported record' : ''}</p></td><td className="p-4">{row.status}</td><td className="p-4">{row.priority}</td><td className="p-4">{display(row.owner || 'Unassigned')}</td><td className="p-4 text-xs">{when(row.updated_at)}</td></tr>)}</tbody></table>{!busy && !rows.length && <p className="p-5">No cases yet. Review a finding to start.</p>}{cursor && <button disabled={busy} className={secondary + ' m-4'} onClick={() => load(true)}>Older cases</button>}</section></Frame>
}
