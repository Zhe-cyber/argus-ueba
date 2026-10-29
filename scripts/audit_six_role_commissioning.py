"""Independent real receipt/feature diagnostic; no model training or event writes."""
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import local_pilot as pilot
from scripts.commission_six_roles import PURPOSE
from scripts.simulation_lab import PERSONAS, FIXTURE_KEY, buckets
from scripts.persona_history_plan import MALAYSIA
from scripts.aws_lab_daily_features import CONTRACT, extract


def audit(cfg):
    now = datetime.now(timezone.utc)
    account, stack = cfg['account_id'], cfg['stack']
    expected = {}
    for role, bucket in zip(PERSONAS, buckets(account, stack)):
        for op in ('GetObject', 'HeadObject', 'GetBucketLocation'):
            identity = f'{pilot.PROFILE_SHA}|commission-six-v1|{account}|{stack}|{role}|{op}'
            expected[hashlib.sha256(identity.encode()).hexdigest()] = (role, op, bucket)
    with closing(sqlite3.connect((Path(cfg['ledger_dir']) / 'ledger.db').as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        rows = {r['action_id']: dict(r) for r in db.execute('SELECT * FROM actions WHERE action_id IN ('
                            + ','.join('?' for _ in expected) + ')', tuple(expected))}
        reserved = db.execute('SELECT coalesce(sum(reserved_calls),0) FROM runs').fetchone()[0]
        ordinary = Counter()
        for row in db.execute("SELECT plan,status FROM actions WHERE day='2026-10-29'"):
            if json.loads(row['plan']).get('purpose') != PURPOSE:
                ordinary[row['status']] += 1
        db.rollback()
    evidence, statuses = [], Counter()
    with closing(sqlite3.connect((Path(cfg['connected_dir']) / 'events.db').as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        for action_id, (role, op, bucket) in expected.items():
            row = rows.get(action_id)
            if row is None:
                statuses['missing_claim'] += 1
                continue
            statuses[row['status']] += 1
            plan = json.loads(row['plan'])
            if (plan.get('purpose') != PURPOSE or plan.get('operation') != op or plan.get('bucket') != bucket
                    or plan.get('persona') != role or plan.get('key') != FIXTURE_KEY or row['day'] != '2026-10-29'):
                raise ValueError('Unexpected commissioning claim')
            if not row['request_id'] or not row['principal_id']: continue
            matches = []
            for event in db.execute('''SELECT timestamp,action,resource,ip_address,event_id,metadata FROM events
                WHERE source='aws_cloudtrail' AND source_account_id=?
                AND json_extract(metadata,'$.requestID')=?''', (account, row['request_id'])):
                event = dict(event)
                meta = json.loads(event['metadata'])
                who = meta.get('userIdentity', {})
                stamp = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
                # API client and provider clocks are independent. Exact receipt
                # identifiers establish correspondence; this is a sanity bound,
                # not a rewrite of native times or a detection threshold.
                earliest = datetime.fromisoformat(row['attempted_at']) - timedelta(seconds=60)
                latest = datetime.fromisoformat(row['completed_at']) + timedelta(seconds=60)
                if (who.get('type') == 'AssumedRole' and who.get('principalId') == row['principal_id']
                        and who.get('arn') == f'arn:aws:sts::{account}:assumed-role/{stack}-{role}/argus-{role}'
                        and not meta.get('errorCode') and event['action'] == op and event['resource'] == bucket
                        and stamp.tzinfo is not None and earliest <= stamp <= min(now, latest)
                        and stamp.astimezone(MALAYSIA).date().isoformat() == '2026-10-29'):
                    matches.append(event)
            if len(matches) == 1:
                evidence.append({**matches[0], 'persona': role, 'day': '2026-10-29', 'action_id': action_id})
        db.rollback()
    unique = len({e['event_id'] for e in evidence}) == len(evidence)
    grouped = defaultdict(list)
    for event in evidence: grouped[event['persona']].append(event)
    mapping = dict(zip(buckets(account, stack), CONTRACT['resource_domain']))
    projected = [{'persona': role, 'native_receipts': len(events), **extract(events, mapping)} for role, events in sorted(grouped.items())]
    complete = len(evidence) == 18 and statuses['provider_verified'] == 18 and unique
    return {'schema': 'argus_six_role_commissioning_audit_v1', 'purpose': PURPOSE,
            'status': 'complete' if complete else 'pending', 'expected_operations': 18,
            'independently_matched_native_receipts': len(evidence), 'unique_native_ids': unique,
            'ledger_states': dict(statuses), 'role_diagnostics': projected,
            'ordinary_action_states_preserved': dict(ordinary), 'shared_reserved_calls': reserved,
            'evidence_sha256': hashlib.sha256(json.dumps(sorted(evidence, key=lambda e: e['action_id']), sort_keys=True).encode()).hexdigest(),
            'checked_at_utc': now.isoformat(), 'test_source_sha256': hashlib.sha256((ROOT / 'scripts/commission_six_roles.py').read_bytes()).hexdigest(),
            'cross_clock_sanity_tolerance_seconds': 60,
            'trained': False, 'activated': False,
            'limitations': ['Engineering commissioning only, not normal training history or detection evaluation.',
                            'Tests own toy buckets and allowed operation types, not every future resource combination.',
                            'CloudTrail arrival latency may differ across management/data events.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot-config', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    cfg = pilot.validate(json.loads(args.pilot_config.read_text()))
    report = audit(cfg)
    with args.out.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print(json.dumps({k: report[k] for k in ('status', 'expected_operations', 'independently_matched_native_receipts', 'ledger_states')}))
