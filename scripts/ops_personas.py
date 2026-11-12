"""Ordinary persona workloads after the pilot, on the operational store. Owner-run via the ops task.

AWS: the pilot's own plan generator (persona_history_plan.make_plan, profiles v2) and execution
mechanics (run_persona_history.plan_today / execute / audit), imported unchanged, against a NEW
ledger that this script creates and marks. Same caps (48/run, 128/day, 1792/ledger), same 15-minute
grace, same claim-before-I/O and no-retry rule. Any unknown claim blocks further AWS actions.

Cloudflare: one service-token request per persona per day in the machine pilot's windows
(cloudflare_machine_pilot.WINDOWS), credentials through the existing DPAPI loader
(github_lab_app.load_secret), own ledger, caps 6/day and 90/ledger, no retry; any error blocks.
The machine pilot's own plan() is date-limited to its study window, so the schedule is re-derived
here with the same formula under a new id namespace.

GitHub: collection only. The machine pilot's write function (github_machine_pilot.perform) checks
the item against its date-limited plan and writes to the pilot's ledger, so it cannot be reused.

  python scripts/ops_personas.py tick --config data/live/ops/ops.json
  python scripts/ops_personas.py plan --config data/live/ops/ops.json --date 2026-11-16
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import date, datetime, time as daytime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import ops_collect  # noqa: E402
from scripts import run_persona_history as history  # noqa: E402  read-only reuse
from scripts.persona_history_plan import make_plan, MALAYSIA  # noqa: E402
from scripts.local_pilot import atomic_json, lock  # noqa: E402

STATUS_NAME = 'ops-personas-status.json'
MARKER = 'ops-ledger.json'
CF_DAY_CAP, CF_LEDGER_CAP, CF_WINDOW = 6, 90, timedelta(minutes=45)
AWS_FRESH = timedelta(minutes=15)


def guard_ledger(cfg):
    """A ledger directory this script created, never the pilot's (or any unmarked) ledger."""
    ledger_dir = ops_collect.guard_path(cfg, cfg['personas']['ledger_dir'])
    if ledger_dir.name == 'persona-history-v1':
        raise ValueError("Refusing the pilot's ledger directory")
    marker = ledger_dir / MARKER
    existing = [p for p in ('ledger.db', 'cloudflare-ledger.db') if (ledger_dir / p).exists()]
    if not marker.is_file():
        if existing:
            raise ValueError('Existing ledger was not created by ops_personas; refusing to write')
        ledger_dir.mkdir(parents=True, exist_ok=True)
        with marker.open('x', encoding='utf-8') as out:
            json.dump({'schema': 'argus_ops_persona_ledger_v1', 'created_utc': datetime.now(timezone.utc).isoformat()}, out)
    elif json.loads(marker.read_text(encoding='utf-8')).get('schema') != 'argus_ops_persona_ledger_v1':
        raise ValueError('Invalid ops ledger marker')
    return ledger_dir


def plan_for(day):
    """Offline AWS plan for any date with the shipped v2 profiles (no I/O)."""
    return make_plan(json.loads(history.PROFILE.read_bytes()), day)


def aws_collection_ready(cfg, now):
    if now.astimezone(MALAYSIA).date().isoformat() < cfg['collect_start_local']:
        return True  # the pilot collector still owns the queue
    aws = ops_collect.read_status(cfg['status_dir']).get('providers', {}).get('aws', {})
    last_ok = aws.get('last_ok_utc')
    return bool(aws.get('ok') and last_ok and now - datetime.fromisoformat(last_ok) <= AWS_FRESH)


def unknown_claims(ledger_dir, name='ledger.db', states=("'claimed_unknown'",)):
    path = ledger_dir / name
    if not path.exists():
        return 0
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        return db.execute(f"SELECT count(*) FROM actions WHERE status IN ({','.join(states)})").fetchone()[0]


def run_aws(cfg, ledger_dir, now):
    account = cfg['providers']['aws']['account_id']
    if not re.fullmatch(r'[0-9]{12}', account):
        return {'ok': False, 'state': 'not_configured'}
    if unknown_claims(ledger_dir):
        return {'ok': False, 'state': 'blocked_unknown_claims_review_required'}
    if not aws_collection_ready(cfg, now):
        return {'ok': False, 'state': 'blocked_collection_not_ok'}
    p = cfg['personas']
    plan = history.plan_today(account, p.get('stack', 'argus-ueba-actors'))
    result = history.execute(plan, ledger_dir, profile=p.get('aws_profile', 'argus-simulator'))
    out = {'ok': True, 'state': result['status'], 'new_actions': result['new_actions'],
           'action_states': result['action_states'], 'reserved_sdk_calls_today': result['reserved_sdk_calls_today']}
    events = cfg['live_state_dir'] / 'events.db'
    if events.is_file():
        audit = history.audit(ledger_dir, events)
        out.update(newly_provider_verified=audit['newly_provider_verified'], pending_or_ambiguous=audit['pending_or_ambiguous'])
    return out


# ---- Cloudflare service-token personas -----------------------------------------------------------

def cf_plan(day):
    from scripts import cloudflare_machine_pilot as cfm
    result = []
    for n, (lo, hi) in cfm.WINDOWS.items():
        actor = f'persona-{n:02d}'
        seed = int(cfm.digest([20261030, day, actor]), 16)
        due = datetime.combine(date.fromisoformat(day), daytime(lo), cfm.MY) + timedelta(minutes=seed % ((hi - lo) * 60 - 45))
        result.append({'id': cfm.digest(['cf-ops-v1', day, actor]), 'day': day, 'persona': actor, 'due': due})
    return result


def cf_loader(state_dir, persona):
    """(host, client_id, client_secret) through the existing DPAPI loader. Never printed or logged."""
    from scripts.github_lab_app import load_secret
    state = Path(state_dir)
    pilot = json.loads((state / 'pilot-config.json').read_bytes())
    token = load_secret(state / f'{persona}.dpapi')
    if token['client_id'] != pilot['tokens'][persona]['client_id'] or token['id'] != pilot['tokens'][persona]['id']:
        raise ValueError('Credential scope differs')
    if not re.fullmatch(r'argus-machine-lab\.[a-z0-9-]+\.workers\.dev', pilot.get('host', '')):
        raise ValueError('Unexpected workload host')
    return pilot['host'], token['client_id'], token['client_secret']


def cf_http(url, headers):
    import requests
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(url, headers=headers, timeout=25, allow_redirects=False)
    ok = response.status_code == 200 and 'Argus machine workload: authenticated' in response.text
    return response.status_code, response.headers.get('CF-Ray', '').split('-')[0].lower(), ok


def cf_ledger(ledger_dir):
    db = sqlite3.connect(ledger_dir / 'cloudflare-ledger.db', timeout=10)
    db.execute('''CREATE TABLE IF NOT EXISTS actions(action_id TEXT PRIMARY KEY, day TEXT, persona TEXT,
                  status TEXT, claimed_at TEXT, ray_id TEXT, http_status INTEGER, verified_at TEXT)''')
    return closing(db)


def blockers(ledger_dir, reviewed_through=None):
    """Unknown, error or rejected-token rows block further requests until the owner reviews them
    and sets personas.cloudflare.reviewed_through_utc past their claim time."""
    path = ledger_dir / 'cloudflare-ledger.db'
    if not path.exists():
        return {}
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        return dict(db.execute("""SELECT status, count(*) FROM actions
            WHERE status IN ('claimed_unknown','response_error_log_pending','token_rejected') AND claimed_at > ?
            GROUP BY status""", (datetime.fromisoformat(reviewed_through).astimezone(timezone.utc).isoformat()
                                 if reviewed_through else '',)).fetchall())


def run_cloudflare(cfg, ledger_dir, now, loader=cf_loader, http=cf_http):
    c = cfg['personas'].get('cloudflare', {})
    if not c.get('enabled'):
        return {'ok': True, 'state': 'disabled'}
    # Provider-side token expiry as recorded by the owner after renewal (the old local EXPIRY/END dates do not apply).
    valid = c.get('tokens_valid_until_utc')
    if not valid or now >= datetime.fromisoformat(valid):
        return {'ok': False, 'state': 'tokens_expired_owner_must_renew'}
    if ops_collect.machine_app_collected(cfg) is not True:
        return {'ok': False, 'state': 'blocked_machine_app_not_collected'}  # requests could never be confirmed
    blocking = blockers(ledger_dir, c.get('reviewed_through_utc'))
    if blocking:
        return {'ok': False, 'state': 'token_expired_or_invalid' if 'token_rejected' in blocking
                else 'blocked_unknown_or_error_review_required', 'blocking': blocking}
    day = now.astimezone(MALAYSIA).date().isoformat()
    new = 0
    with cf_ledger(ledger_dir) as db:
        for item in cf_plan(day):
            if now < item['due'] or db.execute('SELECT 1 FROM actions WHERE action_id=?', (item['id'],)).fetchone():
                continue
            missed = now >= item['due'] + CF_WINDOW
            if not missed:
                if db.execute("SELECT count(*) FROM actions WHERE status!='missed'").fetchone()[0] >= CF_LEDGER_CAP:
                    raise ValueError('Cloudflare ledger cap')
                if db.execute("SELECT count(*) FROM actions WHERE day=? AND status!='missed'", (day,)).fetchone()[0] >= CF_DAY_CAP:
                    raise ValueError('Cloudflare daily cap')
            with db:  # durable claim before any provider I/O
                db.execute('INSERT INTO actions(action_id,day,persona,status,claimed_at) VALUES(?,?,?,?,?)',
                           (item['id'], day, item['persona'], 'missed' if missed else 'claimed_unknown', now.isoformat()))
            if missed:
                continue
            host, client_id, secret = loader(c['state_dir'], item['persona'])
            status, ray, ok = http(f"https://{host}/workloads/{item['persona']}/{item['id'][:24]}",
                                   {'CF-Access-Client-Id': client_id, 'CF-Access-Client-Secret': secret})
            if status in (401, 403):  # token expired or invalid: stop all Cloudflare persona actions
                with db:
                    db.execute("UPDATE actions SET status='token_rejected',http_status=? WHERE action_id=?", (status, item['id']))
                new += 1
                break
            if not re.fullmatch('[0-9a-f]{16}', ray or ''):
                raise ValueError('Native ray ID missing; claim stays unknown, no retry')
            with db:
                db.execute('UPDATE actions SET status=?,ray_id=?,http_status=? WHERE action_id=?',
                           ('api_ok_log_pending' if ok else 'response_error_log_pending', ray, status, item['id']))
            new += 1
            if not ok:
                break  # stop for review; never retried
        events = cfg['live_state_dir'] / 'events.db'
        verified = 0
        if events.is_file():
            with closing(sqlite3.connect(events.as_uri() + '?mode=ro', uri=True)) as native:
                for (action_id, ray) in db.execute("SELECT action_id, ray_id FROM actions WHERE status='api_ok_log_pending'").fetchall():
                    if native.execute("SELECT 1 FROM events WHERE source='cloudflare_access' AND event_id=?", (ray,)).fetchone():
                        with db:
                            db.execute("UPDATE actions SET status='provider_verified',verified_at=? WHERE action_id=?",
                                       (now.isoformat(), action_id))
                        verified += 1
        states = dict(db.execute('SELECT status,count(*) FROM actions GROUP BY status').fetchall())
    blocking = blockers(ledger_dir, c.get('reviewed_through_utc'))
    if 'token_rejected' in blocking:
        return {'ok': False, 'state': 'token_expired_or_invalid', 'new_actions': new, 'action_states': states}
    return {'ok': 'response_error_log_pending' not in blocking, 'state': 'ran', 'new_actions': new,
            'newly_provider_verified': verified, 'action_states': states}


def tick(cfg, now=None, cf_loader_fn=cf_loader, cf_http_fn=cf_http):
    now = now or history.utc_now()
    day = now.astimezone(MALAYSIA).date().isoformat()
    doc = {'schema': 'argus_ops_personas_status_v1', 'at_utc': now.isoformat(), 'date_local': day,
           'github': 'collection_only_no_persona_pushes'}
    p = cfg.get('personas', {})
    if not p.get('enabled'):
        doc['status'] = 'disabled'
    elif day < p['start_local']:
        doc['status'] = 'not_started'
    else:
        ledger_dir = guard_ledger(cfg)
        doc['aws'] = _isolated(run_aws, cfg, ledger_dir, now)
        doc['cloudflare'] = _isolated(run_cloudflare, cfg, ledger_dir, now, cf_loader_fn, cf_http_fn)
        doc['status'] = 'completed' if doc['aws']['ok'] and doc['cloudflare']['ok'] else 'attention_required'
    cfg['status_dir'].mkdir(parents=True, exist_ok=True)
    atomic_json(cfg['status_dir'] / STATUS_NAME, doc)
    return doc


def _isolated(fn, *args):
    try:
        return fn(*args)
    except Exception as error:  # kind only; messages could carry identifiers
        return {'ok': False, 'state': 'stopped', 'error_kind': type(error).__name__}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=['tick', 'loop', 'plan'])
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--date', type=date.fromisoformat)
    args = parser.parse_args(argv)
    out = sys.stdout
    try:
        cfg = ops_collect.load_config(args.config)
        if args.mode == 'loop':  # supervisor: independent of fetches, so personas never wait on a slow fetch
            cfg['status_dir'].mkdir(parents=True, exist_ok=True)
            ops_collect.loop(lambda: ops_collect._locked(cfg['status_dir'] / 'ops-personas.lock', tick, cfg),
                             cfg.get('supervisor', {}).get('persona_interval_seconds', 60))
        if args.mode == 'plan':
            day = args.date or datetime.now(MALAYSIA).date()
            plan = plan_for(day)
            result = {'date_local': day.isoformat(), 'aws_planned_actions': plan['planned_actions'],
                      'aws_idle_personas': len(plan['planned_idle']), 'cloudflare_planned': len(cf_plan(day.isoformat())),
                      'executed': False}
        else:
            cfg['status_dir'].mkdir(parents=True, exist_ok=True)
            with lock(cfg['status_dir'] / 'ops-personas.lock'):
                result = tick(cfg)
        if out is not None:
            print(json.dumps(result))
        return 0 if result.get('status') != 'attention_required' else 1
    except Exception as error:
        if out is not None:
            print(json.dumps({'status': 'stopped', 'error_kind': type(error).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
