"""Synthetic exports only; these fixtures are not live baseline evidence."""
from datetime import datetime, timezone
import hashlib
import json
import sqlite3

import pytest

from scripts import aws_lab_daily_features as features, export_live_daily as exporter
from scripts.tests.test_live_history_readiness import study, ACCOUNT, STACK, NOW


@pytest.fixture
def export_study(study):
    with sqlite3.connect(study[1]) as db:
        db.execute("ALTER TABLE events ADD COLUMN ip_address TEXT DEFAULT '192.0.2.1'")
    return study


def resource_map():
    return {name: name for name in features.CONTRACT['resource_domain']}


def event(stamp='2026-10-30T00:00:00Z', action='GetObject', resource='p01', ip='192.0.2.1'):
    date = datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone(exporter.readiness.MALAYSIA).date().isoformat()
    return {'timestamp': stamp, 'persona': 'persona-01', 'day': date, 'action': action,
            'resource': resource, 'ip_address': ip}


def test_exact_feature_counts_and_ip_missingness():
    events = [event(), event(action='HeadObject', resource='p02', ip=None),
              event(action='GetBucketLocation', resource='confidential', ip='AWS Internal')]
    row = features.extract(events, resource_map())
    assert list(row['features']) == features.FEATURES
    assert list(row['features'].values()) == [3, 1, 1, 1, 3, 1, 0, 1]
    assert row['ip_observability'] == {'valid_events': 1, 'missing_events': 1, 'invalid_events': 1}
    assert row['action_counts'] == {'GetObject': 1, 'HeadObject': 1, 'GetBucketLocation': 1}


@pytest.mark.parametrize('stamp,expected', [('2026-10-29T23:59:59Z', 1),  # Fri07:59MY
    ('2026-10-30T00:00:00Z', 0), ('2026-10-30T11:59:59Z', 0),
    ('2026-10-30T12:00:00Z', 1), ('2026-10-31T02:00:00Z', 1)])
def test_malaysia_off_hours_boundaries(stamp, expected):
    assert features.extract([event(stamp)], resource_map())['features']['off_hours_events'] == expected


def test_resource_identity_not_erased_when_counts_match():
    first = features.extract([event(resource='p01')], resource_map())
    changed = features.extract([event(resource='p06')], resource_map())
    assert first['features'] == changed['features']
    assert first['resource_counts'] != changed['resource_counts']


def test_feature_rejects_empty_mixed_day_or_unknown_resource():
    with pytest.raises(ValueError): features.extract([], resource_map())
    with pytest.raises(ValueError): features.extract([event(resource='real-production')], resource_map())
    with pytest.raises(ValueError): features.extract([event(), event('2026-10-31T00:00:00Z')], resource_map())
    with pytest.raises(ValueError): features.extract([event('2026-10-30T00:00:00')], resource_map())


def test_readonly_export_evidence_parity_privacy_and_no_overwrite(export_study, tmp_path):
    before = [p.read_bytes() for p in export_study]
    out = tmp_path / 'candidate'
    manifest = exporter.export(*export_study, ACCOUNT, STACK, out, NOW)
    data = json.loads((out / 'dataset.json').read_text())
    contract = json.loads((out / 'feature_contract.json').read_text())
    assert contract == features.CONTRACT
    assert hashlib.sha256((out / 'feature_contract.json').read_bytes()).hexdigest() == manifest['feature_contract_sha256']
    assert hashlib.sha256((out / 'dataset.json').read_bytes()).hexdigest() == manifest['dataset_sha256']
    assert manifest['partition_rows'] == {'fit': 42, 'validation': 12, 'normal_calibration': 18}
    assert len(data['rows']) == 72 and manifest['history_gates_pass'] is True
    assert sum(r['features']['event_count'] for r in data['rows']) == manifest['included_native_events']
    assert all(r['features']['event_count'] == r['coverage']['verified'] for r in data['rows'])
    for secret in (ACCOUNT, '192.0.2.1', 'request-', 'principal-', 'arn:aws:'):
        assert secret not in json.dumps(data)
    assert before == [p.read_bytes() for p in export_study]
    with pytest.raises(ValueError): exporter.export(*export_study, ACCOUNT, STACK, out, NOW)


def test_missing_receipt_removes_whole_day_not_just_failed_action(export_study, tmp_path):
    with sqlite3.connect(export_study[0]) as db:
        day, role, event_id = db.execute("SELECT day,persona,native_event_id FROM actions WHERE day='2026-10-30' LIMIT 1").fetchone()
    with sqlite3.connect(export_study[1]) as db:
        db.execute('DELETE FROM events WHERE event_id=?', (event_id,))
    out = tmp_path / 'missing'
    exporter.export(*export_study, ACCOUNT, STACK, out, NOW)
    data = json.loads((out / 'dataset.json').read_text())
    assert not any(r['date_local'] == day and r['persona'] == role for r in data['rows'])
    assert next(r for r in data['readiness']['days'] if r['day'] == day and r['persona'] == role)['status'] == 'incomplete'


def test_later_normal_events_cannot_change_fitting_features(export_study, tmp_path):
    first = tmp_path / 'first'
    exporter.export(*export_study, ACCOUNT, STACK, first, NOW)
    with sqlite3.connect(export_study[1]) as db:
        db.execute("UPDATE events SET ip_address='2001:db8::1' WHERE timestamp>='2026-11-06'")
    second = tmp_path / 'second'
    exporter.export(*export_study, ACCOUNT, STACK, second, NOW)
    rows1 = json.loads((first / 'dataset.json').read_text())['rows']
    rows2 = json.loads((second / 'dataset.json').read_text())['rows']
    assert [r for r in rows1 if r['partition'] == 'fit'] == [r for r in rows2 if r['partition'] == 'fit']


def test_early_empty_export_and_partial_day_exclusion(export_study, tmp_path):
    with sqlite3.connect(export_study[0]) as db:
        db.execute("DELETE FROM actions WHERE day>='2026-10-30'")
    out = tmp_path / 'early'
    m = exporter.export(*export_study, ACCOUNT, STACK, out, datetime(2026, 10, 29, tzinfo=timezone.utc))
    assert m['status'] == 'empty_dataset' and not m['history_gates_pass']
    assert json.loads((out / 'dataset.json').read_text())['rows'] == []


def test_source_drift_refuses_export(export_study, tmp_path, monkeypatch):
    original = exporter.hashes()
    calls = iter([original, {'changed': 'different'}])
    monkeypatch.setattr(exporter, 'hashes', lambda: next(calls))
    out = tmp_path / 'drift'
    with pytest.raises(ValueError, match='source changed'):
        exporter.export(*export_study, ACCOUNT, STACK, out, NOW)
    assert not out.exists()


def test_open_local_fitting_day_is_not_exported(export_study, tmp_path):
    out = tmp_path / 'open'
    exporter.export(*export_study, ACCOUNT, STACK, out, datetime(2026, 10, 30, 12, tzinfo=timezone.utc))
    data = json.loads((out / 'dataset.json').read_text())
    assert not data['rows']
    assert all(r['status'] == 'current_partial' for r in data['readiness']['days'] if r['day'] == '2026-10-30')


def test_legacy_trainer_refuses_new_profile_before_fitting(export_study, tmp_path):
    from scripts.train_verified_cloud import prepare, TrainingRefusal
    out = tmp_path / 'incompatible'
    exporter.export(*export_study, ACCOUNT, STACK, out, NOW)
    with pytest.raises(TrainingRefusal, match='Unsupported dataset contract'):
        prepare(out / 'dataset.json', '2026-11-05', '2026-11-07', '2026-11-10')
