"""Live diagnostic receipt tests: synthetic live rows, injected coverage cells and random-weight models."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import sqlite3

import pytest

from scripts import audit_clue_v2_live as audit, clue_v2_features as v2, live_receipts_clue_v2 as receipts
from scripts import train_clue_v2 as trainer

_ids = iter(range(1, 10**9))
PERSONA, INFRA = 'acct_' + 'a' * 64, 'acct_' + 'b' * 64
AT = datetime(2026, 11, 10, 4, 0, tzinfo=timezone.utc)  # 10 Nov 12:00 MYT
REQUIRED = {'schema', 'label', 'live_activation', 'alert', 'risk_tier', 'key', 'cutoff_utc', 'source_timezone',
            'provenance', 'history', 'coverage', 'completeness', 'input', 'features', 'detectors', 'facts',
            'limitations', 'receipt_id'}


def aws(account, day, action='GetObject', bucket='toy-bucket-01', hour=3):
    return {'source': 'aws_cloudtrail', 'source_account_id': 'aws-acct', 'account_key': account,
            'event_id': f'evt-{next(_ids)}', 'payload_digest': hashlib.sha256(str(next(_ids)).encode()).hexdigest(),
            'timestamp': f'{day}T{hour:02d}:00:00Z', 'action': action, 'resource': bucket,
            'metadata': json.dumps({'eventSource': 's3.amazonaws.com'}), 'ingested_at': f'{day}T{hour:02d}:05:00+00:00'}


def dates(first, n):
    return [(date.fromisoformat(first) + timedelta(i)).isoformat() for i in range(n)]


def bundle():
    import torch
    torch.manual_seed(0)
    return {'C': (trainer.build_model(trainer.METHOD['detectors']['C']['architecture']).eval(),
                  trainer.Scaler([0.0] * 9, [1.0] * 9), v2.FEATURES),
            'B': (trainer.build_model(trainer.METHOD['detectors']['B']['architecture']).eval(),
                  trainer.Scaler([0.0] * 5, [1.0] * 5), v2.FEATURES[:5])}


def cell(day, status):
    return {'day': day, 'status': status, 'planned': 3, 'verified': 3 if status == 'usable' else 1,
            'missing': 0, 'missed': 0 if status == 'usable' else 2, 'unresolved': 0, 'not_yet_ingested': 0,
            'commissioning_actions': 0, 'case_actions': 0,
            'verified_native_event_ids': [f'native-{day}-{i}' for i in range(3 if status == 'usable' else 1)]}


def build(records, coverage, at=AT):
    days, _, _ = audit.closed_days(records, at)
    return receipts.build_receipts(days, at, bundle(), {'fixture': True}, coverage, {PERSONA}, 'aws-acct')


def by_day(items, account):
    return {r['key']['day']: r for r in items if r['key']['account'] == account}


def test_incomplete_persona_day_is_neither_scored_nor_added_to_history():
    persona_days = dates('2026-11-01', 9)  # 1-9 Nov
    records = [aws(PERSONA, d) for d in persona_days] + [aws(PERSONA, d, action='HeadObject') for d in persona_days]
    coverage = {(PERSONA, d): cell(d, 'incomplete' if d == '2026-11-03' else 'usable') for d in persona_days}
    out = by_day(build(records, coverage), PERSONA)
    third = out['2026-11-03']
    assert third['input']['status'] == 'not_scored_by_coverage_policy' and third['detectors'] == {}
    assert third['coverage']['policy_status'] == 'incomplete' and third['coverage']['missed'] == 2
    assert third['completeness'] == 'unknown'
    # 3 Nov never enters history: the 7th accepted day (8 Nov) is the first with 5 prior accepted days.
    assert out['2026-11-08']['history']['prior_accepted_days'] == ['2026-11-01', '2026-11-02', '2026-11-04',
                                                                    '2026-11-05', '2026-11-06', '2026-11-07']
    assert out['2026-11-07']['input']['status'] == 'eligible'
    assert '2026-11-03' not in out['2026-11-09']['history']['prior_accepted_days']
    scored = [r for r in out.values() if r['detectors']]
    assert scored and all(r['completeness'] == 'policy_verified' for r in scored)


def test_scored_receipt_fields_scores_and_labels():
    persona_days = dates('2026-11-01', 7)
    records = [aws(PERSONA, d) for d in persona_days]
    out = by_day(build(records, {(PERSONA, d): cell(d, 'usable') for d in persona_days}), PERSONA)
    receipt = out['2026-11-07']
    assert REQUIRED <= set(receipt) and receipt['risk_tier'] is None and receipt['alert'] is False
    assert receipt['label'].startswith('experimental model diagnostic') and receipt['live_activation'] is False
    assert receipt['key'] == {'source': 'aws_cloudtrail', 'scope': 'aws-acct', 'account': PERSONA, 'day': '2026-11-07'}
    assert receipt['source_timezone'] == 'Asia/Kuala_Lumpur' and receipt['features']['names'] == v2.FEATURES
    model, scaler, columns = bundle()['C']
    expected = trainer.score_rows(model, scaler.transform(trainer.matrix([{'features': receipt['features']['raw_values']}], columns)))[0]
    assert receipt['detectors']['C']['score_raw_mse'] == expected
    assert sum(t['additive_term'] for t in receipt['detectors']['C']['terms']) == pytest.approx(expected, rel=1e-6)
    assert {f['kind'] for f in receipt['facts']} >= {'volume', 'hours', 'action_mix'}
    assert json.loads(json.dumps(receipt)) == receipt  # JSON-safe
    assert len({r['receipt_id'] for r in out.values()}) == len(out)


def test_excluded_dates_and_days_before_history_start_carry_reasons():
    records = [aws(PERSONA, d) for d in ['2026-10-29', '2026-11-08']]
    out = by_day(build(records, {(PERSONA, '2026-11-08'): cell('2026-11-08', 'excluded_case_date')}), PERSONA)
    assert out['2026-10-29']['coverage']['policy_status'] == 'excluded_before_history_start'
    assert out['2026-11-08']['coverage']['policy_status'] == 'excluded_case_date'
    assert all(r['detectors'] == {} for r in out.values())


def test_fully_missed_persona_day_is_visible_without_events_or_history():
    persona_days = dates('2026-11-01', 7)
    observed = [d for d in persona_days if d != '2026-11-03']  # 3 Nov: every planned action missed, 0 events
    coverage = {(PERSONA, d): cell(d, 'usable') for d in observed}
    coverage[PERSONA, '2026-11-03'] = dict(cell('2026-11-03', 'incomplete'), verified=0, missed=3)
    coverage[PERSONA, '2026-11-08'] = dict(cell('2026-11-08', 'planned_idle'), planned=0)
    out = by_day(build([aws(PERSONA, d) for d in observed], coverage), PERSONA)
    gap = out['2026-11-03']
    assert gap['key'] == {'source': 'aws_cloudtrail', 'scope': 'aws-acct', 'account': PERSONA, 'day': '2026-11-03'}
    assert gap['coverage']['observed_events'] == 0 and gap['coverage']['missed'] == 3 and gap['detectors'] == {}
    assert '2026-11-03' not in out['2026-11-07']['history']['prior_accepted_days']
    assert '2026-11-08' not in out  # planned idle: no manufactured day


def test_v2_history_provenance_separates_expanding_and_rolling_scopes_past_28_days():
    persona_days = dates('2026-11-01', 35)
    out = by_day(build([aws(PERSONA, d) for d in persona_days], {(PERSONA, d): cell(d, 'usable') for d in persona_days},
                       at=datetime(2026, 12, 10, 4, 0, tzinfo=timezone.utc)), PERSONA)
    last = out[persona_days[-1]]
    assert last['schema'] == 'clue_v2_live_diagnostic_receipt_v2'
    history = last['history']
    assert history['expanding_history_days'] == history['prior_accepted_days'] == persona_days[:34]
    assert history['rolling_window_days'] == persona_days[6:34] and len(history['rolling_window_days']) == 28
    assert history['feature_history_scope']['new_action_count'] == 'expanding_history_days'
    assert {history['feature_history_scope'][f] for f in v2.FEATURES[5:]} == {'rolling_window_days'}
    assert {history['feature_history_scope'][f] for f in v2.FEATURES[:4]} == {'current_day_only'}
    early = out[persona_days[3]]['history']  # below 28: both scopes are the same short list
    assert early['rolling_window_days'] == early['expanding_history_days'] == persona_days[:3]
    assert last['detectors']['C']['score_raw_mse'] is not None  # additive fields only; scoring still runs


def test_non_persona_accounts_keep_frozen_rules_and_unknown_completeness():
    infra = [aws(INFRA, d, action='DescribeAlarms') for d in dates('2026-11-01', 3)]
    out = by_day(build(infra, {}), INFRA)
    assert {r['coverage']['policy_status'] for r in out.values()} == {'outside_policy_completeness_unknown'}
    assert {r['input']['status'] for r in out.values()} == {'invalid_input'}
    assert all(r['completeness'] == 'unknown' and r['detectors'] == {} for r in out.values())


def test_run_is_read_only_and_writes_versioned_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(receipts, 'ROOT', tmp_path)
    db = tmp_path / 'events.db'
    rows = [aws(PERSONA, d) for d in dates('2026-11-01', 7)]
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, source, source_account_id, account_key, event_id, '
                    'payload_digest, timestamp, action, resource, metadata, ingested_at)')
        for r in rows:
            con.execute('INSERT INTO events (source,source_account_id,account_key,event_id,payload_digest,timestamp,'
                        'action,resource,metadata,ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?)', tuple(r.values()))
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'account_id': '123456789012', 'stack': 'argus-ueba-actors', 'ledger_dir': str(tmp_path)}))
    mapping = ({'persona-01': PERSONA}, {'unavailable_personas': [], 'invalid_key_rows': {}, 'late_or_unparseable_rows': {}})
    monkeypatch.setattr(receipts.policy, 'persona_account_keys', lambda *a: mapping)
    monkeypatch.setattr(receipts.policy, 'persona_day_coverage',
                        lambda *a: [dict(cell(d, 'usable'), persona='persona-01') for d in dates('2026-10-30', 11)])
    monkeypatch.setattr(receipts, 'load_bundle', lambda *a: (bundle(), {'fixture': True}))
    before = db.read_bytes()
    manifest = receipts.run(db, config, 'prereg', 'training', tmp_path / 'data/receipts', at=AT)
    assert db.read_bytes() == before
    lines = (tmp_path / 'data/receipts/receipts.jsonl').read_bytes()
    assert manifest['receipts'] == 7 and manifest['scored_receipts'] == 2  # 6 and 7 Nov have 5+ prior days
    assert manifest['receipts_sha256'] == hashlib.sha256(lines).hexdigest()
    assert manifest['live_activation'] is False and manifest['alerts_created'] is False
    assert manifest['persona_mapping']['unavailable_personas'] == [] and 'atomic' in manifest['snapshot_note']
    first = json.loads(lines.splitlines()[-1])
    assert first['coverage']['observed_events'] == 1 and len(first['coverage']['verified_native_event_ids']) == 3
    with pytest.raises(ValueError):
        receipts.run(db, config, 'prereg', 'training', tmp_path / 'data/receipts', at=AT)
