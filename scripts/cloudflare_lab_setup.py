"""Isolated Cloudflare machine-lab preflight and one encrypted service token.

No schedule, human login automation, model activation or existing-app mutation.
"""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.setup_cloudflare import Cloudflare, load_token, APIError
from scripts.github_lab_app import save_secret, dpapi, atomic

STATE = ROOT/'data/live/cloudflare-workload-lab-v1'
NAME = 'argus-machine-lab-persona-01'
EXPIRY = datetime(2026, 11, 14, 16, tzinfo=timezone.utc)
PILOT = Path('C:/Users/yyzhe/.codex/worktrees/argus-cloud-live/fyp-ueba/data/live/pilot-local-v1/config.json')


def api():
    cfg = json.loads(PILOT.read_bytes())
    account = cfg['cloudflare']['account']
    if not re.fullmatch('[0-9a-f]{32}', account):
        raise ValueError('Existing Cloudflare account required')
    return Cloudflare(account, load_token(account))


def inspect(client):
    tokens = client.all('access/service_tokens')
    apps = client.all('access/apps')
    scripts = client.all('workers/scripts')
    subdomain = client.call('GET', 'workers/subdomain')['subdomain']
    if not re.fullmatch('[a-z0-9-]+', subdomain):
        raise ValueError('Existing Workers subdomain required')
    return tokens, {'apps': len(apps), 'workers': len(scripts),
                    'service_tokens': len(tokens), 'token_name_collision': any(t.get('name') == NAME for t in tokens),
                    'proposed_worker': 'argus-machine-lab',
                    'worker_name_collision': any(s.get('id') == 'argus-machine-lab' for s in scripts),
                    'host': 'argus-machine-lab.'+subdomain+'.workers.dev'}


def create_token(client, state=STATE, now=None):
    state = Path(state)
    now = now or datetime.now(timezone.utc)
    if now >= EXPIRY:
        raise ValueError('Pilot is expired')
    if (state/'persona-01.dpapi').exists():
        raise ValueError('Credential already saved; inspect instead of creating again')
    prior = state/'token-attempt.json'
    if prior.exists() and json.loads(prior.read_bytes()).get('status') != 'permission_denied':
        raise ValueError('Previous outcome needs inspection; no automatic retry')
    _, summary = inspect(client)
    if summary['token_name_collision'] or summary['worker_name_collision']:
        raise ValueError('Same-name lab resource requires inspection')
    probe = b'argus-nonsecret-protection-test'
    if dpapi(dpapi(probe, True), False) != probe:
        raise ValueError('Local credential protection failed before provider mutation')
    state.mkdir(parents=True, exist_ok=True)
    claim = {'status': 'claimed_unknown', 'at_utc': now.isoformat(), 'name': NAME,
             'account': client.account, 'expires_no_later_than': EXPIRY.isoformat(),
             'scheduled': False, 'model_activated': False}
    atomic(prior, claim)
    try:
        token = client.call('POST', 'access/service_tokens',
                            {'name': NAME, 'duration': str(int((EXPIRY-now).total_seconds()))+'s'})
    except APIError as error:
        if error.status == 403:
            claim.update(status='permission_denied', http_status=403)
            atomic(prior, claim)
        raise
    # Only ciphertext is written, including the one-time client secret.
    save_secret(state/'persona-01.dpapi', token)
    if not token.get('id') or not token.get('client_id') or not token.get('client_secret'):
        raise ValueError('Incomplete token response; encrypted response retained')
    claim.update(status='created_encrypted', token_id=token['id'])
    atomic(prior, claim)
    atomic(state/'scope.json', {'account': client.account, 'token_id': token['id'],
                               'token_name': NAME, 'host': summary['host'],
                               'scheduled': False, 'model_activated': False})
    return {'status': 'commissioning_token_created_encrypted', 'scheduled': False,
            'existing_app_changed': False, 'app_deployed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['inspect', 'create-commission-token'])
    args = parser.parse_args()
    try:
        client = api()
        print(json.dumps(inspect(client)[1] if args.mode == 'inspect' else create_token(client)))
    except Exception as error:
        result = {'status': 'stopped', 'error_type': type(error).__name__, 'scheduled': False}
        if isinstance(error, APIError):
            result['http_status'] = error.status
        STATE.mkdir(parents=True, exist_ok=True)
        atomic(STATE/'last-setup-status.json', result)
        print(json.dumps(result))
        raise SystemExit(1)
