"""Final read-only evaluation of frozen case/control days, never training."""
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone, timedelta
import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import reserved_study as study, live_history_readiness as readiness
from scripts import aws_lab_daily_features as features
from scripts.simulation_lab import buckets


def zoned(value):
    if not isinstance(value, str):
        raise ValueError('Zoned receipt time required')
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('Zoned receipt time required')
    return stamp


def audit_days(ledger, database, account, stack, now):
    """Same plan/coverage gates, independently verifies each native receipt."""
    if now < study.EVALUATE_FROM:
        raise ValueError('Final evaluation cutoff not reached')
    plans = {day: study.plan_for_date(account, stack, day) for day in study.CASES}
    expected = {r['action_id']: (day, r) for day, plan in plans.items() for r in plan['actions']}
    with closing(sqlite3.connect(Path(ledger).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        scope = db.execute('SELECT contract FROM scope WHERE id=1').fetchone()
        if scope is None or json.loads(scope['contract']) != [account, stack, study.PROFILE_SHA]:
            raise ValueError('Wrong reserved ledger scope')
        actual = [dict(r) for r in db.execute('SELECT * FROM actions WHERE day IN (?,?) LIMIT 1001', tuple(study.CASES))]
    if len(actual) > 1000 or len({r['action_id'] for r in actual}) != len(actual):
        raise ValueError('Ledger bound/uniqueness failed')
    if set(r['action_id'] for r in actual) - set(expected):
        raise ValueError('Unexpected action on reserved dates')
    by_id = {r['action_id']: r for r in actual}
    native_ids = Counter(r['native_event_id'] for r in actual if r.get('native_event_id'))
    grouped = {}
    resources = dict(zip(buckets(account, stack), features.CONTRACT['resource_domain']))
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        for action_id, (day, plan) in expected.items():
            key = day, plan['persona']
            group = grouped.setdefault(key, {'coverage': {'planned': 0, 'verified': 0, 'missing': 0,
                                                         'missed': 0, 'unresolved': 0},
                                             'events': [], 'late_receipts': 0, 'substitution_verified': False})
            cv = group['coverage']
            cv['planned'] += 1
            row = by_id.get(action_id)
            if row is None:
                cv['missing'] += 1
                continue
            if row['persona'] != key[1] or json.loads(row['plan']) != plan:
                raise ValueError('Stored reserved action differs from frozen plan')
            if row['status'] == 'missed' and not row.get('request_id') and not row.get('native_event_id'):
                cv['missed'] += 1
                continue
            matched = False
            if row['status'] == 'provider_verified' and native_ids[row.get('native_event_id')] == 1:
                native = db.execute('''SELECT * FROM events WHERE source='aws_cloudtrail'
                    AND source_account_id=? AND event_id=?''', (account, row['native_event_id'])).fetchall()
                if len(native) == 1:
                    event = dict(native[0])
                    try:
                        ingested = zoned(event['ingested_at'])
                        when = zoned(event['timestamp'])
                        attempted, completed = zoned(row['attempted_at']), zoned(row['completed_at'])
                        if ingested > study.CUTOFF:
                            group['late_receipts'] += 1
                        else:
                            matched = (ingested >= when - timedelta(seconds=60) and ingested <= now
                                       and attempted <= completed <= now
                                       and zoned(plan['planned_utc']) <= attempted
                                       and attempted - zoned(plan['planned_utc']) <= timedelta(minutes=15)
                                       and attempted - timedelta(seconds=60) <= when <= completed + timedelta(seconds=60)
                                       and readiness.native_matches(db, row, {**plan, 'day': day}, account, stack, now))
                    except (ValueError, TypeError, KeyError):
                        matched = False
                    if matched:
                        group['events'].append({'persona': key[1], 'day': day, 'action': event['action'],
                                                'timestamp': event['timestamp'], 'resource': event['resource'],
                                                'ip_address': event['ip_address'], 'event_id': event['event_id']})
                        cv['verified'] += 1
                        if 'case_slot' in plan:
                            group['substitution_verified'] = True
            if not matched:
                cv['unresolved'] += 1
    result = []
    for (day, role), group in sorted(grouped.items()):
        cv = group['coverage']
        cv['verified_fraction_of_planned'] = cv['verified'] / cv['planned']
        target = role in study.TARGETS
        available = not target or next(slot['status'] == 'available' for slot in plans[day]['case_availability'] if slot['persona'] == role)
        eligible = (available and cv['verified'] * 10 >= cv['planned'] * 9 and cv['unresolved'] == 0
                    and (not target or group['substitution_verified']))
        context = study.CASES[day] if target else 'ordinary_profile_control'
        row = {'date_local': day, 'persona': role, 'analyst_context': context,
               'is_target_account_day': target, 'coverage': cv, 'late_receipts': group['late_receipts'],
               'substitution_verified': group['substitution_verified'] if target else None,
               'slot_available': available,
               'status': ('unavailable_no_planned_target_read' if not available else
                          'eligible_for_inference' if eligible else 'unscored_receipt_or_day_coverage')}
        if eligible:
            aggregated = features.extract(group['events'], resources)
            if aggregated['ip_observability']['missing_events'] or aggregated['ip_observability']['invalid_events']:
                row['status'] = 'unscored_ip_observability'
            else:
                row['observation'] = {'persona': role, 'date_local': day, **aggregated}
                row['evidence_sha256'] = study.digest(sorted(group['events'], key=lambda r: r['event_id']))
        result.append(row)
    return result


def evaluate(release, ledger, database, account, stack, now=None, *, allow_synthetic=False):
    now = now or datetime.now(timezone.utc)
    if now < study.EVALUATE_FROM:
        raise ValueError('Final evaluation only from 16 November 00:00 MY')
    from scripts import train_live_daily as trainer, live_daily_method as method
    release_sha = study.sha(release)
    frozen, model, scaler, references, calibration = study.validate_release(release, account, stack,
                                                                           allow_synthetic=allow_synthetic)
    rows = audit_days(ledger, database, account, stack, now)
    observations = [r['observation'] for r in rows if 'observation' in r]
    scored = trainer.score_rows(model, scaler, references, observations) if observations else []
    scores = {(r['date_local'], r['persona']): r for r in scored}
    for row in rows:
        row.pop('observation', None)
        score = scores.get((row['date_local'], row['persona']))
        if score is None:
            continue
        decisions = {}
        for name in method.COMPONENTS:
            gate = calibration['components'][name]['gate']
            decisions[name] = {'score': score[name], 'threshold': calibration['components'][name]['threshold'],
                               'gate': gate, 'flagged': score[name] > calibration['components'][name]['threshold']
                               if gate == 'normal_calibration_only' else None}
        row['decisions'] = decisions
        row['primary_flagged'] = decisions['personal']['flagged']
        row['combined_flagged'] = (decisions['personal']['flagged'] or decisions['ae']['flagged']
                                   if calibration['combined_gate'] == 'normal_calibration_only' else None)
        row['status'] = 'scored'
    summary = {}
    for context in (*study.CASES.values(), 'ordinary_profile_control'):
        own = [r for r in rows if r['analyst_context'] == context]
        usable = [r for r in own if r['status'] == 'scored']
        summary[context] = {'planned_account_days': len(own), 'scored': len(usable),
                            'unscored': len(own) - len(usable),
                            'unavailable_slots': sum(not r['slot_available'] for r in own),
                            'primary_flagged': sum(r['primary_flagged'] is True for r in usable),
                            'combined_flagged': sum(r['combined_flagged'] is True for r in usable),
                            'combined_unavailable': sum(r['combined_flagged'] is None for r in usable)}
    if study.sha(release) != release_sha or frozen['source_sha256'] != study.source_hashes():
        raise ValueError('Frozen release/source drift during evaluation')
    if {name: study.sha(Path(frozen['bundle']) / name) for name in study.BUNDLE_FILES} != frozen['bundle_sha256']:
        raise ValueError('Frozen bundle drift during evaluation')
    return {'schema': 'argus_reserved_case_report_v3', 'study': study.protocol.binding(), 'study_sha256': study.protocol.binding_sha256(), 'computed_at_utc': now.isoformat(),
            'run_kind': 'synthetic_contract_test' if allow_synthetic else 'controlled_aws_lab',
            'release_sha256': release_sha, 'receipt_cutoff_my': study.CUTOFF.isoformat(),
            'rows': rows, 'summary': summary, 'activated': False, 'live_release_approved': False,
            'limitations': ['Three available target slots on two dates; only persona-02 has a complete change/control pair.',
                            'Approved/unannounced labels do not enter detector inputs; novelty does not infer intent.',
                            'Other roles are ordinary-profile controls, not independent human test subjects.',
                            'Late receipts excluded by ingested_at; separate ledger/native snapshots may require reconciliation.',
                            'Scores and flags are descriptive outcomes, not population attack recall or false-positive rates.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', required=True)
    parser.add_argument('--ledger', required=True)
    parser.add_argument('--events', required=True)
    parser.add_argument('--account-id', required=True)
    parser.add_argument('--stack', default='argus-ueba-actors')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        if Path(args.out).exists():
            raise ValueError('Fresh report path required')
        report = evaluate(args.release, args.ledger, args.events, args.account_id, args.stack)
        with Path(args.out).open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
        print(json.dumps(report['summary']))
        return 0
    except Exception:
        print('Reserved evaluation refused; check cutoff, frozen release and native coverage. No raw errors displayed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
