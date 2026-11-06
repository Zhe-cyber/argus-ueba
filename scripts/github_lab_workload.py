"""One real bot commissioning commit and native repository-activity round-trip.

No fabricated events, score writes, scheduler, project-repository writes or retries
of unknown provider actions. Secrets remain in memory/Windows DPAPI.
"""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import github_lab_app as app
from scripts.collect_live import LocalBackend

RECEIPT = app.STATE_DIR/'commissioning.json'


def context():
    status = json.loads((app.STATE_DIR/'status.json').read_bytes())
    if status.get('status') != 'installed_verified' or status.get('repo') != app.REPO:
        raise ValueError('Verified lab installation required')
    secret = app.load_secret(app.STATE_DIR/'registration.dpapi')
    token = app.installation_token(secret, status['repo_id'], status['installation_id'])
    return status, token


def check_commit(data, sha, slug):
    actor = data.get('author') or {}
    if (data.get('sha') != sha or actor.get('type') != 'Bot'
            or actor.get('login', '').lower() != (slug+'[bot]').lower()
            or type(actor.get('id')) is not int or actor['id'] <= 0):
        raise ValueError('Native commit is not attributed to the expected App bot')
    return actor['id']


def matches(event, receipt):
    if not isinstance(event, dict):
        return False
    payload, actor, repo = event.get('payload') or {}, event.get('actor') or {}, event.get('repo') or {}
    return (event.get('type') == 'PushEvent' and repo.get('id') == receipt['repo_id']
            and actor.get('id') == receipt['bot_actor_id']
            and (payload.get('head') == receipt['commit_sha']
                 or any(c.get('sha') == receipt['commit_sha'] for c in payload.get('commits', []) if isinstance(c, dict))))


def matches_activity(event, receipt):
    actor = event.get('actor') if isinstance(event, dict) else None
    return (isinstance(actor, dict) and actor.get('id') == receipt['bot_actor_id']
            and event.get('activity_type') == 'push' and event.get('after') == receipt['commit_sha'])


def commission():
    if RECEIPT.exists():
        raise ValueError('A commissioning claim already exists; reconcile it, never repeat it')
    backend = LocalBackend('http://127.0.0.1:8013')
    backend.preflight()
    status, token = context()
    content = {'provenance': 'controlled_machine_workload', 'purpose': 'one-time integration commissioning',
               'independent_human_user': False, 'at_utc': datetime.now(timezone.utc).isoformat()}
    claim = {'status': 'claimed_unknown', 'repo_id': status['repo_id'], 'repo': app.REPO,
             'slug': status['slug'], 'at_utc': content['at_utc'], 'model_activated': False}
    with RECEIPT.open('x', encoding='utf-8') as handle:
        json.dump(claim, handle, indent=2)
    result = app.api('PUT', '/repos/'+app.REPO+'/contents/workloads/commissioning.json', token,
                     {'message': '[Argus controlled machine workload] commissioning',
                      'content': base64.b64encode((json.dumps(content, indent=2)+'\n').encode()).decode()})
    sha = result['commit']['sha']
    claim.update(status='api_ok_identity_pending', commit_sha=sha)
    app.atomic(RECEIPT, claim)
    commit = app.api('GET', '/repos/'+app.REPO+'/commits/'+sha, token)
    claim.update(status='commit_verified_event_pending', bot_actor_id=check_commit(commit, sha, status['slug']))
    app.atomic(RECEIPT, claim)
    return {'status': claim['status'], 'bot_identity_verified': True, 'scheduled': False}


def reconcile():
    status, token = context()
    receipt = json.loads(RECEIPT.read_bytes())
    if receipt.get('repo_id') != status['repo_id'] or receipt.get('repo') != app.REPO:
        raise ValueError('Commissioning repository binding differs')
    if receipt.get('status') == 'ingested':
        return {'status': 'ingested', 'new_events': 0, 'scheduled': False}
    if receipt.get('status') not in ('commit_verified_event_pending', 'api_ok_identity_pending'):
        raise ValueError('Unknown action outcome needs manual read-only reconciliation')
    if receipt['status'] == 'api_ok_identity_pending':
        commit = app.api('GET', '/repos/'+app.REPO+'/commits/'+receipt['commit_sha'], token)
        receipt.update(status='commit_verified_event_pending', bot_actor_id=check_commit(commit, receipt['commit_sha'], status['slug']))
        app.atomic(RECEIPT, receipt)
    # The private lab uses repository activity exclusively. Never also ingest
    # its Events feed: both endpoints could describe the same underlying push.
    metadata = app.api('GET', '/repos/'+app.REPO, token)
    if (metadata.get('id') != receipt['repo_id'] or metadata.get('full_name') != app.REPO
            or metadata.get('private') is not True or type(metadata.get('owner', {}).get('id')) is not int):
        raise ValueError('Native repository request context differs')
    events = app.api('GET', '/repos/'+app.REPO+'/activity', token)
    if not isinstance(events, list) or len(events) > 30:
        raise ValueError('Unexpected bounded repository activity response')
    selected = [e for e in events if matches_activity(e, receipt)]
    if len(selected) > 1:
        raise ValueError('Ambiguous native activity evidence')
    if not selected:
        return {'status': 'awaiting_native_activity', 'provider_activity_rows': len(events), 'new_events': 0, 'scheduled': False}
    event = selected[0]
    from backend.github_activity import receipt_id, FORMAT
    event_id = receipt_id(receipt['repo_id'], event.get('id'))
    namespace = 'github-owner:'+str(metadata['owner']['id'])
    backend = LocalBackend('http://127.0.0.1:8013'); backend.preflight()
    # Forward original provider bytes as JSON values, without synthesized fields.
    # Persist exact provider evidence before requesting ingestion. Never
    # overwrite an earlier payload snapshot or fabricate an Events API record.
    import hashlib
    payload = json.dumps(event, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    archive = app.STATE_DIR/'native-activity'/ (hashlib.sha256(payload).hexdigest()+'.json')
    archive.parent.mkdir(parents=True, exist_ok=True)
    try:
        with archive.open('xb') as stream:
            stream.write(payload)
            stream.flush()
            import os
            os.fsync(stream.fileno())
    except FileExistsError:
        if archive.read_bytes() != payload:
            raise ValueError('Native activity archive differs')
    duplicate = backend.post_github_activity(namespace, app.REPO, receipt['repo_id'], event)
    if duplicate is None:
        raise ValueError('Local native receipt is missing; retry reconcile, not commit')
    receipt.update(status='ingested', event_id=event_id, native_activity_id=event['id'],
                   evidence_format=FORMAT, collection_authority='repository_activity_only',
                   event_timestamp=event['timestamp'],
                   source_account_id=namespace, ingested_at_utc=datetime.now(timezone.utc).isoformat())
    app.atomic(RECEIPT, receipt)
    return {'status': 'ingested', 'new_events': int(not duplicate), 'evidence_format': FORMAT, 'scheduled': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['commission', 'reconcile'])
    args = parser.parse_args()
    try:
        print(json.dumps(commission() if args.mode == 'commission' else reconcile()))
    except Exception as error:
        print(json.dumps({'status': 'stopped', 'error_type': type(error).__name__, 'scheduled': False}))
        raise SystemExit(1)
