"""Operational collection after the pilot: one bounded tick of the existing provider fetchers.

No study dates, persona actors or reserved logic. Each provider is independent: a failing provider
is recorded and the others still run. Writes ops-status.json (counts and error kind only; never
identifiers, raw records or error text).

  python scripts/ops_collect.py tick  --config data/live/ops/ops.json
  python scripts/ops_collect.py init  --config data/live/ops/ops.json --from <pilot connected/events.db>
  python scripts/ops_collect.py serve --config data/live/ops/ops.json      (ingest backend)
  python scripts/ops_collect.py check --config data/live/ops/ops.json
"""
from __future__ import annotations

import argparse
from argparse import Namespace
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import collect_live  # noqa: E402  read-only reuse of the pilot fetchers
from scripts.local_pilot import atomic_json, lock  # noqa: E402

MY = timezone(timedelta(hours=8))
STATUS_NAME = 'ops-status.json'
PERSONA_FIRST_DAY = '2026-11-16'
PAGE = 100  # GitHub and Cloudflare fetchers read one bounded page (last 24 h, at most 100 records)
PROVIDERS = ('aws', 'github', 'cloudflare')


def now_utc():
    return datetime.now(timezone.utc)


def _path(value):
    path = Path(value)
    return (path if path.is_absolute() else ROOT / path).resolve()


def guard_path(cfg, path):
    """Refuse any write location inside a protected (live pilot) checkout."""
    path = Path(path).resolve()
    for protected in cfg['protected_paths']:
        if path == protected or protected in path.parents:
            raise ValueError('Refusing to write inside a protected pilot checkout')
    return path


def load_config(path):
    cfg = json.loads(Path(path).read_text(encoding='utf-8-sig'))  # PowerShell 5.1 writes a BOM
    if cfg.get('schema') != 'argus_ops_v1':
        raise ValueError('Unsupported ops config schema')
    cfg['backend_url'] = collect_live.local_api(cfg['backend_url'])
    cfg['protected_paths'] = [Path(p).resolve() for p in cfg.get('protected_paths', [])]
    for key in ('live_state_dir', 'status_dir'):
        cfg[key] = guard_path(cfg, _path(cfg[key]))
    date.fromisoformat(cfg['collect_start_local'])
    personas = cfg.setdefault('personas', {'enabled': False})
    if personas.get('enabled') and personas.get('start_local', '') < PERSONA_FIRST_DAY:
        raise ValueError('Persona start must be on or after 2026-11-16 (the pilot actors own earlier dates)')
    if personas.get('ledger_dir'):
        personas['ledger_dir'] = guard_path(cfg, _path(personas['ledger_dir']))
    aws = cfg['providers'].get('aws', {})
    if aws.get('enabled') and (not re.fullmatch(r'[0-9]{12}', aws.get('account_id', ''))
                               or aws.get('batches', 5) not in range(1, 6)):
        raise ValueError('AWS provider needs a 12-digit account and 1-5 batches')
    cf = cfg['providers'].get('cloudflare', {})
    if cf.get('enabled') and (not re.fullmatch(r'[a-f0-9]{32}', cf.get('account_id', ''))
                              or not cf.get('app_ids')
                              or not all(re.fullmatch(r'[a-f0-9-]{36}', a) for a in cf['app_ids'])):
        raise ValueError('Cloudflare provider needs an account and application IDs')
    gh = cfg['providers'].get('github', {})
    if gh.get('enabled') and (not gh.get('repos')
                              or not all(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', r) for r in gh['repos'])):
        raise ValueError('GitHub provider needs owner/repository names')
    return cfg


def read_status(status_dir):
    path = Path(status_dir) / STATUS_NAME
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _summary(counts):
    keep = ('received', 'inserted', 'duplicates', 'retained', 'malformed', 'skipped', 'acknowledged')
    return {k: counts.get(k, 0) for k in keep}


def _merge(total, counts):
    """Sum counts; a fetch that returned a full page may have missed older records (bounded sample)."""
    for k, v in _summary(counts).items():
        total[k] = total.get(k, 0) + v
    total['possibly_truncated'] = total.get('possibly_truncated', False) or counts.get('received', 0) >= PAGE
    return total


def run_aws(cfg, backend):
    p = cfg['providers']['aws']
    args = Namespace(account_id=p['account_id'], queue_url=p['queue_url'],
                     profile=p.get('profile', 'argus-collector'), batches=p.get('batches', 5))
    return _summary(collect_live.collect_aws(args, backend))


def run_github(cfg, backend):
    p = cfg['providers']['github']
    if p.get('gh_path'):
        os.environ['PATH'] = str(Path(p['gh_path']).parent) + os.pathsep + os.environ.get('PATH', '')
    revisions = cfg['live_state_dir'] / 'github-event-revisions'
    total = {}
    for repo in p['repos']:
        _merge(total, collect_live.collect_github(Namespace(repo=repo, revision_dir=revisions), backend))
    return total


def run_cloudflare(cfg, backend):
    p = cfg['providers']['cloudflare']
    total = {}
    for app_id in p['app_ids']:
        _merge(total, collect_live.collect_cloudflare(Namespace(account_id=p['account_id'], app_id=app_id), backend))
    return total


RUNNERS = {'aws': run_aws, 'github': run_github, 'cloudflare': run_cloudflare}


def tick(cfg, now=None, runners=None, backend_factory=collect_live.LocalBackend):
    """One bounded pass. Returns and writes the status document."""
    now = now or now_utc()
    runners = runners or RUNNERS
    status_dir = cfg['status_dir']
    status_dir.mkdir(parents=True, exist_ok=True)
    previous = read_status(status_dir).get('providers', {})
    day = now.astimezone(MY).date().isoformat()
    doc = {'schema': 'argus_ops_status_v1', 'at_utc': now.isoformat(), 'date_local': day, 'providers': {}}
    if day < cfg['collect_start_local']:
        doc['status'] = 'not_started_pilot_owns_collection'
        for name in PROVIDERS:
            doc['providers'][name] = {**previous.get(name, {}), 'state': 'not_started'}
        atomic_json(status_dir / STATUS_NAME, doc)
        return doc
    backend, backend_error = None, None
    try:
        backend = backend_factory(cfg['backend_url'])
        backend.preflight()
    except Exception as error:  # Nothing is consumed from any provider without a ready backend.
        backend_error = type(error).__name__
    for name in PROVIDERS:
        spec = cfg['providers'].get(name, {})
        last = previous.get(name, {})
        entry = dict(last)
        if not spec.get('enabled'):
            doc['providers'][name] = {'state': 'disabled'}
            continue
        interval = timedelta(minutes=cfg.get('intervals_minutes', {}).get(name, 5))
        last_run = last.get('last_run_utc')
        if last_run and now - datetime.fromisoformat(last_run) < interval - timedelta(seconds=30):
            entry['state'] = 'not_due'
            doc['providers'][name] = entry
            continue
        entry = {'last_run_utc': now.isoformat(), 'state': 'ran'}
        if backend_error:
            entry.update(ok=False, error_kind='backend_unavailable', received=0, inserted=0)
        else:
            try:
                counts = runners[name](cfg, backend)
                entry.update(ok=counts.get('retained', 0) == 0, error_kind=None, **counts)
                if not entry['ok']:
                    entry['error_kind'] = 'records_retained_for_retry'
            except Exception as error:  # Provider isolation: record the kind only, never the message.
                entry.update(ok=False, error_kind=type(error).__name__, received=0, inserted=0)
        if entry['ok']:
            entry['last_ok_utc'] = now.isoformat()
        elif last.get('last_ok_utc'):
            entry['last_ok_utc'] = last['last_ok_utc']
        doc['providers'][name] = entry
    for entry in doc['providers'].values():
        if entry.get('last_ok_utc'):
            entry['minutes_since_last_ok'] = round((now - datetime.fromisoformat(entry['last_ok_utc'])).total_seconds() / 60, 1)
    try:  # persona outcome summary (written by ops_personas.py; read here so each file has one writer)
        personas = json.loads((status_dir / 'ops-personas-status.json').read_text(encoding='utf-8'))
        doc['personas'] = {k: personas[k] for k in ('at_utc', 'status', 'aws', 'cloudflare', 'github') if k in personas}
    except (OSError, ValueError):
        doc['personas'] = None
    ran = [p for p in doc['providers'].values() if p.get('state') == 'ran']
    doc['status'] = 'completed' if all(p['ok'] for p in ran) else 'partial_failure'
    atomic_json(status_dir / STATUS_NAME, doc)
    return doc


def machine_app_collected(cfg):
    """Is the Cloudflare machine-lab app among the collected app ids? None when personas' Cloudflare is not configured."""
    state = cfg.get('personas', {}).get('cloudflare', {}).get('state_dir')
    if not state:
        return None
    try:
        app_id = json.loads((Path(state) / 'pilot-config.json').read_bytes())['app_id']
    except (OSError, ValueError, KeyError):
        return False
    cf = cfg['providers'].get('cloudflare', {})
    return bool(cf.get('enabled')) and app_id in cf.get('app_ids', [])


def init_store(cfg, source):
    """Consistent copy of an existing events.db (opened read-only) to start the operational store."""
    source = Path(source).resolve(strict=True)
    dest = guard_path(cfg, cfg['live_state_dir'] / 'events.db')
    if dest.exists():
        raise ValueError('Operational store already exists; refusing to overwrite')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(dest) as out:
        src.backup(out)
    with sqlite3.connect(dest) as out:
        rows = out.execute('SELECT count(*) FROM events').fetchone()[0]
    return {'status': 'initialized', 'events_copied': rows}


def serve(cfg):
    """Ingest backend on the configured loopback port, SQLite store in live_state_dir."""
    from urllib.parse import urlparse
    db = cfg['live_state_dir'] / 'events.db'
    if not db.is_file():
        raise ValueError('Run init first; refusing to start on an empty store')
    if sys.stdout is None or sys.stderr is None:  # pythonw: uvicorn needs real streams
        stream = (cfg['status_dir'] / 'backend-service.log').open('a', encoding='utf-8', buffering=1)
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream
    os.environ.update({'DATABASE_URL': 'sqlite-local', 'ARGUS_MODE': 'live', 'DEMO_MODE': 'false',
                       'CLOUD_MODEL_PROFILE': 'unverified', 'LIVE_STATE_DIR': str(cfg['live_state_dir']),
                       'ADMIN_TOKEN': '', 'ARGUS_ACCOUNT_KEYS': 'source-principal-v1'})
    from backend import event_store
    from backend.main import app
    if event_store._PG or Path(event_store.DB_PATH).resolve() != db:
        raise ValueError('Backend storage mismatch')
    import uvicorn
    port = urlparse(cfg['backend_url']).port
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning', access_log=False)


def _locked(path, fn, cfg):
    with lock(path):
        return fn(cfg)


def loop(once, interval, sleep=None):
    """Run once() every interval seconds; one failed pass never ends the loop (status files record it)."""
    import time
    sleep = sleep or time.sleep
    while True:
        try:
            once()
        except Exception:
            pass
        sleep(interval)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=['tick', 'loop', 'init', 'serve', 'check'])
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--from', dest='source', type=Path)
    args = parser.parse_args(argv)
    out = sys.stdout
    try:
        cfg = load_config(args.config)
        if args.mode == 'serve':
            serve(cfg)
            return 0
        if args.mode == 'loop':  # run by the supervisor: the single scheduler
            cfg['status_dir'].mkdir(parents=True, exist_ok=True)
            loop(lambda: _locked(cfg['status_dir'] / 'ops-collect.lock', tick, cfg),
                 cfg.get('supervisor', {}).get('collect_interval_seconds', 300))
        if args.mode == 'check':
            result = {'status': 'config_ok', 'collect_start_local': cfg['collect_start_local'],
                      'providers': {n: bool(cfg['providers'].get(n, {}).get('enabled')) for n in PROVIDERS},
                      'machine_lab_app_collected': machine_app_collected(cfg)}
        elif args.mode == 'init':
            if not args.source:
                raise ValueError('--from is required')
            result = init_store(cfg, args.source)
        else:
            cfg['status_dir'].mkdir(parents=True, exist_ok=True)
            with lock(cfg['status_dir'] / 'ops-collect.lock'):  # overlapping ticks fail fast
                result = tick(cfg)
        if out is not None:
            print(json.dumps(result))
        return 0 if result.get('status') != 'partial_failure' else 1
    except Exception as error:
        if out is not None:
            print(json.dumps({'status': 'stopped', 'error_kind': type(error).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
