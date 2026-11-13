# L9 workspace sign-in: threat list (for the security review step)

Scope: `backend/auth.py`, its installation in `workspace_next/app.py`, the identity used by
`workspace_next/case_api.py`, and the UI (`pages/login.js`, `pages/_app.js`, `components/WorkspaceUI.js`).
The ingest backend (`backend.main`: `/`, `/ingest`) is a loopback-only machine interface and is not behind sign-in.

| Threat | Handling | Test |
|---|---|---|
| Unauthenticated access to data | Middleware: every route needs a session except `POST /auth/login`, `POST /auth/logout`, `GET /health` (returns only `{"status":"ok"}`) | `test_every_protected_route_needs_a_session` (all routes enumerated from the app) |
| Password disclosure at rest | `hashlib.scrypt` (n=2^14, r=8, p=1), 16-byte random salt per user; users file outside git | `test_add_user_cli_...`, `test_salts_differ...` |
| Password on command line / default account | `add-user` prompts twice with `getpass`; no default user; minimum 10 characters | `test_add_user_cli_...` |
| Online guessing | 5 failures lock that name for 5 minutes (also unknown names); generic error text; scrypt run for unknown names (similar timing) | `test_wrong_password_and_lockout` |
| Password in logs | Logger `argus.auth` records the user name and outcome only | asserted in `test_wrong_password_and_lockout` |
| Session theft via script | Cookie is HttpOnly; JS never sees it (checked in browser: `document.cookie` lacks it) | `test_login_sets_strict_http_only_cookie...` |
| Cookie forgery / tampering | Random 256-bit session id + HMAC-SHA256 signature with a 32-byte secret created exclusively on first run; constant-time compare; server-side session table | `test_tampered_cookie_is_rejected` |
| Stale sessions | 8 h idle expiry, refreshed on activity; logout deletes the server-side session; restart signs everyone out | `test_idle_session_expires...`, logout test |
| CSRF | SameSite=Strict cookie, plus every changing request (and login/logout) must carry `X-Argus-Request: 1`, which a cross-site form cannot send and CORS only allows from the configured UI origin | `test_missing_request_header_is_blocked` |
| Privilege misuse | Role `viewer` gets 403 on every changing route; UI hides change controls | `test_viewer_reads_but_cannot_change`, browser check |
| Analyst impersonation in audit | Analyst name comes from the session; client `actor`/`analyst` fields are accepted for one release, ignored and logged | `test_audit_rows_carry_the_session_user...` |
| Open redirect after login | `next` accepted only as a same-site path (`/...`, not `//`) | code review (login.js `safeNext`) |
| Login CSRF | Login also requires the custom header | `test_missing_request_header_is_blocked` |

Known limits (accepted for a single-laptop deployment): no TLS on loopback (cookie `Secure` flag off;
`install(..., secure=True)` when served over HTTPS); sessions are in memory (one process); a user
removed from the users file keeps an open session until idle expiry or restart; lockout state is in
memory and resets on restart; no password change command (re-create the users file entry).
Old audit rows keep their typed names and are shown as "recorded before sign-in" (based on the time
the session secret was first created).
