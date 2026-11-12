import { useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import { ErrorNotice, request, setSession, field, button } from '@/components/WorkspaceUI'

// Only same-site paths are accepted as the return target (no open redirect).
const safeNext = value => typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') && !value.startsWith('/login') ? value : '/'

export default function Login() {
  const router = useRouter()
  const [username, setUsername] = useState(''), [password, setPassword] = useState('')
  const [error, setError] = useState(null), [busy, setBusy] = useState(false)
  async function submit(event) {
    event.preventDefault()
    setBusy(true); setError(null)
    try {
      await request('/auth/login', { username: username.trim(), password })
      setSession(await request('/auth/me'))
      setPassword('')
      router.replace(safeNext(router.query.next))
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <main className="max-w-sm mx-auto px-5 py-16 space-y-5"><Head><title>Argus — Sign in</title></Head>
    <div><p className="text-xs font-semibold tracking-wide text-indigo-700">Argus</p><h1 className="text-2xl font-semibold text-slate-900">Sign in</h1></div>
    <ErrorNotice error={error} />
    <form onSubmit={submit} className="bg-white border rounded-xl p-5 space-y-3">
      <label className="block text-sm">User name<input name="username" autoComplete="username" maxLength={64} className={field} value={username} onChange={e => setUsername(e.target.value)} required /></label>
      <label className="block text-sm">Password<input name="password" type="password" autoComplete="current-password" maxLength={1024} className={field} value={password} onChange={e => setPassword(e.target.value)} required /></label>
      <button disabled={busy} className={button}>{busy ? 'Signing in…' : 'Sign in'}</button>
    </form>
  </main>
}
