"""Live HTTP workflow without CERT files, production state or model inference."""
import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from backend import event_store, investigations, loader, main


@pytest.fixture
def live_client(monkeypatch, tmp_path):
    monkeypatch.setattr(loader, 'LIVE_MODE', True)
    monkeypatch.setattr(main, 'LIVE_MODE', True)
    monkeypatch.setattr(main, 'ARGUS_MODE', 'live')
    monkeypatch.setattr(main, 'store', loader.DataStore())
    monkeypatch.setattr(event_store, 'DB_PATH', tmp_path / 'events.db')
    monkeypatch.setattr(investigations, 'INVESTIGATIONS_PATH', tmp_path / 'investigations.json')
    monkeypatch.setattr(main.cloud_ae_scorer, 'score_user', lambda *_: 0.85)

    def forbidden_read(*args, **kwargs):
        raise AssertionError('Live mode attempted to read benchmark data')

    monkeypatch.setattr(loader.pd, 'read_csv', forbidden_read)
    monkeypatch.setattr(loader.pd, 'read_parquet', forbidden_read)
    with TestClient(main.app) as client:
        yield client


def cloud_event(user='cloud-alice'):
    return {'source': 'aws_cloudtrail', 'event': {
        'eventTime': '2026-10-27T02:00:00Z',
        'userIdentity': {'userName': user}, 'eventName': 'ListBuckets',
        'eventSource': 's3.amazonaws.com', 'sourceIPAddress': '203.0.113.10',
        'eventID': 'live-test-event',
    }}


def test_empty_live_startup_without_benchmark_files(live_client):
    health = live_client.get('/').json()
    assert health['application_mode'] == 'live'
    assert health['users'] == 0
    stats = live_client.get('/stats').json()
    assert stats['total_users'] == 0
    assert stats['insiders'] is None
    assert stats['high_threshold'] == main.LIVE_HIGH_THRESHOLD
    assert live_client.get('/users').json()['users'] == []


def test_cloud_ingest_to_list_detail_stats_and_investigation(live_client):
    response = live_client.post('/ingest', json=cloud_event())
    assert response.status_code == 200
    assert response.json()['ae_live_score'] == 0.85
    listing = live_client.get('/users').json()
    assert listing['total'] == 1
    user = listing['users'][0]
    assert user['data_source'] == 'cloud'
    assert user['is_insider'] is None and user['scenario'] is None
    assert user['risk_level'] == 'High'
    detail = live_client.get('/users/cloud-alice')
    assert detail.status_code == 200
    assert detail.json()['ae_score'] == 0.85
    stats = live_client.get('/stats').json()
    assert stats['total_users'] == stats['high_risk'] == 1
    assert live_client.get('/').json()['users'] == 1
    assert live_client.get('/users?source=cert').json()['total'] == 0
    assert live_client.get('/users?q=missing').json()['total'] == 0
    assert live_client.get('/users?risk=Low').json()['total'] == 0
    assert live_client.get('/users/cloud-alice/events').json()[0]['source'] == 'aws_cloudtrail'
    queued = live_client.post('/investigations/bulk').json()
    assert queued['created'] == queued['total_high_risk'] == 1
    assert live_client.post('/investigations/bulk').json()['skipped'] == 1


def test_unavailable_model_is_unknown_not_low(live_client, monkeypatch):
    monkeypatch.setattr(main.cloud_ae_scorer, 'score_user', lambda *_: None)
    assert live_client.post('/ingest', json=cloud_event()).status_code == 200
    stored = event_store.get_live_score('cloud-alice')
    assert stored['ae_live'] is None
    user = live_client.get('/users?risk=Unknown').json()['users'][0]
    assert user['ae_score'] is None and user['risk_level'] == 'Unknown'
    detail = live_client.get('/users/cloud-alice').json()
    assert detail['ae_score'] is None and detail['risk_level'] == 'Unknown'
    stats = live_client.get('/stats').json()
    assert stats['unscored_users'] == stats['total_users'] == 1
    assert stats['scoring_status']['status'] == 'missing_artifacts'
    assert stats['scoring_status']['model_ready'] is False
    assert detail['scoring_status'] == stats['scoring_status']
    assert stats['low_risk'] == 0
    assert live_client.get('/users/cloud-alice/live-score').json()['ae_live'] is None


def test_live_rejects_cert_ingestion_and_offline_seeding(live_client):
    request = {'source': 'cert_logon', 'event': {'user': 'benchmark-user'}}
    assert live_client.post('/ingest', json=request).status_code == 422
    assert live_client.post('/admin/seed-live-scores', json=[]).status_code == 409
    assert event_store.list_event_store_users() == []


def test_live_hides_legacy_cert_and_seed_only_scores(live_client):
    event_store.insert_event({
        'user': 'cert-only', 'timestamp': '2026-10-27T02:00:00Z',
        'source': 'cert_logon', 'action': 'Logon', 'resource': 'pc1',
        'ip_address': '', 'metadata': {},
    })
    for user in ['cert-only', 'offline-seed']:
        event_store.upsert_live_score(user, 0.99, 0, 0, 1)
    assert live_client.get('/users').json()['total'] == 0
    assert live_client.get('/stats').json()['total_users'] == 0
    for user in ['cert-only', 'offline-seed']:
        assert live_client.get(f'/users/{user}').status_code == 404
        assert live_client.get(f'/users/{user}/events').json() == []
        assert live_client.get(f'/users/{user}/live-score').json()['ae_live'] is None


def test_live_does_not_serve_stale_pseudo_shap_or_call_llms(live_client, monkeypatch):
    live_client.post('/ingest', json=cloud_event())
    event_store.upsert_cloud_shap('cloud-alice', '[]', 'Stale seeded explanation')

    def forbidden_llm(**kwargs):
        raise AssertionError('Unverified evidence was sent to an LLM')

    monkeypatch.setattr(main.ai_suggest, 'generate_ensemble', forbidden_llm)
    assert live_client.get('/users/cloud-alice/shap').status_code == 404
    response = live_client.post('/users/cloud-alice/investigation/suggest')
    assert response.status_code == 503
    assert 'verified AE explanations' in response.json()['detail']


@pytest.mark.parametrize(('mode', 'demo', 'expected'), [
    ('live', 'true', 'live'), ('benchmark', 'true', 'benchmark'),
    ('demo', 'false', 'demo'), (None, 'true', 'demo'), (None, 'false', 'benchmark'),
])
def test_explicit_mode_and_legacy_configuration(mode, demo, expected):
    env = dict(os.environ, DEMO_MODE=demo)
    env.pop('ARGUS_MODE', None)
    if mode is not None:
        env['ARGUS_MODE'] = mode
    result = subprocess.run(
        [sys.executable, '-c', 'from backend.config import ARGUS_MODE; print(ARGUS_MODE)'],
        cwd=Path(__file__).resolve().parents[2], env=env,
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_invalid_mode_fails_before_startup():
    result = subprocess.run(
        [sys.executable, '-c', 'import backend.config'],
        cwd=Path(__file__).resolve().parents[2],
        env=dict(os.environ, ARGUS_MODE='typo'),
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode != 0
    assert 'ARGUS_MODE must be' in result.stderr


def test_actual_live_startup_isolated_from_tracked_benchmark_state(tmp_path):
    script = '''
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import LIVE_STATE_DIR
from backend import event_store, investigations
assert event_store.DB_PATH == LIVE_STATE_DIR / 'events.db'
assert investigations.INVESTIGATIONS_PATH == LIVE_STATE_DIR / 'investigations.json'
with TestClient(app) as client:
    assert client.get('/').json()['users'] == 0
    assert client.get('/stats').json()['insiders'] is None
    assert client.get('/investigations').json() == []
'''
    result = subprocess.run(
        [sys.executable, '-c', script],
        cwd=Path(__file__).resolve().parents[2],
        env=dict(os.environ, ARGUS_MODE='live', DATABASE_URL='sqlite-local',
                 LIVE_STATE_DIR=str(tmp_path / 'live-state'),
                 DATA_DIR=str(tmp_path / 'no-benchmark-data')),
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
