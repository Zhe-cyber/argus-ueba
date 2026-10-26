"""Retries must not inflate observations or strand a partly processed event."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from backend import event_store, investigations, loader, main
from backend.normalizer import normalize


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(loader, 'LIVE_MODE', True)
    monkeypatch.setattr(main, 'LIVE_MODE', True)
    monkeypatch.setattr(main, 'store', loader.DataStore())
    monkeypatch.setattr(event_store, 'DB_PATH', tmp_path / 'events.db')
    monkeypatch.setattr(investigations, 'INVESTIGATIONS_PATH', tmp_path / 'investigations.json')
    monkeypatch.setattr(main.cloud_ae_scorer, 'score_user', lambda *_: 0.2)
    with TestClient(main.app, raise_server_exceptions=False) as instance:
        yield instance


def payload(event_id='one', namespace=''):
    return {'source': 'aws_cloudtrail', 'source_account_id': namespace, 'event': {
        'eventID': event_id, 'eventTime': '2026-10-27T12:00:00Z',
        'userIdentity': {'userName': 'retry-test'}, 'eventName': 'ListBuckets',
        'eventSource': 's3.amazonaws.com', 'sourceIPAddress': '203.0.113.1',
    }}


def test_retry_returns_original_receipt_without_rescoring(client, monkeypatch):
    first = client.post('/ingest', json=payload()).json()
    score = event_store.get_live_score('retry-test')
    alerts_before = client.get('/alerts').json()

    def forbidden(*args):
        raise AssertionError('Duplicate invoked scoring or rarity again')

    monkeypatch.setattr(main.cloud_ae_scorer, 'score_user', forbidden)
    monkeypatch.setattr(main, 'compute_rarity_flags', forbidden)
    event_store.init_db()  # A fresh connection reads the persisted receipt.
    second_response = client.post('/ingest', json=payload())
    assert second_response.status_code == 200
    second = second_response.json()
    assert first.pop('duplicate') is False
    assert second.pop('duplicate') is True
    assert second == first
    assert event_store.get_total_event_count('retry-test') == 1
    assert event_store.get_live_score('retry-test') == score
    assert client.get('/alerts').json() == alerts_before


def test_conflicting_native_key_is_rejected(client):
    assert client.post('/ingest', json=payload()).status_code == 200
    conflicting = payload()
    conflicting['event']['eventName'] = 'DeleteBucket'
    assert client.post('/ingest', json=conflicting).status_code == 409
    assert event_store.get_total_event_count('retry-test') == 1


def test_keys_are_separate_across_accounts_and_sources(client):
    assert client.post('/ingest', json=payload(namespace='account-a')).status_code == 200
    assert client.post('/ingest', json=payload(namespace='account-b')).json()['duplicate'] is False
    cf = {'source': 'cloudflare_access', 'source_account_id': 'account-a', 'event': {
        'ray_id': 'one', 'created_at': '2026-10-27T12:00:00Z',
        'user_email': 'retry-test', 'allowed': True, 'action': 'login',
    }}
    assert client.post('/ingest', json=cf).json()['duplicate'] is False
    assert event_store.get_total_event_count('retry-test') == 3


def test_aws_native_account_is_used_and_contradictions_rejected(client):
    event = payload()
    event['event']['recipientAccountId'] = '123456789012'
    first = client.post('/ingest', json=event).json()
    assert first['source_account_id'] == '123456789012'
    event['source_account_id'] = '123456789012'
    assert client.post('/ingest', json=event).json()['duplicate'] is True
    event['source_account_id'] = '999999999999'
    assert client.post('/ingest', json=event).status_code == 422


def test_score_failure_rolls_back_and_retry_recovers(client, monkeypatch):
    def fail(*args):
        raise RuntimeError('Injected scoring failure')

    monkeypatch.setattr(main.cloud_ae_scorer, 'score_user', fail)
    assert client.post('/ingest', json=payload()).status_code == 500
    assert event_store.get_total_event_count('retry-test') == 0
    assert event_store.get_live_score('retry-test') is None
    monkeypatch.setattr(main.cloud_ae_scorer, 'score_user', lambda *_: 0.3)
    response = client.post('/ingest', json=payload())
    assert response.status_code == 200
    assert response.json()['duplicate'] is False
    assert event_store.get_total_event_count('retry-test') == 1


def test_optional_alert_failure_rolls_back_its_partial_write(client, monkeypatch):
    original = main.astore.create_alert

    def partial_failure(*args):
        original(*args)
        with event_store._db() as con:
            event_store._cursor(con).execute('SELECT * FROM nonexistent_alert_test_table')

    monkeypatch.setattr(main.astore, 'create_alert', partial_failure)
    response = client.post('/ingest', json=payload())
    assert response.status_code == 200
    assert event_store.get_total_event_count('retry-test') == 1
    with event_store._db() as con:
        assert con.execute('SELECT COUNT(*) FROM alerts').fetchone()[0] == 0
    assert client.post('/ingest', json=payload()).json()['duplicate'] is True


def test_identical_idless_cert_replay_is_preserved(client, monkeypatch):
    monkeypatch.setattr(main, 'LIVE_MODE', False)
    monkeypatch.setattr(main.ae_scorer, 'score_user', lambda *args, **kwargs: None)
    event = {'source': 'cert_logon', 'event': {
        'id': 'cert-row-id', 'user': 'cert-retry', 'date': '2026-10-27T12:00:00Z',
        'pc': 'pc1', 'activity': 'Logon',
    }}
    for _ in range(2):
        response = client.post('/ingest', json=event)
        assert response.status_code == 200
        assert response.json()['event_id'] is None
        assert response.json()['duplicate'] is False
    assert event_store.get_total_event_count('cert-retry') == 2


def test_native_ids_exclude_correlation_and_malformed_values():
    assert normalize({'id': 'signin-id'}, 'azure_ad')['event_id'] == 'signin-id'
    assert normalize({'CorrelationId': 'shared-request'}, 'azure_ad')['event_id'] is None
    assert normalize({'id': 123}, 'github_events')['event_id'] == '123'
    for invalid in ('', '   ', True, {}, []):
        assert normalize({'eventID': invalid}, 'aws_cloudtrail')['event_id'] is None


def test_old_schema_migration_retains_rows(client, monkeypatch, tmp_path):
    old_file = tmp_path / 'old.db'
    with sqlite3.connect(old_file) as con:
        con.execute(event_store._DDL_EVENTS)
        con.execute('INSERT INTO events ("user", timestamp, source, action, resource, ingested_at) '
                    "VALUES ('legacy', 'old-time', 'cert_logon', 'Logon', 'pc1', 'old-time')")
    monkeypatch.setattr(event_store, 'DB_PATH', old_file)
    event_store.init_db()
    event_store.init_db()
    assert event_store.get_total_event_count('legacy') == 1
    event = normalize(payload()['event'], 'aws_cloudtrail')
    assert event_store.insert_event(event) is True
    assert event_store.insert_event(event) is False
    for _ in range(2):
        assert event_store.insert_event(normalize({'user': 'legacy'}, 'cert_logon')) is True
    assert event_store.get_total_event_count('legacy') == 3


def test_concurrent_native_inserts_have_one_winner(client):
    event = normalize(payload()['event'], 'aws_cloudtrail')

    def insert(_):
        with event_store.transaction():
            return event_store.insert_event(event)

    with ThreadPoolExecutor(max_workers=6) as pool:
        inserted = list(pool.map(insert, range(12)))
    assert inserted.count(True) == 1
    assert event_store.get_total_event_count('retry-test') == 1


def test_receipt_excludes_raw_payload(client):
    event = payload()
    event['event']['extra'] = 'fake-sensitive-marker'
    assert client.post('/ingest', json=event).status_code == 200
    with event_store._db() as con:
        stored = dict(con.execute('SELECT pipeline_result, payload_digest FROM events').fetchone())
    assert 'fake-sensitive-marker' not in stored['pipeline_result']
    assert 'raw' not in json.loads(stored['pipeline_result'])
    assert len(stored['payload_digest']) == 64
