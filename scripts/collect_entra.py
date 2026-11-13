"""Microsoft Entra ID sign-in connector (READY, NOT CONNECTED): bounded one-shot poll of Graph
GET /v1.0/auditLogs/signIns into a LOCAL Argus backend as source azure_ad.

Needs an Entra ID P1/P2 tenant and an app registration with AuditLog.Read.All (application, admin consent).
The client secret is read from a file outside the repo and is never printed, logged or put in an error.
`check` validates config and prints what would be called, with no network access.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.collect_live import CollectionError, LocalBackend, stats, valid_time  # noqa: E402

TOKEN_URL = 'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token'
SIGNINS_URL = 'https://graph.microsoft.com/v1.0/auditLogs/signIns'
SCOPE = 'https://graph.microsoft.com/.default'
GUID = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
PACE_SECONDS = 2.0      # Graph allows 5 requests / 10 s per app per tenant
MAX_RETRY_AFTER = 120   # never sleep longer than this on one 429
MAX_429_RETRIES = 3
DEFAULTS = dict(api='http://127.0.0.1:8000', page_size=100, max_requests=20, overlap_minutes=60,
                initial_lookback_hours=24)


def load_config(path):
    """Validate the config file. The secret itself is read separately (read_secret)."""
    try:
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise CollectionError('Config file missing or not valid JSON.') from None
    if not isinstance(raw, dict):
        raise CollectionError('Config must be a JSON object.')
    config = {**DEFAULTS, **{k: v for k, v in raw.items() if not k.startswith('_')}}
    for key in ('tenant_id', 'client_id'):
        if not isinstance(config.get(key), str) or not GUID.fullmatch(config[key]):
            raise CollectionError(f'{key} must be a GUID.')
    for key in ('client_secret_file', 'state_file'):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise CollectionError(f'{key} is required.')
        if Path(config[key]).resolve().is_relative_to(ROOT):
            raise CollectionError(f'{key} must live outside the repository.')
    for key, lo, hi in (('page_size', 1, 999), ('max_requests', 1, 200), ('overlap_minutes', 0, 1440),
                        ('initial_lookback_hours', 1, 720)):
        if type(config[key]) is not int or not lo <= config[key] <= hi:
            raise CollectionError(f'{key} must be an integer in {lo}..{hi}.')
    return config


def read_secret(config):
    try:
        secret = Path(config['client_secret_file']).read_text(encoding='utf-8').strip()
    except OSError:
        raise CollectionError('Client secret file is unreadable.') from None
    if not secret:
        raise CollectionError('Client secret file is empty.')
    return secret


def get_token(config, http):
    try:
        response = http.post(TOKEN_URL.format(tenant=config['tenant_id']), timeout=30, data={
            'grant_type': 'client_credentials', 'client_id': config['client_id'],
            'client_secret': read_secret(config), 'scope': SCOPE})
        token = response.json().get('access_token') if response.status_code == 200 else None
    except (requests.RequestException, ValueError, AttributeError):
        token = None
    if not isinstance(token, str) or not token:
        # Body is deliberately not echoed: error responses can repeat request values.
        raise CollectionError('Token request failed; check tenant, client id and secret.')
    return token


def load_watermark(config, now):
    try:
        value = json.loads(Path(config['state_file']).read_text(encoding='utf-8'))['watermark']
        if valid_time(value):
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return now - timedelta(hours=config['initial_lookback_hours'])


def save_watermark(config, mark):
    path = Path(config['state_file'])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps({'watermark': mark.strftime('%Y-%m-%dT%H:%M:%SZ')}), encoding='utf-8')
    tmp.replace(path)


def first_url(config, since):
    stamp = since.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return f"{SIGNINS_URL}?$filter=createdDateTime ge {stamp}&$top={config['page_size']}"


def graph_get(http, url, token, sleep):
    """One GET honouring 429 Retry-After. Returns (json, requests_used)."""
    used = 0
    for _ in range(MAX_429_RETRIES + 1):
        used += 1
        try:
            response = http.get(url, headers={'Authorization': 'Bearer ' + token}, timeout=60)
        except requests.RequestException:
            raise CollectionError('Graph request failed.') from None
        if response.status_code == 429:
            try:
                wait = float(response.headers.get('Retry-After', PACE_SECONDS * 5))
            except (TypeError, ValueError):
                wait = PACE_SECONDS * 5
            sleep(min(max(wait, 0), MAX_RETRY_AFTER))
            continue
        if response.status_code != 200:
            raise CollectionError(f'Graph returned HTTP {response.status_code}; '
                                  'check AuditLog.Read.All admin consent and the P1/P2 licence.')
        try:
            body = response.json()
        except ValueError:
            raise CollectionError('Graph returned a non-JSON body.') from None
        if not isinstance(body, dict):
            raise CollectionError('Unexpected Graph response.')
        return body, used
    raise CollectionError('Graph kept throttling (429); try again later.')


def collect_entra(config, backend, now, http=None, sleep=time.sleep):
    """One bounded poll. The watermark only advances when every record was committed and the
    backlog was fully drained; otherwise the next run re-reads the window (dedup makes that safe)."""
    http = http or _session()
    token = get_token(config, http)
    since = load_watermark(config, now) - timedelta(minutes=config['overlap_minutes'])
    url, requests_used, newest = first_url(config, since), 0, None
    counts = {**stats(), 'requests': 0, 'drained': True}
    while url:
        if requests_used >= config['max_requests']:
            counts['drained'] = False
            break
        if requests_used:
            sleep(PACE_SECONDS)
        body, used = graph_get(http, url, token, sleep)
        requests_used += used
        for record in body.get('value') or []:
            counts['received'] += 1
            native = record.get('id') if isinstance(record, dict) else None
            stamp = record.get('createdDateTime') if isinstance(record, dict) else None
            if not isinstance(native, str) or not native.strip() or not valid_time(stamp):
                counts['malformed'] += 1
                counts['retained'] += 1
                continue
            duplicate = backend.post('azure_ad', config['tenant_id'], record, native)
            if duplicate is None:
                counts['retained'] += 1
                continue
            counts['duplicates' if duplicate else 'inserted'] += 1
            moment = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
            newest = moment if newest is None or moment > newest else newest
        url = body.get('@odata.nextLink')
        if url and not url.startswith(SIGNINS_URL + '?'):
            raise CollectionError('Refusing a nextLink outside the Graph signIns endpoint.')
    counts['requests'] = requests_used
    # ponytail: Graph lists newest first; with a capped backlog the watermark stays put. Raise max_requests.
    if counts['drained'] and not counts['retained'] and newest is not None:
        save_watermark(config, newest)
    return counts


def _session():
    session = requests.Session()
    session.trust_env = False
    return session


def describe(config):
    first = datetime.now(timezone.utc) - timedelta(hours=config['initial_lookback_hours'])
    return [f"POST {TOKEN_URL.format(tenant=config['tenant_id'])}  (client_credentials, scope {SCOPE}; secret read from file, not shown)",
            f"GET  {first_url(config, first)}  (first run; later runs start at watermark minus {config['overlap_minutes']} min)",
            f"follow @odata.nextLink, at most {config['max_requests']} requests, {PACE_SECONDS}s between pages, honour 429 Retry-After",
            f"POST {config['api']}/ingest  source=azure_ad  source_account_id={config['tenant_id']}  event_id=signIn id",
            f"watermark file: {config['state_file']}"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'collect'])
    parser.add_argument('--config', default=str(ROOT / 'config' / 'entra.json'))
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == 'check':
            read_secret(config)  # exists and non-empty; contents never shown
            print('Config OK. Would call (check itself calls nothing):')
            print('\n'.join('  ' + line for line in describe(config)))
            return 0
        backend = LocalBackend(config['api'])
        backend.preflight()
        result = collect_entra(config, backend, datetime.now(timezone.utc))
        print(json.dumps({'source': 'azure_ad', 'bounded_sample': True, **result}))
        return 1 if result['retained'] or not result['drained'] else 0
    except CollectionError as exc:
        print(f'Collection stopped: {exc}', file=sys.stderr)
        return 1
    except Exception:
        print('Collection stopped unexpectedly. No raw records or errors displayed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
