"""Read-only inference contracts; no provider calls or task installation."""
from datetime import datetime, timezone
import json
import sqlite3

import pytest

from scripts import cloud_ae_shadow as shadow

NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
ACCOUNT = '123456789012'


@pytest.fixture
def database(tmp_path):
    path = tmp_path / 'events.db'
    with sqlite3.connect(path) as db:
        db.execute('''CREATE TABLE events(id INTEGER PRIMARY KEY,timestamp TEXT,user TEXT,
            source TEXT,action TEXT,resource TEXT,ip_address TEXT,metadata TEXT,
            source_account_id TEXT,event_id TEXT)''')
        rows = [
            ('2026-10-27T08:00:00Z', 'secret@example.test', 'aws_cloudtrail', 'GetObject', 'bucket-a', '192.0.2.1', '{}', ACCOUNT, 'prior'),
            ('2026-10-28T08:00:00Z', 'secret@example.test', 'aws_cloudtrail', 'GetObject', 'bucket-b', '192.0.2.1', '{}', ACCOUNT, 'current'),
            ('2026-10-28T08:01:00Z', '', 'aws_cloudtrail', 'AssumeRole', '', '', '{}', ACCOUNT, 'missing'),
            ('2026-10-28T08:00:00Z', 'other', 'aws_cloudtrail', 'GetObject', 'bucket-a', '', '{}', '999999999999', 'foreign'),
            ('2026-10-28T08:00:00Z', 'secret@example.test', 'github', 'PushEvent', 'repo', '', '{}', ACCOUNT, 'github')]
        db.executemany('INSERT INTO events VALUES(NULL,?,?,?,?,?,?,?,?,?)', rows)
    return path


def test_namespace_history_missing_identity_and_read_only(database):
    before = database.read_bytes()
    events = shadow.read_snapshot(database, ACCOUNT, NOW)
    assert len(events) == 3
    rows, matrix, excluded = shadow.prepare(events, 'a' * 64, NOW)
    assert len(rows) == 1 and excluded == 1
    assert rows[0]['observed_window_events'] == 1 and rows[0]['observed_prior_events'] == 1
    assert matrix[0][shadow.CLOUD_FEATURES.index('new_action_count')] == 0
    assert rows[0]['risk_level'] == 'Unknown' and rows[0]['review_priority'] is None
    assert 'secret' not in json.dumps(rows) and ACCOUNT not in json.dumps(rows)
    assert database.read_bytes() == before


def test_same_day_never_becomes_prior_history(database):
    events = shadow.read_snapshot(database, ACCOUNT, NOW)
    events[0]['_utc_day'] = '2026-10-28'
    events[0]['action'] = 'HeadObject'
    rows, matrix, _ = shadow.prepare(events, 'a' * 64, NOW)
    assert rows[0]['observed_prior_events'] == 0
    assert matrix[0][shadow.CLOUD_FEATURES.index('new_action_count')] == 2


def test_other_principal_history_cannot_suppress_novelty(database):
    events = shadow.read_snapshot(database, ACCOUNT, NOW)
    events[0]['user'] = 'another-principal'
    rows, matrix, _ = shadow.prepare(events, 'a' * 64, NOW)
    current = next(i for i, r in enumerate(rows) if r['partial_current_utc_day'])
    assert rows[current]['observed_prior_events'] == 0
    assert matrix[current][shadow.CLOUD_FEATURES.index('new_action_count')] == 1


def test_alias_stable_but_private_salt_changes_it(database):
    events = shadow.read_snapshot(database, ACCOUNT, NOW)
    first = shadow.prepare(events, 'a' * 64, NOW)[0][0]['account_alias']
    assert first == shadow.prepare(list(reversed(events)), 'a' * 64, NOW)[0][0]['account_alias']
    assert first != shadow.prepare(events, 'b' * 64, NOW)[0][0]['account_alias']


@pytest.mark.parametrize('fault', ['future', 'naive', 'metadata', 'limit'])
def test_snapshot_refuses_invalid_or_truncated_history(database, fault):
    with sqlite3.connect(database) as db:
        if fault == 'future':
            db.execute("UPDATE events SET timestamp='2027-01-01T00:00:00Z' WHERE event_id='current'")
        elif fault == 'naive':
            db.execute("UPDATE events SET timestamp='2026-10-28T08:00:00' WHERE event_id='current'")
        elif fault == 'metadata':
            db.execute("UPDATE events SET metadata='[]' WHERE event_id='current'")
    with pytest.raises(ValueError):
        shadow.read_snapshot(database, ACCOUNT, NOW, limit=1 if fault == 'limit' else 100)


def test_expiry_precedes_model_and_database_access(monkeypatch):
    monkeypatch.setattr(shadow, 'validate', lambda _: pytest.fail('Validation/model access after expiry'))
    assert shadow.run({}, now=shadow.END)['status'] == 'shadow_expired'


def test_provisional_report_privacy_failure_and_html(database, tmp_path, monkeypatch):
    cfg = {'database': str(database), 'account_id': ACCOUNT, 'alias_key': 'a' * 64,
           'output_dir': str(tmp_path), 'source_sha256': {}, 'artifacts': {}}
    monkeypatch.setattr(shadow, 'validate', lambda c: c)
    monkeypatch.setattr(shadow, 'infer', lambda c, x: [{'raw_reconstruction_mse': .25,
        'maximum_absolute_standardized_feature': 1., 'largest_residual_features': ['event_count']} for _ in x])
    assert shadow.run(cfg, NOW)['status'] == 'success'
    report = json.loads((tmp_path / 'latest.json').read_text())
    page = (tmp_path / 'latest.html').read_text()
    for secret in ('secret@example.test', '192.0.2.1', 'bucket-a', ACCOUNT):
        assert secret not in page and secret not in json.dumps(report)
    assert report['activated'] is False and report['risk_thresholds_applied'] is False
    assert 'Raw AE MSE' in page and 'not SHAP' in page and 'STALE' in page
    before = (tmp_path / 'latest.json').read_bytes()
    shadow.mark_attempt(tmp_path / 'last_attempt.json', {'status': 'failed', 'error_type': 'ValueError'})
    assert (tmp_path / 'latest.json').read_bytes() == before
    assert 'Showing previous successful output only' in (tmp_path / 'latest.html').read_text()


def test_artifact_drift_rejected_before_deserialisation(tmp_path):
    cfg = {'schema': 'argus_cloud_ae_shadow_v1', 'end_utc': shadow.END.isoformat(),
           'account_id': ACCOUNT, 'alias_key': 'a' * 64, 'source_sha256': shadow.source_hashes(),
           'artifacts': {name: {'path': str(tmp_path / name), 'sha256': 'a' * 64} for name in shadow.ARTIFACTS}}
    for name in shadow.ARTIFACTS:
        (tmp_path / name).write_bytes(b'not a model; must never deserialize')
    with pytest.raises(ValueError, match='artifact changed'):
        shadow.validate(cfg)


def test_real_inference_matches_explicit_standardized_mse(tmp_path):
    torch = pytest.importorskip('torch')
    import joblib
    import numpy as np
    from sklearn.preprocessing import StandardScaler
    from scripts.train_cloud_ae import _build_cloud_ae
    torch.manual_seed(42)
    model = _build_cloud_ae(12)
    torch.save({'input_dim': 12, 'features': shadow.CLOUD_FEATURES, 'state_dict': model.state_dict()}, tmp_path / 'cloud_ae_v1.pt')
    scaler = StandardScaler().fit(np.asarray([[0] * 12, [2] * 12], dtype=np.float32))
    joblib.dump(scaler, tmp_path / 'cloud_scaler_v1.pkl')
    (tmp_path / 'cloud_ae_metrics.json').write_text('{}')
    cfg = {'artifacts': {name: {'path': str(tmp_path / name)} for name in shadow.ARTIFACTS}}
    data = [[1.] * 12, [2.] * 12]
    actual = shadow.infer(cfg, data)
    x = torch.tensor(scaler.transform(np.asarray(data, dtype=np.float32)))
    model.eval()
    with torch.inference_mode():
        expected = ((model(x) - x) ** 2).mean(dim=1).tolist()
    assert [r['raw_reconstruction_mse'] for r in actual] == pytest.approx(expected)
