"""Bounded due-only AWS lab history runner. Default is offline; no backfilling.

The durable ledger claims before I/O: uncertain attempts are never auto-retried.
Native receipt correlation is required before claiming collected coverage.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, closing
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.persona_history_plan import make_plan, MALAYSIA
from scripts.run_simulation import audit_coverage, METHODS
from scripts.simulation_lab import FIXTURE, FIXTURE_KEY, PERSONAS, REGION, buckets, role_arn, validate_scope

PROFILE = Path(__file__).with_name('persona_profiles_v1.json')
MAX_RUN_CALLS, MAX_DAY_CALLS, MAX_PILOT_CALLS = 48, 128, 1792
GRACE = timedelta(minutes=15)


def utc_now():
    return datetime.now(timezone.utc)


def plan_today(account, stack):
    validate_scope(account, stack)
    raw = PROFILE.read_bytes()
    profiles = json.loads(raw)
    if (profiles.get('schema') != 'argus_offline_persona_draft_v1'
            or tuple(p['id'] for p in profiles['personas']) != PERSONAS
            or profiles['max_sdk_calls_per_run'] != MAX_RUN_CALLS
            or profiles['reserved_preflight_and_role_calls'] != 9
            or profiles['max_actions_per_persona_day'] != 5):
        raise ValueError('Unsupported profile contract')
    now = utc_now()
    plan = make_plan(profiles, now.astimezone(MALAYSIA).date())
    digest = hashlib.sha256(raw).hexdigest()
    targets = dict(zip([f'p{i:02d}' for i in range(1, 7)] + ['confidential'], buckets(account, stack)))
    actions = []
    for row in plan['actions']:
        if row['operation'] not in METHODS or row['key'] != FIXTURE_KEY:
            raise ValueError('Unexpected operation')
        identity = f"{digest}|{plan['date_local']}|{row['persona']}|{row['ordinal']}"
        actions.append({**row, 'action_id': hashlib.sha256(identity.encode()).hexdigest(),
                        'bucket': targets[row['symbolic_bucket']]})
    return {**plan, 'profile_sha256': digest, 'account_id': account, 'stack': stack,
            'actions': actions, 'created_at_utc': now.isoformat(), 'purpose': 'controlled_lab_history'}


def commissioning_plan(account, stack, created_at=None):
    """One fixed probe, explicitly excluded from baseline; at most once per ledger."""
    plan = plan_today(account, stack)
    instant = created_at if created_at is not None else utc_now()
    now = utc_now()
    if instant.tzinfo is None or not timedelta(0) <= now - instant <= GRACE:
        raise ValueError('Commissioning request is stale or in the future')
    if instant.astimezone(MALAYSIA).date().isoformat() != plan['date_local']:
        raise ValueError('Commission only on the current local date')
    identity = f"{plan['profile_sha256']}|commissioning-v1|{account}|{stack}"
    action = {'persona': PERSONAS[0], 'ordinal': 0, 'planned_local': instant.astimezone(MALAYSIA).isoformat(),
              'planned_utc': instant.astimezone(timezone.utc).isoformat(), 'operation': 'GetObject',
              'symbolic_bucket': 'p01', 'bucket': buckets(account, stack)[0], 'key': FIXTURE_KEY,
              'status': 'planned_not_executed', 'purpose': 'commissioning_exclude_from_baseline',
              'action_id': hashlib.sha256(identity.encode()).hexdigest()}
    return {**plan, 'purpose': 'commissioning_exclude_from_baseline', 'created_at_utc': instant.isoformat(),
            'actions': [action], 'planned_actions': 1, 'planned_idle': []}


@contextmanager
def ledger(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=15)) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS scope (id INTEGER PRIMARY KEY CHECK(id=1), contract TEXT NOT NULL)')
        db.execute('''CREATE TABLE IF NOT EXISTS actions (
            action_id TEXT PRIMARY KEY, day TEXT NOT NULL, persona TEXT NOT NULL,
            plan TEXT NOT NULL, status TEXT NOT NULL, attempted_at TEXT,
            request_id TEXT, principal_id TEXT, completed_at TEXT,
            native_event_id TEXT, observed_at TEXT)''')
        db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, day TEXT NOT NULL, reserved_calls INTEGER NOT NULL)')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_native_event ON actions(native_event_id) WHERE native_event_id IS NOT NULL')
        db.commit()
        yield db


def claim(db, plan):
    now = utc_now()
    if plan['date_local'] != now.astimezone(MALAYSIA).date().isoformat():
        raise ValueError('Never execute another local date')
    contract = json.dumps([plan['account_id'], plan['stack'], plan['profile_sha256']], separators=(',', ':'))
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('INSERT OR IGNORE INTO scope VALUES(1,?)', (contract,))
        if db.execute('SELECT contract FROM scope WHERE id=1').fetchone()[0] != contract:
            raise ValueError('Ledger scope/profile changed; explicit review required')
        due = []
        for row in plan['actions']:
            planned = datetime.fromisoformat(row['planned_utc'])
            if planned > now:
                continue
            status = 'missed' if now - planned > GRACE else 'claimed_unknown'
            inserted = db.execute('INSERT OR IGNORE INTO actions(action_id,day,persona,plan,status) VALUES(?,?,?,?,?)',
                                  (row['action_id'], plan['date_local'], row['persona'], json.dumps(row), status)).rowcount
            if inserted and status != 'missed':
                due.append(row)
        roles = {r['persona'] for r in due}
        reserved = 3 + len(roles) + len(due) if due else 0
        daily = db.execute('SELECT coalesce(sum(reserved_calls),0) FROM runs WHERE day=?', (plan['date_local'],)).fetchone()[0]
        total = db.execute('SELECT coalesce(sum(reserved_calls),0) FROM runs').fetchone()[0]
        if reserved > MAX_RUN_CALLS or daily + reserved > MAX_DAY_CALLS or total + reserved > MAX_PILOT_CALLS:
            raise ValueError('Reserved SDK-call budget exhausted')
        if due:
            db.execute('INSERT INTO runs VALUES(?,?,?)', (uuid4().hex, plan['date_local'], reserved))
        db.commit()
        return due, reserved
    except Exception:
        db.rollback()
        raise


def status(db, day):
    counts = dict(db.execute('SELECT status,count(*) FROM actions WHERE day=? GROUP BY status', (day,)))
    return {'action_states': counts, 'coverage': 'provider_receipt_audit_pending',
            'reserved_sdk_calls_today': db.execute('SELECT coalesce(sum(reserved_calls),0) FROM runs WHERE day=?', (day,)).fetchone()[0]}


def execute(plan, state_dir, profile='argus-simulator', trail_name='argus-ueba-live-trail', commissioning=False):
    # Regenerate from shipped profile, never execute caller-supplied targets/actions.
    expected = (commissioning_plan(plan['account_id'], plan['stack'], datetime.fromisoformat(plan['created_at_utc']))
                if commissioning else plan_today(plan['account_id'], plan['stack']))
    if any(plan.get(k) != v for k, v in expected.items() if k != 'created_at_utc'):
        raise ValueError('Plan changed; no calls performed')
    if trail_name != 'argus-ueba-live-trail':
        raise ValueError('Only the existing audited trail is supported')
    with ledger(Path(state_dir) / 'ledger.db') as db:
        due, reserved = claim(db, expected)
        if not due:
            return {'status': 'no_due_actions', 'new_actions': 0, 'purpose': expected['purpose'], **status(db, plan['date_local'])}
        import boto3
        from botocore.config import Config
        config = Config(retries={'total_max_attempts': 1, 'mode': 'standard'},
                        s3={'addressing_style': 'virtual'}, connect_timeout=5, read_timeout=30)
        session = boto3.Session(profile_name=profile, region_name=REGION)
        used = 0
        http_attempts = 0

        def call(method, **kwargs):
            nonlocal used
            if used >= reserved:
                raise ValueError('SDK-call reservation exhausted')
            used += 1
            return method(**kwargs)

        # Count actual sends too: S3 region redirects can bypass ordinary retry
        # settings. An extra send consumes the reservation or stops before I/O.
        def before_send(**kwargs):
            nonlocal http_attempts
            if http_attempts >= reserved:
                raise ValueError('HTTP-attempt reservation exhausted')
            http_attempts += 1

        def client(service, **kwargs):
            result = session.client(service, config=config, **kwargs)
            result.meta.events.register('before-send.*.*', before_send)
            return result

        sts = client('sts')
        identity = call(sts.get_caller_identity)
        account, stack = plan['account_id'], plan['stack']
        if (identity.get('Account') != account
                or identity.get('Arn') != f'arn:aws:iam::{account}:user/argus-lab/{stack}-runner'):
            raise ValueError('Require exact non-root lab runner')
        trail = client('cloudtrail')
        if not call(trail.get_trail_status, Name=trail_name).get('IsLogging'):
            raise ValueError('Trail is not logging')
        if not audit_coverage(call(trail.get_event_selectors, TrailName=trail_name), buckets(account, stack)):
            raise ValueError('Exact toy-S3 audit coverage is required')
        for persona in sorted({r['persona'] for r in due}):
            assumed = call(sts.assume_role, RoleArn=role_arn(account, stack, persona),
                           RoleSessionName='argus-' + persona, DurationSeconds=900)
            principal = assumed['AssumedRoleUser']
            if principal['Arn'] != f'arn:aws:sts::{account}:assumed-role/{stack}-{persona}/argus-{persona}':
                raise ValueError('Unexpected lab role')
            cred = assumed['Credentials']
            s3 = client('s3', aws_access_key_id=cred['AccessKeyId'], aws_secret_access_key=cred['SecretAccessKey'],
                        aws_session_token=cred['SessionToken'])
            try:
                for row in [r for r in due if r['persona'] == persona]:
                    # A blocked/sleeping process must not execute a stale plan.
                    now = utc_now()
                    planned = datetime.fromisoformat(row['planned_utc'])
                    if not timedelta(0) <= now - planned <= GRACE or now.astimezone(MALAYSIA).date().isoformat() != plan['date_local']:
                        db.execute("UPDATE actions SET status='missed' WHERE action_id=?", (row['action_id'],))
                        db.commit()
                        continue
                    db.execute('UPDATE actions SET attempted_at=?,principal_id=? WHERE action_id=?',
                               (now.isoformat(), principal['AssumedRoleId'], row['action_id']))
                    db.commit()  # Durable before provider I/O. No automatic retry on unknown outcome.
                    kwargs = {'Bucket': row['bucket'], 'ExpectedBucketOwner': account}
                    if row['operation'] != 'GetBucketLocation':
                        kwargs['Key'] = FIXTURE_KEY
                    response = call(getattr(s3, METHODS[row['operation']]), **kwargs)
                    request = response.get('ResponseMetadata', {}).get('RequestId')
                    body = response.get('Body')
                    try:
                        if not request:
                            raise ValueError('Missing provider request ID')
                        if row['operation'] != 'GetBucketLocation':
                            if response.get('Metadata', {}).get('argus-lab') != stack or response.get('ContentLength', 4097) > 4096:
                                raise ValueError('Not the expected small synthetic fixture')
                            if body is not None and body.read(4097) != FIXTURE:
                                raise ValueError('Synthetic fixture mismatch')
                        db.execute("UPDATE actions SET status='api_ok_audit_pending',request_id=?,completed_at=? WHERE action_id=?",
                                   (request, utc_now().isoformat(), row['action_id']))
                        db.commit()
                    finally:
                        if body is not None:
                            body.close()
            finally:
                s3.close()
        return {'status': 'api_calls_completed_audit_pending', 'new_actions': len(due),
                'purpose': expected['purpose'], **status(db, plan['date_local'])}


def audit(state_dir, event_database):
    """Read-only provider evidence; only ledger audit fields are updated."""
    ledger_path = Path(state_dir) / 'ledger.db'
    event_database = Path(event_database).resolve()
    if not ledger_path.is_file() or not event_database.is_file():
        raise ValueError('Require existing ledger and native event store')
    verified, pending = 0, 0
    with ledger(ledger_path) as db, closing(sqlite3.connect(event_database.as_uri() + '?mode=ro', uri=True)) as native:
        scope = db.execute('SELECT contract FROM scope WHERE id=1').fetchone()
        if scope is None:
            raise ValueError('Missing pinned scope')
        account = json.loads(scope[0])[0]
        rows = db.execute("SELECT action_id,plan,request_id,principal_id FROM actions WHERE status='api_ok_audit_pending'").fetchall()
        for action_id, raw, request, principal in rows:
            row = json.loads(raw)
            matches = native.execute('''SELECT event_id,timestamp FROM events
                WHERE source='aws_cloudtrail' AND source_account_id=? AND event_id IS NOT NULL
                AND action=? AND resource=? AND json_extract(metadata,'$.requestID')=?
                AND json_extract(metadata,'$.userIdentity.principalId')=?
                AND json_extract(metadata,'$.errorCode') IS NULL''',
                (account, row['operation'], row['bucket'], request, principal)).fetchall()
            if len(matches) == 1:
                db.execute("UPDATE actions SET status='provider_verified',native_event_id=?,observed_at=? WHERE action_id=?",
                           (*matches[0], action_id))
                verified += 1
            else:
                pending += 1
        db.commit()
    return {'newly_provider_verified': verified, 'pending_or_ambiguous': pending,
            'coverage': 'matched_actions_only_not_complete_day', 'model_activated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-id', required=True)
    parser.add_argument('--stack', default='argus-ueba-actors')
    parser.add_argument('--profile', default='argus-simulator')
    parser.add_argument('--state-dir', type=Path, default=ROOT / 'data/live/persona-history-v1')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--commissioning-probe', action='store_true', help='One fixed fixture read, excluded from baseline, claimed once per ledger')
    parser.add_argument('--audit-events', type=Path, help='Audit existing receipts against a local native events.db; no cloud calls')
    args = parser.parse_args()
    try:
        if args.audit_events:
            if args.execute or args.commissioning_probe:
                raise ValueError('Audit and execution are separate operations')
            print(json.dumps(audit(args.state_dir, args.audit_events)))
            return 0
        plan = commissioning_plan(args.account_id, args.stack) if args.commissioning_probe else plan_today(args.account_id, args.stack)
        if not args.execute:
            print(json.dumps({'mode': 'offline_plan', 'date_local': plan['date_local'],
                              'planned_actions': len(plan['actions']), 'profile_sha256': plan['profile_sha256'],
                              'executed': False}))
        else:
            print(json.dumps(execute(plan, args.state_dir, args.profile, commissioning=args.commissioning_probe)))
        return 0
    except Exception:
        print('History runner stopped. Check ledger, scoped lab identity, audit coverage and budget. Unknown attempts require review; no provider details displayed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
