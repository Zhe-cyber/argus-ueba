import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { maskText } from '@/lib/presentationPrivacy.mjs'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8015'
export function presentationEnabled() { try { return typeof window !== 'undefined' && sessionStorage.getItem('argus-presentation') === 'true' } catch { return false } }
export function display(value) {
  if (!presentationEnabled() || typeof value !== 'string') return value
  return maskText(value)
}
function displayValue(value) {
  if (Array.isArray(value)) return value.map(displayValue)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key,item]) => [display(key), displayValue(item)]))
  return typeof value === 'number' && /^\d{12}$/.test(String(value)) && presentationEnabled() ? '[account ID hidden]' : display(value)
}
export const field = 'rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm w-full'
export const button = 'rounded-lg bg-indigo-700 px-3 py-2 text-sm text-white disabled:opacity-50'
export const secondary = 'rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm disabled:opacity-50'
export const when = value => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString('en-GB', { timeZone: 'Asia/Kuala_Lumpur' }) + ' MYT' : 'Time unavailable'
export async function request(path, body, method = 'POST') {
  if (body !== undefined && presentationEnabled()) throw new Error('Presentation mode is read-only. Turn it off to edit cases.')
  const response = await fetch(API + path, body === undefined ? {} : { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const result = await response.json()
  if (!response.ok) throw new Error(response.status === 409 ? 'This request conflicts with a newer edit or a reused request key. Reload the case before making a new decision.' : typeof result.detail === 'string' ? result.detail : `Request failed (${response.status})`)
  return result
}
export function useCommand() {
  const pending = useRef(new Map())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const running = useRef(false)
  async function run(path, body, method, done) {
    if (running.current) return
    running.current = true; setBusy(true); setError(null)
    const fingerprint = JSON.stringify([path, body, method])
    try {
      const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(API + fingerprint)))].map(x => x.toString(16).padStart(2, '0')).join('')
      const key = 'argus-workspace-request:' + hash
      if (!pending.current.has(fingerprint)) pending.current.set(fingerprint, sessionStorage.getItem(key) || crypto.randomUUID())
      sessionStorage.setItem(key, pending.current.get(fingerprint))
      const result = await request(path, { ...body, request_key: pending.current.get(fingerprint) }, method)
      pending.current.delete(fingerprint)
      sessionStorage.removeItem(key)
      await done(result)
    } catch (e) { setError(e.message) }
    finally { running.current = false; setBusy(false) }
  }
  return { run, busy, error, setError }
}
export function Frame({ title, children }) {
  const router = useRouter()
  const [masked, setMasked] = useState(false)
  useEffect(() => { setMasked(presentationEnabled()) }, [])
  const nav = [['/', 'Overview'], ['/workspace', 'Work queue'], ['/cases', 'Cases'], ['/entities', 'Entities'], ['/connections', 'Connections']]
  return <main className={'max-w-7xl mx-auto px-5 py-7 space-y-5 ' + (masked ? 'argus-presentation' : '')}><style jsx global>{`.argus-presentation form:not([data-readonly='true']),.argus-presentation [data-write-action]{display:none}`}</style><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs text-slate-500">Argus · workspace preview · isolated data copy</p><h1 className="text-2xl font-semibold text-slate-900">{display(title)}</h1></div><nav aria-label="Workspace navigation" className="flex flex-wrap gap-1 text-sm">{nav.map(([href,label]) => { const active = href === '/' ? router.pathname === '/' : router.pathname.startsWith(href); return <Link key={href} href={href} aria-current={active ? 'page' : undefined} className={'rounded-lg px-3 py-2 ' + (active ? 'bg-indigo-700 text-white' : 'text-slate-600 hover:bg-slate-200')}>{label}</Link> })}</nav></div><div className="text-xs text-slate-500 flex flex-wrap items-center gap-3"><button aria-pressed={masked} className="underline" onClick={() => { sessionStorage.setItem('argus-presentation', String(!masked)); window.location.reload() }}>Presentation mode: {masked ? 'on (read-only)' : 'off'}</button>{masked && <span>Visual masking only. API responses and URLs still contain native identifiers.</span>}</div>{children}</main>
}
export function ErrorNotice({ error }) { return error ? <p role="alert" className="border border-rose-200 bg-rose-50 text-rose-800 p-3 rounded-lg text-sm">{error}</p> : null }
export function Drawer({ title, close, children }) {
  const panel = useRef(null)
  useEffect(() => {
    const previous = document.activeElement
    panel.current?.focus()
    function key(event) {
      if (event.key === 'Escape') close()
      if (event.key !== 'Tab') return
      const elements = [...panel.current.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary')]
      const first = elements[0], last = elements[elements.length - 1]
      if (!first) { event.preventDefault(); return }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', key)
    return () => { document.body.style.overflow = overflow; document.removeEventListener('keydown', key); previous?.focus() }
  }, []) // The drawer is mounted per selection, not on each render.
  return <div className="fixed inset-0 z-50 bg-slate-900/30 flex justify-end"><section ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className="bg-white shadow-xl w-full max-w-xl h-full overflow-auto p-6 space-y-5"><div className="flex justify-between gap-4"><h2 className="text-lg font-semibold">{title}</h2><button className={secondary} onClick={close}>Close</button></div>{children}</section></div>
}
export function Facts({ value }) {
  return <dl className="text-sm space-y-2">{Object.entries(value || {}).filter(([key]) => key !== 'resource_value').map(([key, raw]) => { const item = key === 'resource' && value.resource_value != null ? value.resource_value : raw; return <div key={key} className="grid grid-cols-[minmax(100px,1fr)_2fr] gap-3"><dt className="text-slate-500 break-words">{key.replaceAll('_', ' ')}</dt><dd className="break-words min-w-0">{item == null || item === '' ? 'Unavailable' : typeof item === 'object' ? <details><summary>Structured details</summary><pre className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(displayValue(item), null, 2)}</pre></details> : display(String(item))}</dd></div> })}</dl>
}
