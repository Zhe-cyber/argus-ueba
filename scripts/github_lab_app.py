"""Local GitHub App registration and repository-scoped installation authentication.

No workload execution or schedule installation. Private keys are DPAPI-encrypted.
The HTTP helper listens on loopback only, suppresses URL logs, and expires.
"""
import argparse
import base64
import ctypes
from ctypes import wintypes
import hashlib
import hmac
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from urllib.parse import parse_qs, urlsplit

import requests

OWNER = 'Zhe-cyber'
REPO = OWNER + '/argus-activity-lab'
PORT = 8774
ORIGIN = f'http://127.0.0.1:{PORT}'
ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / 'data/live/github-app-lab-v1'


def atomic(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
    os.replace(temp, path)


def dpapi(value, encrypt):
    if os.name != 'nt':
        raise ValueError('Current-user Windows DPAPI required')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    source, output = Blob(len(value), buffer), Blob()
    crypt, kernel = ctypes.WinDLL('crypt32', use_last_error=True), ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if encrypt:
        fun = crypt.CryptProtectData
        fun.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
                        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        args = [ctypes.byref(source), 'Argus lab GitHub App', None, None, None, 1, ctypes.byref(output)]
    else:
        fun = crypt.CryptUnprotectData
        fun.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        args = [ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)]
    fun.restype = wintypes.BOOL
    if not fun(*args):
        raise ValueError('Credential protection operation failed')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.memset(buffer, 0, len(value))
        ctypes.memset(output.data, 0, output.size)
        kernel.LocalFree(output.data)


def save_secret(path, data):
    # Encryption happens before a file is opened. No plaintext fallback.
    encrypted = dpapi(json.dumps(data).encode(), True)
    with Path(path).open('xb') as handle:
        handle.write(encrypted)


def load_secret(path):
    return json.loads(dpapi(Path(path).read_bytes(), False))


def api(method, path, token=None, body=None):
    if not path.startswith('/') or path.startswith('//') or '?' in path or '#' in path:
        raise ValueError('Invalid GitHub API path')
    with requests.Session() as session:
        session.trust_env = False
        headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        response = session.request(method, 'https://api.github.com'+path, json=body,
                                   headers=headers, timeout=30, allow_redirects=False)
        if not 200 <= response.status_code < 300:
            raise ValueError('GitHub API request failed: HTTP '+str(response.status_code))
        return response.json()


def gh(path):
    proc = subprocess.run(['gh', 'api', '--hostname', 'github.com', path],
                          capture_output=True, text=True, timeout=30)
    if proc.returncode:
        raise ValueError('GitHub CLI read failed')
    return json.loads(proc.stdout)


def manifest(state):
    return {'name': 'Argus Workload Lab ' + state[:8], 'url': 'https://github.com/'+REPO,
            'description': 'Controlled machine activity in the Argus toy repository; not human users.',
            # GitHub validates public reachability even for an inactive hook.
            # Reuse our existing protected endpoint; no webhook is subscribed.
            'hook_attributes': {'url': 'https://argus-access-demo.argus-lab-e98718.workers.dev/github-app-hook-disabled', 'active': False},
            'redirect_url': ORIGIN+'/callback', 'setup_url': ORIGIN+'/installed?state='+state,
            'public': False, 'default_permissions': {'contents': 'write', 'metadata': 'read'},
            'default_events': [], 'request_oauth_on_install': False}


def app_jwt(document):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    key = serialization.load_pem_private_key(document['pem'].encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError('RSA App key required')
    encode = lambda b: base64.urlsafe_b64encode(b).rstrip(b'=')
    now = int(time.time())
    payload = {'iat': now-60, 'exp': now+480, 'iss': str(document['id'])}
    unsigned = encode(b'{"alg":"RS256","typ":"JWT"}') + b'.' + encode(json.dumps(payload, separators=(',', ':')).encode())
    return (unsigned+b'.'+encode(key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256()))).decode()


def installation_token(secret, repo_id, installation_id):
    jwt = app_jwt(secret)
    install = api('GET', f'/app/installations/{installation_id}', jwt)
    if (install.get('account', {}).get('login', '').lower() != OWNER.lower()
            or install.get('app_id') != secret['id'] or install.get('repository_selection') != 'selected'
            or install.get('suspended_at') is not None
            or install.get('permissions') != {'contents': 'write', 'metadata': 'read'}):
        raise ValueError('Installation identity, scope or permissions differ')
    token = api('POST', f'/app/installations/{installation_id}/access_tokens', jwt,
                {'repository_ids': [repo_id], 'permissions': {'contents': 'write', 'metadata': 'read'}})
    metadata = api('GET', '/repos/'+REPO, token['token'])
    if metadata.get('id') != repo_id or metadata.get('private') is not True:
        raise ValueError('Expected private lab repository')
    return token['token']


def verify_repository_selection(secret, repo_id, installation_id):
    # The gh OAuth token is not a GitHub App user token. Use a metadata-only
    # installation token to inspect actual selection, before requesting writes.
    jwt = app_jwt(secret)
    install = api('GET', f'/app/installations/{installation_id}', jwt)
    if (install.get('account', {}).get('login', '').lower() != OWNER.lower()
            or install.get('app_id') != secret['id'] or install.get('repository_selection') != 'selected'
            or install.get('suspended_at') is not None
            or install.get('permissions') != {'contents': 'write', 'metadata': 'read'}):
        raise ValueError('Installation identity, scope or permissions differ')
    access = api('POST', f'/app/installations/{installation_id}/access_tokens', jwt,
                 {'permissions': {'metadata': 'read'}})
    inventory = api('GET', '/installation/repositories', access['token'])
    if inventory.get('total_count') != 1 or [r['id'] for r in inventory.get('repositories', [])] != [repo_id]:
        raise ValueError('Install only on argus-activity-lab')


def verify_saved_installation(directory=STATE_DIR):
    directory = Path(directory)
    public = json.loads((directory/'status.json').read_bytes())
    repository = json.loads((directory/'repository.json').read_bytes())
    if public['repo'] != REPO or repository['full_name'] != REPO or repository['id'] != public['repo_id']:
        raise ValueError('Lab repository binding differs')
    secret = load_secret(directory/'registration.dpapi')
    validate_registration(secret)
    installs = api('GET', '/app/installations', app_jwt(secret))
    if len(installs) != 1:
        raise ValueError('Expected exactly one App installation')
    installation_id = installs[0]['id']
    verify_repository_selection(secret, public['repo_id'], installation_id)
    installation_token(secret, public['repo_id'], installation_id)
    public.update(status='installed_verified', installation_id=installation_id, verified_at_unix=time.time())
    public.pop('error_type', None)
    atomic(directory/'status.json', public)
    return {'status': 'installed_verified', 'repo': REPO, 'background_workload_enabled': False}


def validate_registration(data):
    if (type(data.get('id')) is not int or data['id'] <= 0
            or data.get('owner', {}).get('login', '').lower() != OWNER.lower()
            or not re.fullmatch(r'argus-workload-lab-[a-z0-9-]+', data.get('slug', ''))
            or data.get('permissions') != {'contents': 'write', 'metadata': 'read'}):
        raise ValueError('App owner, slug or permissions differ')
    # Parse and sign once to verify the returned key format before use.
    app_jwt(data)


def serve(directory=STATE_DIR):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if (directory/'registration.dpapi').exists():
        raise ValueError('Registration already saved; inspect before another registration')
    repo = gh('repos/'+REPO)
    viewer = gh('user')
    if (viewer.get('login', '').lower() != OWNER.lower() or repo.get('private') is not True
            or repo.get('owner', {}).get('id') != viewer.get('id') or not repo.get('permissions', {}).get('admin')):
        raise ValueError('Owned private lab repository required')
    state, expires = secrets.token_urlsafe(32), time.time()+1800
    definition = manifest(state)
    public = {'status': 'awaiting_registration', 'repo': REPO, 'repo_id': repo['id'],
              'local_setup_url': ORIGIN+'/setup/'+state, 'expires_at_unix': expires,
              'model_activated': False, 'background_workload_enabled': False}
    atomic(directory/'status.json', public)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # OAuth-like one-time code/state must never enter access logs.

        def reply(self, status, body):
            encoded = ('<!doctype html><meta charset="utf-8"><title>Argus GitHub App setup</title>'
                       '<main style="font:18px system-ui;max-width:760px;margin:60px auto">'+body+'</main>').encode()
            self.send_response(status)
            for key, value in {'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store',
                               'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff',
                               'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action https://github.com; frame-ancestors 'none'"}.items():
                self.send_header(key, value)
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers(); self.wfile.write(encoded)

        def do_GET(self):
            if self.headers.get('Host') != f'127.0.0.1:{PORT}' or time.time() >= expires:
                return self.reply(403, 'Setup unavailable.')
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True)
            try:
                if parsed.path == '/setup/'+state:
                    if public['status'] != 'awaiting_registration':
                        return self.reply(409, 'Registration already received. Continue in the original tab.')
                    encoded = html.escape(json.dumps(definition), quote=True)
                    return self.reply(200, '<h1>Argus workload bot</h1><p>Create a private GitHub App with Contents read/write and Metadata read. Webhooks are disabled.</p>'
                                      '<p>On installation, choose <b>Only select repositories</b> and <b>argus-activity-lab</b> only.</p>'
                                      f'<form method="post" action="https://github.com/settings/apps/new?state={state}">'
                                      f'<input type="hidden" name="manifest" value="{encoded}"><button>Create GitHub App</button></form>')
                if parsed.path not in ('/callback', '/installed'):
                    return self.reply(404, 'Not found.')
                if len(query.get('state', [])) != 1 or not hmac.compare_digest(query['state'][0], state):
                    return self.reply(403, 'Setup state mismatch; no credentials requested.')
                if parsed.path == '/callback':
                    codes = query.get('code', [])
                    if public['status'] != 'awaiting_registration' or len(codes) != 1 or not re.fullmatch('[A-Za-z0-9_-]{1,256}', codes[0]):
                        return self.reply(409, 'Invalid or already-used registration callback.')
                    public['status'] = 'conversion_in_progress'
                    atomic(directory/'status.json', public)
                    data = api('POST', '/app-manifests/'+codes[0]+'/conversions')
                    save_secret(directory/'registration.dpapi', data)
                    validate_registration(data)
                    public.update(status='registered_awaiting_installation', app_id=data['id'], slug=data['slug'])
                    atomic(directory/'status.json', public)
                    return self.reply(200, '<h1>App credentials saved securely</h1><p>Next, install only on <b>argus-activity-lab</b>.</p>'
                                      f'<a href="https://github.com/apps/{html.escape(data["slug"])}/installations/new">Install workload bot</a>')
                ids = query.get('installation_id', [])
                if public['status'] not in ('registered_awaiting_installation', 'installed_verified') or len(ids) != 1 or not ids[0].isdigit():
                    return self.reply(400, 'Installation registration is missing.')
                installation_id = int(ids[0])
                secret = load_secret(directory/'registration.dpapi')
                verify_repository_selection(secret, repo['id'], installation_id)
                installation_token(secret, repo['id'], installation_id)
                public.update(status='installed_verified', installation_id=installation_id)
                atomic(directory/'status.json', public)
                return self.reply(200, '<h1>GitHub bot installation verified</h1><p>Access is restricted to the private lab repository. Background activity is not scheduled yet. Return to Argus.</p>')
            except Exception as error:
                public.update(status='setup_needs_inspection', error_type=type(error).__name__)
                atomic(directory/'status.json', public)
                return self.reply(500, 'Setup stopped safely. Return to Argus; do not copy codes, keys or response details.')

        def do_POST(self):
            self.reply(405, 'Local POST is disabled.')

    with HTTPServer(('127.0.0.1', PORT), Handler) as server:
        server.timeout = 1
        atomic(directory/'listener.json', {'pid': os.getpid(), 'port': PORT, 'expires_at_unix': expires})
        while time.time() < expires:
            server.handle_request()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['serve', 'verify'])
    args = parser.parse_args()
    try:
        if args.mode == 'serve':
            serve()
        else:
            print(json.dumps(verify_saved_installation()))
    except Exception as error:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        atomic(STATE_DIR/'startup-error.json', {'error_type': type(error).__name__})
        raise SystemExit(1)
