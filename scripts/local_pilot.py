"""Guarded laptop pilot. No new model, provider permissions or fabricated events."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MY = timezone(timedelta(hours=8))
API = 'http://127.0.0.1:8013'
BACKEND_TASK = 'Argus-Pilot-Backend'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
LEGACY_PROFILE_SHA = '98bf9d641823d7764e510f3ff944c365f109ca9941349bf3f51788f92a74566b'
PROFILE_SHA = '150529b73fa71ac75eab06b162ad4bc913d7d0a19e3ff52c009d60ef3ba3899c'
RUNTIME_SCRIPTS = ('local_pilot.py', 'run_persona_history.py', 'persona_history_plan.py',
                   'run_simulation.py', 'simulation_lab.py', 'collect_live.py', 'setup_cloudflare.py')
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def now_utc():
    return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temp, path)


def pinned_sources():
    files = [p for p in (ROOT / 'backend').rglob('*.py') if 'tests' not in p.parts]
    files += [ROOT / 'scripts' / name for name in RUNTIME_SCRIPTS]
    files += [ROOT / 'scripts/persona_profiles_v1.json', ROOT / 'scripts/persona_profiles_v2.json', ROOT / 'infra/aws-live.json', ROOT / 'infra/aws-simulation.json']
    init = ROOT / 'scripts/__init__.py'
    if init.exists():
        files.append(init)
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(files)}


def read_scope(ledger_dir):
    path = Path(ledger_dir) / 'ledger.db'
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT contract FROM scope WHERE id=1').fetchone()
    if row is None:
        raise ValueError('Existing pinned actor ledger required')
    return json.loads(row[0])


def validate(cfg):
    if (cfg.get('schema') != 'argus_local_pilot_v2' or Path(cfg['source_root']).resolve() != ROOT
            or cfg.get('api') != API or cfg.get('actor_start') != '2026-10-29'
            or cfg.get('end_local') != '2026-11-14' or cfg.get('actor_end') != '2026-11-13' or cfg.get('repo') != 'Zhe-cyber/argus-ueba'
            or cfg.get('stack') != 'argus-ueba-actors' or re.fullmatch('[0-9a-f]{32}', cfg.get('runtime_id', '')) is None
            or re.fullmatch('[0-9]{12}', cfg.get('account_id', '')) is None):
        raise ValueError('Unsupported pilot scope')
    console, hidden = Path(cfg['python']), Path(cfg['pythonw'])
    if (not console.is_file() or not hidden.is_file() or console.name.lower() != 'python.exe'
            or hidden.name.lower() != 'pythonw.exe' or console.parent != hidden.parent):
        raise ValueError('Existing hidden and console Python pair required')
    if not Path(cfg['gh']).is_file() or Path(cfg['gh']).name.lower() != 'gh.exe':
        raise ValueError('Existing GitHub CLI required')
    state, connected, ledger = (Path(cfg[k]).resolve() for k in ('state_dir', 'connected_dir', 'ledger_dir'))
    if (connected.name != 'connected' or ledger.name != 'persona-history-v1'
            or connected.parent != ledger.parent or state.parent != connected.parent
            or state.name != 'pilot-local-v1' or not (connected / 'events.db').is_file()):
        raise ValueError('Require the existing connected store and sibling pilot ledger')
    if read_scope(ledger) != [cfg['account_id'], cfg['stack'], PROFILE_SHA]:
        raise ValueError('Existing actor ledger scope differs')
    with sqlite3.connect((ledger / 'ledger.db').as_uri() + '?mode=ro', uri=True) as claims:
        verified = claims.execute("SELECT native_event_id FROM actions WHERE status='provider_verified'").fetchall()
    with sqlite3.connect((connected / 'events.db').as_uri() + '?mode=ro', uri=True) as events:
        if not verified or not any(events.execute('SELECT 1 FROM events WHERE source=? AND source_account_id=? AND event_id=?',
                                                   ('aws_cloudtrail', cfg['account_id'], row[0])).fetchone() for row in verified):
            raise ValueError('Native connected store does not match the existing verified ledger')
    expected_queue = f"https://sqs.us-east-1.amazonaws.com/{cfg['account_id']}/argus-ueba-live-events"
    if cfg.get('queue_url') != expected_queue:
        raise ValueError('Only the existing collection queue is supported')
    cf = cfg.get('cloudflare')
    if cf is not None and (not isinstance(cf, dict) or re.fullmatch('[0-9a-f]{32}', cf.get('account', '')) is None
                           or re.fullmatch('[0-9a-f-]{36}', cf.get('app_id', '')) is None):
        raise ValueError('Invalid Cloudflare app scope')
    if (cfg.get('source_hashes') != pinned_sources() or sha(ROOT / 'scripts/persona_profiles_v2.json') != PROFILE_SHA
            or sha(ROOT / 'scripts/persona_profiles_v1.json') != LEGACY_PROFILE_SHA):
        raise ValueError('Pinned runtime source changed')
    return cfg


def expected_health(cfg):
    path = str((Path(cfg['connected_dir']) / 'events.db').resolve()).casefold()
    return {'runtime_id': cfg['runtime_id'], 'database_path_sha256': hashlib.sha256(path.encode()).hexdigest(),
            'source_sha256': digest(cfg['source_hashes']), 'application_mode': 'live',
            'cloud_model_profile': 'unverified', 'storage': 'sqlite'}


def health(cfg):
    import requests
    with requests.Session() as session:
        session.trust_env = False
        try:
            response = session.get(API + '/pilot-health', timeout=2, allow_redirects=False)
        except requests.ConnectionError:
            return False
        if response.status_code != 200 or response.json() != expected_health(cfg):
            raise ValueError('Unexpected listener or live-store identity')
    return True


def ensure_backend(cfg):
    if health(cfg):
        return
    subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32/schtasks.exe'), '/Run', '/TN', BACKEND_TASK],
                   capture_output=True, timeout=15, check=False, creationflags=NO_WINDOW)
    for _ in range(60):
        if health(cfg):
            return
        time.sleep(.5)
    raise ValueError('Owned backend task did not become ready')


def command(cfg, script, arguments, timeout=150):
    env = os.environ.copy()
    env['DATABASE_URL'] = 'sqlite-local'
    env['PATH'] = str(Path(cfg['gh']).parent) + os.pathsep + env.get('PATH', '')
    try:
        result = subprocess.run([cfg['python'], str(ROOT / 'scripts' / script), *arguments], cwd=ROOT,
                                env=env, capture_output=True, text=True, timeout=timeout,
                                creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {'ok': False, 'status': 'timeout_unknown_attempts_require_review'}
    report = {'ok': result.returncode == 0, 'exit_code': result.returncode}
    try:
        value = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        report['ok'] = False
        return report
    if not isinstance(value, dict):
        return {'ok': False, 'status': 'unexpected_child_output'}
    for key in ('received', 'inserted', 'duplicates', 'retained', 'malformed', 'skipped', 'acknowledged',
                'new_actions', 'newly_provider_verified', 'pending_or_ambiguous', 'reserved_sdk_calls_today'):
        if type(value.get(key)) is int:
            report[key] = value[key]
    if value.get('status') in ('no_due_actions', 'api_calls_completed_audit_pending'):
        report['status'] = value['status']
    if isinstance(value.get('action_states'), dict) and all(k in {'claimed_unknown', 'api_ok_audit_pending', 'provider_verified', 'missed'} and type(v) is int
                                                         for k, v in value['action_states'].items()):
        report['action_states'] = value['action_states']
    return report


def unknown_claims(cfg):
    path = Path(cfg['ledger_dir']) / 'ledger.db'
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        return db.execute("SELECT count(*) FROM actions WHERE status='claimed_unknown'").fetchone()[0]


def tick(cfg, now=None):
    fixed_clock = now is not None
    now = now or now_utc()
    day = now.astimezone(MY).date().isoformat()
    result = {'at_utc': now.isoformat(), 'date_local': day, 'model_activated': False,
              'coverage': 'operational_tick_not_complete_source_or_normal_day', 'phases': {}}
    if day > cfg['end_local']:
        return {**result, 'status': 'pilot_expired', 'ok': True}
    ensure_backend(cfg)
    phases = result['phases']
    phases['aws'] = command(cfg, 'collect_live.py', ['--api', API, 'aws', '--account-id', cfg['account_id'],
                                                    '--queue-url', cfg['queue_url'], '--profile', 'argus-collector', '--batches', '5'])
    unknown = unknown_claims(cfg)
    actor_day = (now if fixed_clock else now_utc()).astimezone(MY).date().isoformat()
    if actor_day > cfg['actor_end']:
        phases['actors'] = {'ok': True, 'status': 'pilot_expired'}
    elif actor_day < cfg['actor_start']:
        phases['actors'] = {'ok': True, 'status': 'starts_2026_10_29'}
    elif not phases['aws']['ok'] or unknown:
        phases['actors'] = {'ok': False, 'status': 'blocked_collection_or_unknown_claims', 'unknown_claims': unknown}
    else:
        phases['actors'] = command(cfg, 'run_persona_history.py', ['--account-id', cfg['account_id'], '--stack', cfg['stack'],
                                                                 '--profile', 'argus-simulator', '--state-dir', cfg['ledger_dir'], '--execute'], timeout=360)
    phases['audit'] = command(cfg, 'run_persona_history.py', ['--account-id', cfg['account_id'], '--state-dir', cfg['ledger_dir'],
                                                            '--audit-events', str(Path(cfg['connected_dir']) / 'events.db')], timeout=60)
    poll_path = Path(cfg['state_dir']) / 'poll_state.json'
    polls = json.loads(poll_path.read_text()) if poll_path.exists() else {}
    sources = {'github': ['github', '--repo', cfg['repo']]}
    if cfg.get('cloudflare'):
        sources['cloudflare'] = ['cloudflare', '--account-id', cfg['cloudflare']['account'], '--app-id', cfg['cloudflare']['app_id']]
    else:
        phases['cloudflare'] = {'ok': False, 'status': 'not_configured'}
    for source, args in sources.items():
        previous = polls.get(source, {})
        last = datetime.fromisoformat(previous['last_attempt']) if previous else None
        if last is not None and now - last < timedelta(minutes=30):
            phases[source] = {'ok': previous['last_outcome']['ok'],
                              'status': 'not_due_previous_success' if previous['last_outcome']['ok'] else 'not_due_previous_failure',
                              'last_attempt': previous['last_attempt'], 'previous_outcome': previous['last_outcome']}
            continue
        polls[source] = {'last_attempt': now.isoformat(), 'last_outcome': {'ok': False, 'status': 'poll_claimed_outcome_unknown'}}
        atomic_json(poll_path, polls)
        phases[source] = command(cfg, 'collect_live.py', ['--api', API, *args])
        polls[source]['last_outcome'] = phases[source]
        atomic_json(poll_path, polls)
    result['ok'] = all(p['ok'] for p in phases.values())
    result['status'] = 'completed' if result['ok'] else 'partial_failure_review_required'
    return result


@contextmanager
def lock(path):
    import msvcrt
    with Path(path).open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def hidden_streams(state_dir):
    if sys.stdout is not None and sys.stderr is not None:
        return None
    stream = (Path(state_dir) / 'backend-service.log').open('a', encoding='utf-8', buffering=1)
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    return stream


def serve(cfg):
    if now_utc().astimezone(MY).date().isoformat() > cfg['end_local']:
        return
    hidden_streams(cfg['state_dir'])  # pythonw has no console; Uvicorn formatters need a real stream.
    env = {'DATABASE_URL': 'sqlite-local', 'ARGUS_MODE': 'live', 'DEMO_MODE': 'false',
           'CLOUD_MODEL_PROFILE': 'unverified', 'LIVE_STATE_DIR': cfg['connected_dir'], 'ADMIN_TOKEN': '',
           'ALLOWED_ORIGINS': 'http://localhost:3000,http://127.0.0.1:3000'}
    os.environ.update(env)
    from backend import config, event_store
    from backend.main import app
    if (event_store._PG or Path(event_store.DB_PATH).resolve() != (Path(cfg['connected_dir']) / 'events.db').resolve()
            or not config.LIVE_MODE or config.CLOUD_MODEL_PROFILE != 'unverified'):
        raise ValueError('Backend storage/mode mismatch')
    def readiness():
        return expected_health(cfg)
    app.add_api_route('/pilot-health', readiness, include_in_schema=False)
    import threading
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8013, log_level='warning', access_log=False))
    end = datetime.fromisoformat(cfg['end_local']).replace(tzinfo=MY) + timedelta(days=1)
    timer = threading.Timer(max(0, (end - now_utc()).total_seconds()), lambda: setattr(server, 'should_exit', True))
    timer.daemon = True
    timer.start()
    try:
        server.run()
    finally:
        timer.cancel()


def initialize(live_dir, config_path):
    live, config_path = Path(live_dir).resolve(), Path(config_path).resolve()
    state = live / 'pilot-local-v1'
    if config_path != state / 'config.json' or config_path.exists():
        raise ValueError('Require a new sibling pilot config')
    scope = read_scope(live / 'persona-history-v1')
    account, stack, profile_sha = scope
    if stack != 'argus-ueba-actors' or profile_sha != PROFILE_SHA:
        raise ValueError('Unrecognized existing lab scope')
    import boto3
    session = boto3.Session(profile_name='argus-collector', region_name='us-east-1')
    identity = session.client('sts').get_caller_identity()
    if identity['Account'] != account or identity['Arn'].endswith(':root'):
        raise ValueError('Restricted collector required')
    queue = session.client('sqs').get_queue_url(QueueName='argus-ueba-live-events', QueueOwnerAWSAccountId=account)['QueueUrl']
    cf, cf_status = None, 'scope_not_confirmed'
    try:
        from scripts.setup_cloudflare import Cloudflare, load_token
        credentials = list((Path(os.environ['LOCALAPPDATA']) / 'Argus/credentials').glob('cloudflare-*.dpapi'))
        if len(credentials) == 1:
            cf_account = credentials[0].stem.removeprefix('cloudflare-')
            apps = Cloudflare(cf_account, load_token(cf_account)).call('GET', 'access/apps?per_page=100&page=1')
            selected = [app for app in apps if app.get('domain') == 'argus-access-demo.argus-lab-e98718.workers.dev']
            if len(selected) == 1:
                cf = {'account': cf_account, 'app_id': selected[0]['id']}
                cf_status = 'configured_existing_app'
    except Exception:
        cf_status = 'existing_scope_or_credential_unavailable'
    cfg = {'schema': 'argus_local_pilot_v2', 'source_root': str(ROOT), 'python': str(Path(sys.executable).with_name('python.exe')),
           'pythonw': str(Path(sys.executable).with_name('pythonw.exe')), 'gh': shutil.which('gh'),
           'state_dir': str(state), 'connected_dir': str(live / 'connected'), 'ledger_dir': str(live / 'persona-history-v1'),
           'account_id': account, 'stack': stack, 'queue_url': queue, 'api': API,
           'repo': 'Zhe-cyber/argus-ueba', 'cloudflare': cf, 'cloudflare_setup_status': cf_status,
           'actor_start': '2026-10-29', 'actor_end': '2026-11-13', 'end_local': '2026-11-14', 'runtime_id': uuid4().hex,
           'source_hashes': pinned_sources()}
    validate(cfg)
    state.mkdir(parents=True, exist_ok=False)
    backups = state / 'initial-backups'
    backups.mkdir()
    for src, name in [(live / 'connected/events.db', 'events.db'), (live / 'persona-history-v1/ledger.db', 'ledger.db')]:
        with sqlite3.connect(src.as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(backups / name) as destination:
            source.backup(destination)
    atomic_json(config_path, cfg)
    return {'configured': True, 'cloudflare': cf_status, 'model_activated': False, 'actor_start': cfg['actor_start']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['init', 'check', 'tick', 'serve', 'status'])
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--live-dir', type=Path)
    args = parser.parse_args()
    try:
        if os.name != 'nt':
            raise ValueError('The local pilot runtime requires Windows')
        if args.mode == 'init':
            if args.live_dir is None:
                raise ValueError('Existing live directory required')
            result = initialize(args.live_dir, args.config)
        else:
            cfg = validate(json.loads(args.config.read_text()))
            state = Path(cfg['state_dir'])
            if args.mode == 'serve':
                with lock(state / 'backend.lock'):
                    serve(cfg)
                return 0
            if args.mode == 'tick':
                with lock(state / 'tick.lock'):
                    result = tick(cfg)
                    atomic_json(state / 'last_tick.json', result)
                    log = state / (result['date_local'] + '-ticks.jsonl')
                    with log.open('a', encoding='utf-8') as handle:
                        handle.write(json.dumps(result, allow_nan=False) + '\n')
            elif args.mode == 'status':
                result = json.loads((state / 'last_tick.json').read_text()) if (state / 'last_tick.json').exists() else {'status': 'no_tick_yet'}
                failure = state / 'tick_failure.json'
                if failure.exists():
                    failed = json.loads(failure.read_text())
                    if failed['at_utc'] > result.get('at_utc', ''):
                        result = failed
                result['backend_ready'] = health(cfg)
            else:
                result = {'configuration_valid': True, 'model_activated': False}
        if sys.stdout is not None:
            print(json.dumps(result))
        return 0 if result.get('ok', True) else 1
    except Exception as error:
        # No raw provider errors, subprocess stderr, paths or credentials in status.
        result = {'status': 'stopped', 'error_type': type(error).__name__, 'model_activated': False,
                  'at_utc': now_utc().isoformat()}
        if args.config.parent.is_dir() and args.mode in ('tick', 'serve'):
            atomic_json(args.config.parent / (args.mode + '_failure.json'), result)
        if sys.stdout is not None:
            print(json.dumps(result))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
