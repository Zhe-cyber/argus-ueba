import { useEffect, useRef, useState } from 'react'
import Head from 'next/head'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { maskText } from '@/lib/presentationPrivacy.mjs'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8015'
// Masking is always on (display only): emails, 12-digit account numbers and IPs never render. Also product wording for the
// one API title that reads like a developer note (the API string itself is unchanged).
const WORDS = [[/First-seen action outside the UTC rule window/g, 'New action outside business hours'], [/outside the UTC rule window/g, 'outside business hours'], [/Account unavailable/g, 'Unknown account'], [/Diagnostic artifact unavailable./g, 'Diagnostic not ready yet.']]
export function display(value) {
  if (typeof value !== 'string') return value
  return WORDS.reduce((text, [from, to]) => text.replace(from, to), maskText(value))
}
function displayValue(value) {
  if (Array.isArray(value)) return value.map(displayValue)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key,item]) => [display(key), displayValue(item)]))
  return typeof value === 'number' && /^\d{12}$/.test(String(value)) ? '<account>' : display(value)
}
// Small info control: the caveat text renders only while open (hover, focus or click), so it stays reachable but off the page.
export function Info({ children, label = 'More information' }) {
  const [open, setOpen] = useState(false), [pinned, setPinned] = useState(false)
  const show = open || pinned
  return <span className="relative inline-block align-baseline" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}><button type="button" aria-label={label} aria-expanded={show} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onClick={() => setPinned(!pinned)} className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full border border-slate-400 text-[10px] leading-none text-slate-500 hover:bg-slate-100">i</button>{show && <span role="note" className="absolute left-0 top-5 z-40 w-64 rounded-lg border border-slate-300 bg-white p-2 text-xs font-normal text-slate-700 shadow-lg">{children}</span>}</span>
}
export const maskEmail = value => typeof value === 'string' && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) ? '[email hidden]' : value
export function FieldError({ show, children }) { return show ? <span role="alert" className="block text-xs text-rose-700 mt-1">{children}</span> : null }
export const field = 'rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm w-full'
export const button = 'rounded-lg bg-indigo-700 px-3 py-2 text-sm text-white disabled:opacity-50'
export const secondary = 'rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm disabled:opacity-50'
export const when = value => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString('en-GB', { timeZone: 'Asia/Kuala_Lumpur' }) + ' MYT' : '—'
// Signed-in session (set by the sign-in gate in _app.js). Viewers get no change controls.
let session = null
export const setSession = value => { session = value }
export const useSession = () => session
export const canChange = value => value?.role === 'analyst'
export const beforeSignIn = (value, at) => !value?.sign_in_since_utc || Date.parse(at) < Date.parse(value.sign_in_since_utc)
export async function request(path, body, method = 'POST') {
  // Cookie session (HTTP-only, set by the API); the header marks requests as coming from this UI.
  const init = { credentials: 'include', headers: { 'X-Argus-Request': '1' } }
  const response = await fetch(API + path, body === undefined ? init : { ...init, method, headers: { ...init.headers, 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (response.status === 401 && path !== '/auth/login' && typeof window !== 'undefined' && window.location.pathname !== '/login') {
    session = null
    window.location.assign('/login?next=' + encodeURIComponent(window.location.pathname + window.location.search))
    throw new Error('Sign-in required')
  }
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
async function signOut() {
  try { await request('/auth/logout', {}) } catch {}
  session = null
  window.location.assign('/login')
}
const ago = seconds => seconds < 60 ? seconds + 's' : seconds < 3600 ? Math.floor(seconds / 60) + 'm' : Math.floor(seconds / 3600) + 'h'
export function Frame({ title, children }) {
  const router = useRouter()
  const [pass, setPass] = useState(null), [now, setNow] = useState(Date.now()), [rehearsal, setRehearsal] = useState(false)
  useEffect(() => { try { sessionStorage.removeItem('argus-presentation') } catch {} request('/workspace/status').then(v => setRehearsal(v.rehearsal === true)).catch(() => {}) }, [])
  useEffect(() => {
    let active = true
    const check = () => request('/workspace/mirror-status').then(v => { if (active) { setPass(Date.parse(v.last_pass_utc) || null); setNow(Date.now()) } }).catch(() => { if (active) setPass(null) })
    check(); const timer = setInterval(check, 30000), tick = setInterval(() => setNow(Date.now()), 5000)
    return () => { active = false; clearInterval(timer); clearInterval(tick) }
  }, [])
  const nav = [['/', 'Overview'], ['/workspace', 'Work queue'], ['/cases', 'Cases'], ['/entities', 'Entities'], ['/connections', 'Connections']]
  const shown = display(title), live = pass != null && now - pass < 300000
  return <main className="max-w-7xl mx-auto px-5 py-7 space-y-5"><Head><title>{'Argus — ' + shown}</title></Head><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold tracking-wide text-indigo-700">Argus</p><h1 className="text-2xl font-semibold text-slate-900">{shown}</h1><div className="mt-1 flex flex-wrap gap-2 text-xs">{live ? <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-emerald-800">Live · updated {ago(Math.max(0, Math.floor((now - pass) / 1000)))} ago</span> : pass != null && <span className="rounded-full bg-slate-200 px-2 py-0.5 text-slate-600">Data as of {when(new Date(pass).toISOString())}</span>}{rehearsal && <span className="rounded-full border border-amber-400 bg-amber-100 px-2 py-0.5 font-semibold text-amber-900">Simulated scenario</span>}</div></div><nav aria-label="Workspace navigation" className="flex flex-wrap gap-1 text-sm">{nav.map(([href,label]) => { const active = href === '/' ? router.pathname === '/' : router.pathname.startsWith(href); return <Link key={href} href={href} aria-current={active ? 'page' : undefined} className={'rounded-lg px-3 py-2 ' + (active ? 'bg-indigo-700 text-white' : 'text-slate-600 hover:bg-slate-200')}>{label}</Link> })}</nav>{session && <div className="flex items-center gap-2 text-sm text-slate-600"><span data-testid="signed-in-user">{display(session.user)} · {session.role}</span><button className={secondary} onClick={signOut}>Sign out</button></div>}</div>{children}<footer className="border-t pt-3 text-xs text-slate-500"><Link href="/about" className="hover:underline">Method &amp; limits</Link></footer></main>
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
  return <dl className="text-sm space-y-2">{Object.entries(value || {}).filter(([key]) => key !== 'resource_value').map(([key, raw]) => { const item = key === 'resource' && value.resource_value != null ? value.resource_value : raw; return <div key={key} className="grid grid-cols-[minmax(100px,1fr)_2fr] gap-3"><dt className="text-slate-500 break-words">{key.replaceAll('_', ' ')}</dt><dd className="break-words min-w-0">{item == null || item === '' ? '—' : typeof item === 'object' ? <details><summary>Structured details</summary><pre className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(displayValue(item), null, 2)}</pre></details> : display(String(item))}</dd></div> })}</dl>
}
