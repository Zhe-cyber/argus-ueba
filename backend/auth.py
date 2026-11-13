"""Workspace sign-in: local users file, scrypt password hashes, signed session cookie.

Users file and session secret live outside git (paths from config/env). Roles: analyst (may change
cases and findings) and viewer (read only). Sessions are held in memory (a restart signs everyone
out) behind an HMAC-signed, HTTP-only, SameSite=Strict cookie; 8 h idle expiry. Five failed
passwords lock that user name for 5 minutes. Failures are logged by user name, never the password.

  python -m backend.auth add-user <name> --role analyst --users-file <path>
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import getpass
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
import threading
import time

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROLES = ('analyst', 'viewer')
SCRYPT = {'n': 2 ** 14, 'r': 8, 'p': 1, 'dklen': 32}
IDLE_SECONDS = 8 * 3600
LOCK_AFTER, LOCK_SECONDS = 5, 300
NAME = re.compile(r'[A-Za-z0-9._-]{1,64}')
COOKIE = 'argus_session'
PUBLIC = {('POST', '/auth/login'), ('POST', '/auth/logout'), ('GET', '/health')}
CHANGING = {'POST', 'PUT', 'PATCH', 'DELETE'}
log = logging.getLogger('argus.auth')


def _hash(password, salt, params=SCRYPT):
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, maxmem=64 * 1024 * 1024, **params)


def make_record(password, role):
    if role not in ROLES:
        raise ValueError('Role must be analyst or viewer')
    if len(password) < 10:
        raise ValueError('Password must be at least 10 characters')
    salt = secrets.token_bytes(16)
    return {'role': role, 'salt': salt.hex(), 'hash': _hash(password, salt).hex(), 'scrypt': SCRYPT}


def read_users(path):
    path = Path(path)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 'argus_users_v1' or not isinstance(data.get('users'), dict):
        raise ValueError('Invalid users file')
    return data['users']


def add_user(path, name, role, password):
    if not NAME.fullmatch(name):
        raise ValueError('User name: 1-64 letters, digits, dot, dash or underscore')
    users = read_users(path)
    if name in users:
        raise ValueError('User already exists')
    users[name] = make_record(password, role)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps({'schema': 'argus_users_v1', 'users': users}, indent=2), encoding='utf-8')
    os.replace(temp, path)


def load_or_create_secret(path):
    """32 random bytes, created exclusively on first run; also records when sign-in started."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as out:
            out.write(secrets.token_bytes(32))
        (path.parent / 'auth-since.json').write_text(
            json.dumps({'sign_in_since_utc': datetime.now(timezone.utc).isoformat()}), encoding='utf-8')
    except FileExistsError:
        pass
    secret = path.read_bytes()
    if len(secret) < 32:
        raise ValueError('Session secret file is invalid')
    return secret


class AuthError(Exception):
    pass


class Login(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=1024)


class Auth:
    def __init__(self, users_file, secret_file, clock=time.time):
        self.users_file = Path(users_file)
        self.secret = load_or_create_secret(secret_file)
        since = Path(secret_file).parent / 'auth-since.json'
        self.since = json.loads(since.read_text(encoding='utf-8'))['sign_in_since_utc'] if since.is_file() else None
        self.clock = clock
        self.sessions = {}   # sid -> {'user', 'role', 'last'}
        self.failures = {}   # name -> [times]
        self.lock = threading.Lock()
        self._dummy = make_record('x' * 16, 'viewer')

    # -- cookie -----------------------------------------------------------------------------------
    def _sign(self, sid):
        return sid + '.' + base64.urlsafe_b64encode(hmac.new(self.secret, sid.encode(), 'sha256').digest()).decode().rstrip('=')

    def _unsign(self, value):
        sid, _, _ = (value or '').partition('.')
        return sid if sid and hmac.compare_digest(self._sign(sid), value) else None

    # -- operations -------------------------------------------------------------------------------
    def login(self, name, password):
        now = self.clock()
        with self.lock:
            if len(self.failures) > 1000:  # bound memory under name-spraying
                self.failures = {k: v for k, v in self.failures.items() if v and now - v[-1] < LOCK_SECONDS}
            recent = [t for t in self.failures.get(name, []) if now - t < LOCK_SECONDS]
            self.failures[name] = recent
            if len(recent) >= LOCK_AFTER:
                log.warning('sign-in refused: user %r locked', name[:64])
                raise AuthError('locked')
        record = read_users(self.users_file).get(name) if NAME.fullmatch(name or '') else None
        check = record or self._dummy  # same scrypt cost for unknown names
        ok = hmac.compare_digest(_hash(password or '', bytes.fromhex(check['salt']), check.get('scrypt', SCRYPT)).hex(), check['hash'])
        with self.lock:
            if not (record and ok):
                self.failures.setdefault(name, []).append(now)
                log.warning('sign-in failed for user %r', (name or '')[:64])
                raise AuthError('invalid')
            self.failures.pop(name, None)
            sid = secrets.token_urlsafe(32)
            self.sessions[sid] = {'user': name, 'role': record['role'], 'last': now}
        log.info('sign-in ok for user %r', name)
        return self._sign(sid)

    def session(self, cookie):
        sid = self._unsign(cookie)
        now = self.clock()
        with self.lock:
            entry = self.sessions.get(sid) if sid else None
            if entry is None:
                return None
            if now - entry['last'] > IDLE_SECONDS:
                self.sessions.pop(sid, None)
                return None
            entry['last'] = now
            return {'user': entry['user'], 'role': entry['role']}

    def logout(self, cookie):
        sid = self._unsign(cookie)
        with self.lock:
            if sid:
                self.sessions.pop(sid, None)


def install(app, auth, cookie_name=COOKIE, secure=False):
    """Every route needs a session except PUBLIC; changing routes need analyst + X-Argus-Request: 1.

    Install BEFORE CORSMiddleware so CORS stays outermost (preflights and 401s keep CORS headers).
    """
    app.state.auth = auth

    @app.middleware('http')
    async def enforce(request: Request, call_next):
        method, path = request.method, request.url.path
        if method == 'OPTIONS':
            return await call_next(request)
        if method in CHANGING and request.headers.get('x-argus-request') != '1':
            return JSONResponse({'detail': 'Missing X-Argus-Request header'}, status_code=403)
        if (method, path) not in PUBLIC:
            who = auth.session(request.cookies.get(cookie_name))
            if who is None:
                return JSONResponse({'detail': 'Sign-in required'}, status_code=401)
            if method in CHANGING and who['role'] != 'analyst':
                return JSONResponse({'detail': 'Your role cannot change cases or findings'}, status_code=403)
            request.state.user = who
        return await call_next(request)

    @app.post('/auth/login')
    def login(body: Login):
        try:
            token = auth.login(body.username, body.password)
        except AuthError as error:
            detail = 'Too many failed attempts; try again in 5 minutes' if str(error) == 'locked' else 'Wrong user name or password'
            return JSONResponse({'detail': detail}, status_code=401)
        who = auth.session(token)
        response = JSONResponse(who)
        response.set_cookie(cookie_name, token, httponly=True, samesite='strict', secure=secure, path='/', max_age=IDLE_SECONDS)
        return response

    @app.post('/auth/logout')
    def logout(request: Request):
        auth.logout(request.cookies.get(cookie_name))
        response = JSONResponse({'signed_out': True})
        response.delete_cookie(cookie_name, path='/', httponly=True, samesite='strict', secure=secure)
        return response

    @app.get('/auth/me')
    def me(request: Request):
        return {**request.state.user, 'sign_in_since_utc': auth.since}  # older audit rows: recorded before sign-in


def session_user(request, *ignored):
    """Name of the signed-in analyst. Client-supplied analyst/actor fields are ignored (and logged)."""
    who = getattr(request.state, 'user', None)
    if who is None:
        raise HTTPException(401, 'Sign-in required')
    if any(isinstance(v, str) and v.strip() for v in ignored):
        log.info('ignored client-supplied analyst field on %s (deprecated)', request.url.path)
    return who['user']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    add = sub.add_parser('add-user')
    add.add_argument('name')
    add.add_argument('--role', choices=ROLES, required=True)
    add.add_argument('--users-file', type=Path, default=os.environ.get('ARGUS_AUTH_USERS_FILE'))
    args = parser.parse_args(argv)
    if not args.users_file:
        parser.error('--users-file (or ARGUS_AUTH_USERS_FILE) is required')
    first = getpass.getpass('Password: ')
    if first != getpass.getpass('Repeat password: '):
        print('Passwords differ; no user added.')
        return 1
    try:
        add_user(args.users_file, args.name, args.role, first)
    except ValueError as error:
        print(f'No user added: {error}')
        return 1
    print(f'Added {args.name} ({args.role}).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
