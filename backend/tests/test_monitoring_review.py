"""Local SQLite workflow checks; no live data or cloud access."""
from backend import alert_store, investigations
from backend.tests.test_live_mode import live_client, cloud_event


def test_overview_reports_observed_sources_without_health_claim(live_client):
    live_client.post('/ingest', json=cloud_event())
    result = live_client.get('/monitoring/overview').json()
    assert result['coverage'] == 'observed_events_completeness_unknown'
    source = result['sources'][0]
    assert source['source'] == 'aws_cloudtrail'
    assert source['event_count'] == 1
    assert source['account_references'] == 1
    assert 'healthy' not in source


def test_local_collector_receipts_require_explicit_runtime_context(live_client, monkeypatch):
    from backend import main, collector_status
    monkeypatch.delattr(main.app.state, 'collector_receipts', raising=False)
    monkeypatch.setattr(collector_status, 'summaries', lambda *_: (_ for _ in ()).throw(AssertionError('Local pilot files read without opt-in')))
    assert live_client.get('/monitoring/overview').json()['collector_status'] == {}


def test_overview_distinguishes_rules_observations_and_models(live_client):
    for kind in ['rarity_spike', 'anomalous_behavior', 'new_user', 'ae_critical', 'legacy']:
        alert_store.create_alert('a', kind, 'Low', 'test')
    result = live_client.get('/monitoring/overview').json()
    assert result['active_alerts_by_origin'] == {'rule': 2, 'observation': 1, 'model': 1, 'unverified': 1}


def test_escalation_preserves_notes_owner_and_is_idempotent(live_client):
    investigations.upsert('a', 'Pending', 'Owner', 'Keep this evidence note')
    alert = alert_store.create_alert('a', 'rarity_spike', 'High', 'test')
    url = '/alerts/' + str(alert['id']) + '/escalate'
    first = live_client.post(url)
    assert first.status_code == 200
    record = first.json()['investigation']
    assert record['analyst'] == 'Owner'
    assert record['notes'].startswith('Keep this evidence note\n')
    second = live_client.post(url)
    assert second.json()['investigation'] == record
    assert alert_store.get_alert(alert['id'])['status'] == 'Acknowledged'


def test_escalation_does_not_reopen_closed_alert_or_case(live_client):
    alert = alert_store.create_alert('a', 'rarity_spike', 'High', 'test')
    alert_store.update_status(alert['id'], 'Resolved')
    url = '/alerts/' + str(alert['id']) + '/escalate'
    assert live_client.post(url).status_code == 409
    alert_store.update_status(alert['id'], 'Open')
    investigations.upsert('a', 'Cleared', 'Owner', 'Closed evidence')
    assert live_client.post(url).status_code == 409
    assert investigations.get('a')['notes'] == 'Closed evidence'
    assert alert_store.get_alert(alert['id'])['status'] == 'Open'
