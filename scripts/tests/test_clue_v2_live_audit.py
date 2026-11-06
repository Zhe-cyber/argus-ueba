"""W33 v2 live compatibility diagnostics on synthetic live rows and a fake scorer."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import sqlite3

import pytest

from scripts import audit_clue_v2_live as live

_ids = iter(range(1, 10**9))
PERSONA = 'acct_' + 'a' * 64
INFRA = 'acct_' + 'b' * 64
MYT = timezone(timedelta(hours=8))


def aws(account, day, action='GetObject', service='s3.amazonaws.com', bucket='toy-bucket-01', hour=3, ingested=None):
    return {'source': 'aws_cloudtrail', 'source_account_id': 'aws-acct', 'account_key': account,
            'event_id': f'evt-{next(_ids)}', 'payload_digest': hashlib.sha256(str(next(_ids)).encode()).hexdigest(),
            'timestamp': f'{day}T{hour:02d}:00:00Z', 'action': action, 'resource': bucket,
            'metadata': json.dumps({'eventSource': service}),
            'ingested_at': ingested or f'{day}T{hour:02d}:05:00+00:00'}


def days(n, first='2026-10-20'):
    return [(date.fromisoformat(first) + timedelta(i)).isoformat() for i in range(n)]


AT = datetime(2026, 10, 31, 4, 0, tzinfo=timezone.utc)  # 31 Oct 12:00 MYT: 31 Oct is the open day
FIT_RANGE = {'min': [-1.0] * 9, 'max': [1.0] * 9}


def fake_score(snapshot):
    if not snapshot['five_feature_eligible']:
        return {'B': None, 'C': None, 'BL': None, 'z': None}
    nine = snapshot['nine_feature_eligible']
    count = float(snapshot['features']['event_count'])
    return {'B': count, 'C': count if nine else None, 'BL': count if nine else None,
            'z': [2.0 if i == 0 else 0.0 for i in range(9)] if nine else None}


CUTOFFS = {name: {'0.01': 2.5, '0.05': 1.5} for name in ('B', 'C', 'BL')}


def test_persona_days_are_usable_while_unsupported_infrastructure_days_are_invalid():
    records = [aws(PERSONA, d) for d in days(7)] + [aws(PERSONA, d, action='HeadObject') for d in days(7)]
    records += [aws(INFRA, d, action='DescribeAlarms', service='monitoring.amazonaws.com') for d in days(7)]
    records.append(aws(PERSONA, '2026-10-31'))  # open MYT day: excluded as partial
    built, exclusions, _ = live.closed_days(records, AT)
    rows = live.snapshots(built)
    assert all(row['scope'] == 'aws-acct' for row in rows)
    persona = [r for r in rows if r['account'] == PERSONA]
    assert [r['status'] for r in persona] == ['cold_start'] * 5 + ['eligible'] * 2
    assert all(r['status'] == 'invalid_input' for r in rows if r['account'] == INFRA)
    assert exclusions['aws_cloudtrail']['current_day_partial'] == 1
    summary = live.summarise(rows, fake_score, CUTOFFS, FIT_RANGE, exclusions, {})['aws_cloudtrail']
    assert summary['nine_feature_eligible_days'] == 2 and summary['projection_valid_days'] == 7
    assert summary['invalid_day_issue_events'] == {'unsupported_service_resource_semantics': 7}
    assert summary['raw_scores']['C'] == {'n': 2, 'min': 2.0, 'median': 2.0, 'max': 2.0}
    assert summary['above_clue_cutoff_descriptive_only']['C'] == {'0.01': 0, '0.05': 2}
    assert summary['outside_observed_clue_fit_range'] == {'event_count': 2}  # z=2 beyond the fit max of 1
    assert summary['large_standardised_magnitude_abs_z_gt_4'] == {}            # yet not a large |z|
    assert {r['account']: r for r in summary['per_account_status']}[PERSONA] == {
        'scope': 'aws-acct', 'account': PERSONA, 'cold_start': 5, 'eligible': 2}
    assert summary['decision'] == 'model_input_available_with_representation_warnings'


def test_cutoff_compares_utc_instants_not_offset_text():
    at_myt = datetime(2026, 10, 31, 12, 0, tzinfo=MYT)  # = 04:00 UTC
    late = aws(PERSONA, '2026-10-29', ingested='2026-10-31T05:00:00+00:00')  # 05:00 UTC > 04:00 UTC
    early_z = aws(PERSONA, '2026-10-29', ingested='2026-10-31T03:59:59Z')
    late_offset = aws(PERSONA, '2026-10-29', ingested='2026-10-31T12:30:00+08:00')  # 04:30 UTC
    _, exclusions, _ = live.closed_days([late, early_z, late_offset], at_myt)
    assert exclusions['aws_cloudtrail'] == {'ingested_after_cutoff': 2}
    with pytest.raises(ValueError):
        live.utc_cutoff(datetime(2026, 10, 31, 12, 0))


def test_malformed_future_rejected_and_unsupported_rows_are_counted_not_dropped():
    future = aws(PERSONA, '2026-11-02', ingested='2026-10-30T00:00:00Z')  # event dated after the cut-off
    broken = dict(aws(PERSONA, '2026-10-20'), account_key='not-a-key')
    other = dict(aws(PERSONA, '2026-10-20'), source='azure_ad')
    for bad in ('not-a-time', '2026-10-20T03:05:00', None):
        _, exclusions, _ = live.closed_days([dict(aws(PERSONA, '2026-10-20'), ingested_at=bad)], AT)
        assert exclusions['aws_cloudtrail'] == {'malformed_ingestion_time': 1}
    _, exclusions, _ = live.closed_days([future, broken, other], AT)
    assert exclusions['aws_cloudtrail'] == {'future_event': 1, 'projection_rejected': 1}
    assert exclusions['unsupported_source'] == {'azure_ad': 1}


def test_unknown_github_label_is_reported_and_invalidates_the_day():
    row = {'source': 'github_events', 'source_account_id': 'gh', 'account_key': PERSONA, 'event_id': 'g1',
           'payload_digest': 'c' * 64, 'timestamp': '2026-10-29T03:00:00Z', 'action': 'Repository push',
           'resource': 'owner/repo', 'metadata': '{}', 'ingested_at': '2026-10-29T03:05:00+00:00'}
    built, exclusions, labels = live.closed_days([row], AT)
    rows = live.snapshots(built)
    assert rows[0]['status'] == 'invalid_input' and labels['github_events'] == {'Repository push': 1}
    summary = live.summarise(rows, fake_score, CUTOFFS, FIT_RANGE, exclusions, labels)
    assert summary['github_events']['unknown_action_labels'] == {'Repository push': 1}
    assert summary['github_events']['decision'] == 'extractor_runs_no_nine_feature_input_yet'
    assert summary['cloudflare_access']['decision'] == 'no_observed_closed_days'


def test_audit_reads_store_read_only_and_never_writes(tmp_path, monkeypatch):
    db = tmp_path / 'events.db'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, source, source_account_id, account_key, event_id, '
                    'payload_digest, timestamp, action, resource, metadata, ingested_at)')
        for record in [aws(PERSONA, d) for d in days(6)]:
            con.execute('INSERT INTO events (source,source_account_id,account_key,event_id,payload_digest,timestamp,'
                        'action,resource,metadata,ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?)', tuple(record.values()))
    before = db.read_bytes()
    monkeypatch.setattr(live, 'load_live_scorer', lambda *a: (fake_score, CUTOFFS, FIT_RANGE, {'fixture': True}))
    result = live.audit(db, 'prereg', 'training', at=datetime(2026, 10, 31, 12, 0, tzinfo=MYT))
    assert db.read_bytes() == before
    assert result['cutoff_utc'] == '2026-10-31T04:00:00+00:00'
    assert result['live_activation'] is False and result['alerts_created'] is False
    assert result['sources']['aws_cloudtrail']['nine_feature_eligible_days'] == 1
    assert result['bindings']['snapshot_rows'] == 6
