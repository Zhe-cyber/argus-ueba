import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { fetchInvestigations, bulkImportHighRisk } from '@/lib/api'

const STATUS_FILTERS = ['All', 'Pending', 'Under Investigation', 'Cleared', 'Confirmed Insider']

const INV_STYLE = {
  'Pending':            { bg: 'bg-slate-100',  text: 'text-slate-600',  ring: 'ring-slate-300',  dot: 'bg-slate-400'  },
  'Under Investigation':{ bg: 'bg-amber-100',  text: 'text-amber-700',  ring: 'ring-amber-300',  dot: 'bg-amber-500'  },
  'Cleared':            { bg: 'bg-green-100',  text: 'text-green-700',  ring: 'ring-green-300',  dot: 'bg-green-500'  },
  'Confirmed Insider':  { bg: 'bg-red-100',    text: 'text-red-700',    ring: 'ring-red-300',    dot: 'bg-red-500'    },
}

function StatusBadge({ status }) {
  const s = INV_STYLE[status] ?? INV_STYLE['Pending']
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5
                      text-xs font-semibold ring-1 ${s.bg} ${s.text} ${s.ring}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {status}
    </span>
  )
}

function Spinner() {
  return (
    <div className="flex items-center justify-center py-20 text-slate-400">
      <svg className="animate-spin h-7 w-7" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    </div>
  )
}

export default function InvestigationQueue() {
  const router = useRouter()
  const [records,    setRecords]    = useState([])
  const [filter,     setFilter]     = useState('All')
  const [loading,    setLoading]    = useState(true)
  const [error,      setError]      = useState(null)
  const [importing,  setImporting]  = useState(false)
  const [importMsg,  setImportMsg]  = useState(null)

  const load = useCallback(async (f) => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchInvestigations(f === 'All' ? null : f)
      setRecords(data)
    } catch (e) {
      setError(e.message ?? 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load(filter) }, [filter, load])

  async function handleBulkImport() {
    setImporting(true)
    setImportMsg(null)
    try {
      const res = await bulkImportHighRisk()
      setImportMsg(`Added ${res.created} user${res.created !== 1 ? 's' : ''} — ${res.skipped} already queued.`)
      load(filter)
    } catch (e) {
      setImportMsg(`Error: ${e.message}`)
    } finally {
      setImporting(false)
    }
  }

  return (
    <>
      <Head>
        <title>Investigations — Argus</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

        <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6">

          <div className="rounded-xl bg-white shadow-sm border border-slate-200 overflow-hidden">

            {/* Toolbar */}
            <div className="px-5 py-4 border-b border-slate-100 flex flex-col gap-3">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-slate-700">Investigation Queue</h2>
                  {!loading && (
                    <p className="text-xs text-slate-400 mt-0.5">
                      {records.length} record{records.length !== 1 ? 's' : ''}
                      {filter !== 'All' ? ` · ${filter}` : ''}
                    </p>
                  )}
                </div>
                <button
                  onClick={handleBulkImport}
                  disabled={importing}
                  className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2
                             text-sm font-semibold text-white hover:bg-red-700
                             disabled:opacity-50 transition-colors self-start sm:self-auto"
                >
                  <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" clipRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-11.25a.75.75 0 00-1.5
                         0v4.59L7.3 9.24a.75.75 0 00-1.1 1.02l3.25 3.5a.75.75 0 001.1
                         0l3.25-3.5a.75.75 0 10-1.1-1.02l-1.95 2.1v-4.59z" />
                  </svg>
                  {importing ? 'Importing…' : 'Import all High-risk users'}
                </button>
              </div>
              {importMsg && (
                <p className={`text-xs font-medium px-1 ${importMsg.startsWith('Error') ? 'text-red-600' : 'text-green-600'}`}>
                  {importMsg}
                </p>
              )}
              <div className="flex items-center gap-1.5 rounded-lg bg-slate-100 p-1 flex-wrap">
                {STATUS_FILTERS.map(f => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={[
                      'rounded-md px-3 py-1.5 text-xs font-semibold transition-all',
                      filter === f
                        ? 'bg-white text-slate-800 shadow-sm ring-1 ring-slate-200'
                        : 'text-slate-500 hover:text-slate-700',
                    ].join(' ')}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>   {/* end toolbar */}

            {/* Content */}
            {loading ? (
              <Spinner />
            ) : error ? (
              <p className="py-10 text-center text-sm text-red-500">{error}</p>
            ) : records.length === 0 ? (
              <p className="py-16 text-center text-sm text-slate-400">
                No investigations{filter !== 'All' ? ` with status "${filter}"` : ''} yet.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 bg-slate-50">
                      <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">User</th>
                      <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">Status</th>
                      <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">Analyst</th>
                      <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">Notes</th>
                      <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {records.map((r, i) => (
                      <tr
                        key={r.user_id}
                        onClick={() => router.push(`/users/${encodeURIComponent(r.user_id)}`)}
                        className={[
                          'border-b border-slate-50 cursor-pointer transition-colors',
                          'hover:bg-indigo-50 hover:border-indigo-100',
                          i % 2 === 0 ? 'bg-white' : 'bg-slate-50/60',
                        ].join(' ')}
                      >
                        <td className="px-5 py-3.5 font-mono text-slate-700 font-medium">
                          {r.user_id}
                        </td>
                        <td className="px-5 py-3.5">
                          <StatusBadge status={r.status} />
                        </td>
                        <td className="px-5 py-3.5 text-slate-600">{r.analyst}</td>
                        <td className="px-5 py-3.5 text-slate-500 max-w-xs truncate">
                          {r.notes || <span className="text-slate-300">—</span>}
                        </td>
                        <td className="px-5 py-3.5 text-slate-400 text-xs tabular-nums whitespace-nowrap">
                          {new Date(r.updated_at).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </main>
    </>
  )
}
