import '@/styles/globals.css'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import { request, setSession, useSession } from '@/components/WorkspaceUI'

// Sign-in gate: every page except /login renders only after /auth/me confirms a session;
// a 401 from any request sends the browser to /login.
export default function App({ Component, pageProps }) {
  const router = useRouter(), open = router.pathname === '/login'
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (open || useSession()) { setReady(true); return }
    setReady(false)
    request('/auth/me').then(value => { setSession(value); setReady(true) }).catch(() => {})
  }, [router.pathname])
  return <div className="min-h-screen bg-slate-100 text-slate-800">{ready || open ? <Component {...pageProps} /> : null}</div>
}
