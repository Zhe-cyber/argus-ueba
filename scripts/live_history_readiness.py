"""Read-only prospective V2 history gates, not scoring or model activation."""
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.persona_history_plan import make_plan, MALAYSIA
from scripts.simulation_lab import buckets, validate_scope

PROFILE_SHA = '150529b73fa71ac75eab06b162ad4bc913d7d0a19e3ff52c009d60ef3ba3899c'
WINDOWS = {'fit': ('2026-10-30', '2026-11-05'),
           'validation': ('2026-11-06', '2026-11-07'),
           'normal_calibration': ('2026-11-08', '2026-11-10')}


def expected_actions(account, stack):
    validate_scope(account, stack)
    raw = (ROOT / 'scripts/persona_profiles_v2.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROFILE_SHA:
        raise ValueError('Frozen daily profile differs')
    profiles = json.loads(raw)
    targets = dict(zip([f'p{i:02d}' for i in range(1, 7)] + ['confidential'], buckets(account, stack)))
    result = {}
    for partition, (start, end) in WINDOWS.items():
        current = date.fromisoformat(start)
        while current.isoformat() <= end:
            plan = make_plan(profiles, current)
            for row in plan['actions']:
                identity = f"{PROFILE_SHA}|{current.isoformat()}|{row['persona']}|{row['ordinal']}"
                action_id = hashlib.sha256(identity.encode()).hexdigest()
                result[action_id] = {**row, 'action_id': action_id, 'bucket': targets[row['symbolic_bucket']],
                                     'day': current.isoformat(), 'partition': partition}
            current += timedelta(days=1)
    return result


def read_ledger(path, account, stack):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        scope = db.execute('SELECT contract FROM scope WHERE id=1').fetchone()
        if scope is None or json.loads(scope[0]) != [account, stack, PROFILE_SHA]:
            raise ValueError('Wrong study scope/profile')
        rows = db.execute('''SELECT action_id,day,persona,plan,status,request_id,principal_id,native_event_id
            FROM actions WHERE day>=? AND day<=? ORDER BY day,action_id LIMIT 10001''',
            (WINDOWS['fit'][0], WINDOWS['normal_calibration'][1])).fetchall()
        db.rollback()
    if len(rows) > 10000:
        raise ValueError('Ledger bound exceeded')
    return [dict(row) for row in rows]


def native_matches(db, row, planned, account, stack, now):
    if not all(row.get(k) for k in ('request_id', 'principal_id', 'native_event_id')):
        return False
    matches = db.execute('''SELECT timestamp,action,resource,metadata FROM events
        WHERE source='aws_cloudtrail' AND source_account_id=? AND event_id=?''',
        (account, row['native_event_id'])).fetchall()
    if len(matches) != 1:
        return False
    event = dict(matches[0])
    stamp = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
    metadata = json.loads(event['metadata'])
    if not isinstance(metadata, dict) or not isinstance(metadata.get('userIdentity'), dict):
        return False
    return (stamp.tzinfo is not None and stamp <= now
            and stamp >= datetime.fromisoformat(planned['planned_utc'])
            and stamp.astimezone(MALAYSIA).date().isoformat() == planned['day']
            and event['action'] == planned['operation'] and event['resource'] == planned['bucket']
            and metadata.get('requestID') == row['request_id']
            and metadata['userIdentity'].get('principalId') == row['principal_id']
            and metadata['userIdentity'].get('type') == 'AssumedRole'
            and metadata['userIdentity'].get('arn') ==
                f"arn:aws:sts::{account}:assumed-role/{stack}-{planned['persona']}/argus-{planned['persona']}"
            and metadata.get('errorCode') is None)


def history_gates(days):
    roles = sorted({r['persona'] for r in days})
    eligibility = []
    for role in roles:
        usable = {part: sorted(r['day'] for r in days if r['persona'] == role
                               and r['partition'] == part and r['status'] == 'usable') for part in WINDOWS}
        fit = usable['fit']
        span = (date.fromisoformat(fit[-1]) - date.fromisoformat(fit[0])).days + 1 if fit else 0
        fit_ok = len(fit) >= 5 and span >= 7
        val_ok = len(usable['validation']) >= 2
        cal_ok = len(usable['normal_calibration']) >= 2
        eligibility.append({'persona': role, 'usable_dates': usable, 'fitting_span_calendar_days': span,
                            'fitting_history_pass': fit_ok, 'validation_history_pass': val_ok,
                            'calibration_history_pass': cal_ok, 'all_role_history_gates_pass': fit_ok and val_ok and cal_ok})
    eligible = {r['persona'] for r in eligibility if r['all_role_history_gates_pass']}
    calibration = [r for r in days if r['status'] == 'usable' and r['partition'] == 'normal_calibration'
                   and r['persona'] in eligible]
    pooled = len(calibration) >= 12 and len(eligible) >= 4 and len({r['day'] for r in calibration}) >= 3
    return {'roles': eligibility, 'eligible_roles': len(eligible), 'eligible_calibration_account_days': len(calibration),
            'pooled_calibration_history_pass': pooled, 'history_gates_pass': pooled}


def evaluate(ledger, database, account, stack, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    today = now.astimezone(MALAYSIA).date().isoformat()
    expected = expected_actions(account, stack)
    rows = read_ledger(ledger, account, stack)
    actual = {row['action_id']: row for row in rows}
    if len(actual) != len(rows) or set(actual) - set(expected):
        raise ValueError('Duplicate or unexpected study action')
    native_counts = Counter(row['native_event_id'] for row in rows if row['native_event_id'])
    by_day = {}
    fields = ('persona', 'ordinal', 'planned_utc', 'planned_local', 'operation', 'symbolic_bucket', 'bucket', 'key')
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        for action_id, planned in expected.items():
            key = planned['day'], planned['persona']
            day = by_day.setdefault(key, {'day': key[0], 'persona': key[1], 'partition': planned['partition'],
                'planned': 0, 'verified': 0, 'missing': 0, 'missed': 0, 'unresolved': 0})
            day['planned'] += 1
            row = actual.get(action_id)
            if row is None:
                day['missing'] += 1
                continue
            plan = json.loads(row['plan'])
            if row['day'] != key[0] or row['persona'] != key[1] or any(plan.get(f) != planned[f] for f in fields):
                raise ValueError('Stored action differs from the frozen plan')
            if row['status'] == 'missed' and not row['request_id'] and not row['native_event_id']:
                day['missed'] += 1
            elif (row['status'] == 'provider_verified' and native_counts[row['native_event_id']] == 1
                  and native_matches(db, row, planned, account, stack, now)):
                day['verified'] += 1
            else:
                day['unresolved'] += 1
        db.rollback()
    days = sorted(by_day.values(), key=lambda r: (r['day'], r['persona']))
    for row in days:
        row['verified_fraction_of_planned'] = row['verified'] / row['planned']
        row['status'] = ('future' if row['day'] > today else 'current_partial' if row['day'] == today
                         else 'usable' if row['verified'] * 10 >= row['planned'] * 9 and row['unresolved'] == 0 else 'incomplete')
    gates = history_gates(days)
    return {'schema': 'argus_live_history_readiness_v1', 'computed_at_utc': now.isoformat(),
            'timezone': 'Asia/Kuala_Lumpur', 'profile_sha256': PROFILE_SHA, 'days': days, **gates,
            'status': 'history_minimums_met' if gates['history_gates_pass'] else 'history_pending',
            'model_activated': False, 'model_release_evaluated': False,
            'limitations': ['History gates only; stricter model requirements still apply.',
                            'Separate read-only ledger/native snapshots; newly arriving receipts may need recheck.',
                            'Warm-up, setup and reserved cases excluded; no scores or attack results inspected.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot-config', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.out.exists():
            raise ValueError('Use a fresh versioned report path')
        cfg = json.loads(args.pilot_config.read_text())
        report = evaluate(Path(cfg['ledger_dir']) / 'ledger.db', Path(cfg['connected_dir']) / 'events.db',
                          cfg['account_id'], cfg['stack'])
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
        print(json.dumps({k: report[k] for k in ('status', 'eligible_roles', 'eligible_calibration_account_days', 'model_activated')}))
        return 0
    except Exception:
        print('Readiness audit refused; check frozen scope, plans and native receipts. No raw identities displayed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
