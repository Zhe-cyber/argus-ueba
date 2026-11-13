import copy
import json
import pytest
from backend import account_identity as identity, event_store, investigations, alert_store
from backend.tests.test_live_mode import live_client


def aws(principal='AIDA111', name='alice', namespace='111111111111'):
    return {'source': 'aws_cloudtrail', 'source_account_id': namespace, 'user': name,
            'metadata': {'userIdentity': {'type': 'IAMUser', 'principalId': principal,
                         'userName': name, 'accountId': namespace}}}


def test_same_label_never_links_different_native_principals_or_namespaces():
    first = identity.identify(aws())
    assert first['account_key'] != identity.identify(aws(principal='AIDA222'))['account_key']
    assert first['account_key'] != identity.identify(aws(namespace='222222222222'))['account_key']
    github = {'source': 'github_events', 'source_account_id': '111111111111',
              'user': 'alice', 'metadata': {'actor_id': 123}}
    assert first['account_key'] != identity.identify(github)['account_key']


def test_rename_changes_label_not_key():
    a, b = identity.identify(aws()), identity.identify(aws(name='renamed'))
    assert a['account_key'] == b['account_key']
    assert a['account_label'] != b['account_label']


def test_role_sessions_group_under_issuer_not_session_name():
    a = aws(); native = a['metadata']['userIdentity']; native.update(type='AssumedRole', principalId='AROA111:session-one')
    native['sessionContext'] = {'sessionIssuer': {'type': 'Role', 'principalId': 'AROA111', 'userName': 'reporter'}}
    b = copy.deepcopy(a); b['user'] = 'different'; b['metadata']['userIdentity']['principalId'] = 'AROA111:session-two'
    assert identity.identify(a) == identity.identify(b)
    assert identity.identify(a)['account_kind'] == 'role'


def test_labels_and_missing_namespace_cannot_establish_identity():
    assert identity.identify({'source': 'github_events', 'source_account_id': 'repo', 'user': 'alice', 'metadata': {}}) is None
    a = aws(); a['source_account_id'] = ''
    assert identity.identify(a) is None
    assert identity.identify({'source': 'github_events', 'source_account_id': 'repo', 'metadata': {'actor_id': True}}) is None


@pytest.fixture
def scoped_client(live_client, monkeypatch):
    monkeypatch.setenv('ARGUS_ACCOUNT_KEYS', 'source-principal-v1')
    from backend import main
    monkeypatch.setattr(main.cloud_ae_scorer, 'score_user', lambda *_: None)
    yield live_client


def body(namespace='111111111111', principal='AIDA111', native='event1', label='alice'):
    return {'source': 'aws_cloudtrail', 'source_account_id': namespace,
            'event': {'eventID': native, 'eventTime': '2026-10-30T02:00:00Z',
                      'recipientAccountId': namespace, 'userIdentity': aws(principal, label, namespace)['metadata']['userIdentity'],
                      'eventName': 'ListBuckets', 'eventSource': 's3.amazonaws.com'}}


def test_scoped_http_history_scores_and_legacy_ambiguity(scoped_client):
    a = scoped_client.post('/ingest', json=body()).json()
    b = scoped_client.post('/ingest', json=body('222222222222', 'AIDA222', 'event2')).json()
    assert a['account_key'] != b['account_key']
    assert a['rarity_flags']['first_time_action'] and b['rarity_flags']['first_time_action']
    assert a['total_events'] == b['total_events'] == 1
    users = scoped_client.get('/users').json()['users']
    assert len(users) == 2 and all(u['display_name'] == 'alice' for u in users)
    for key in [a['account_key'], b['account_key']]:
        assert scoped_client.get('/users/' + key).status_code == 200
        assert len(scoped_client.get('/users/' + key + '/events').json()) == 1
    assert scoped_client.get('/users/alice').status_code == 409
    assert scoped_client.get('/stats').json()['unscored_users'] == 2


def test_rename_preserves_history_and_duplicate_receipt(scoped_client):
    a = scoped_client.post('/ingest', json=body()).json()
    b = scoped_client.post('/ingest', json=body(native='event2', label='renamed')).json()
    assert a['account_key'] == b['account_key']
    assert b['total_events'] == 2 and not b['rarity_flags']['first_time_action']
    duplicate = scoped_client.post('/ingest', json=body()).json()
    assert duplicate['duplicate'] is True and duplicate['account_key'] == a['account_key']
    assert scoped_client.get('/users').json()['users'][0]['display_name'] == 'renamed'


def test_missing_native_identity_preserves_event_without_fake_account(scoped_client):
    data = body(); data['event']['userIdentity'] = {'userName': 'unknown'}
    result = scoped_client.post('/ingest', json=data).json()
    assert result['identity_status'] == 'unattributed' and result['ae_live_score'] is None
    assert scoped_client.get('/users').json()['total'] == 0
    assert event_store.get_total_event_count('unknown') == 1


def test_additive_backfill_preserves_native_event_fields(live_client):
    live_client.post('/ingest', json=body())
    with event_store._db() as con:
        cur = event_store._cursor(con)
        cur.execute('UPDATE events SET account_key=NULL, account_label=NULL, account_kind=NULL, account_basis=NULL')
        cur.execute('SELECT * FROM events'); before = event_store._rows(cur)[0]
    assert event_store.backfill_account_keys() == {'updated': 1, 'unattributed': 0}
    assert event_store.backfill_account_keys()['updated'] == 0
    after = event_store.get_user_events_full('alice')[0]
    # Read the physical row: metadata parsing in get_user_events_full is irrelevant.
    with event_store._db() as con:
        cur = event_store._cursor(con); cur.execute('SELECT * FROM events'); after = event_store._rows(cur)[0]
    for field in before:
        if not field.startswith('account_'):
            assert before[field] == after[field]


def test_migration_maps_only_unambiguous_alerts_and_keeps_legacy_reference(live_client):
    from scripts.migrate_account_keys import migrate
    live_client.post('/ingest', json=body())
    alert = alert_store.create_alert('alice', 'rarity_spike', 'High', 'test')
    result = migrate(event_store)
    assert result['native_evidence_unchanged'] is True
    mapped = alert_store.get_alert(alert['id'])
    assert identity.is_key(mapped['user_id'])
    assert mapped['details']['identity_migration_v1']['legacy_user_id'] == 'alice'
    assert migrate(event_store)['alerts_mapped'] == 0


def test_migration_keeps_ambiguous_alerts_and_legacy_cases(live_client):
    from scripts.migrate_account_keys import migrate
    live_client.post('/ingest', json=body())
    live_client.post('/ingest', json=body('222222222222', 'AIDA222', 'event2'))
    alert = alert_store.create_alert('alice', 'rarity_spike', 'High', 'test')
    assert migrate(event_store)['alerts_ambiguous'] >= 1
    assert alert_store.get_alert(alert['id'])['user_id'] == 'alice'
    assert migrate(event_store, legacy_cases=['alice'])['alerts_held_for_legacy_case'] >= 1


def test_unresolved_legacy_alert_cannot_create_mixed_account_case(scoped_client):
    scoped_client.post('/ingest', json=body())
    scoped_client.post('/ingest', json=body('222222222222', 'AIDA222', 'event2'))
    alert = alert_store.create_alert('alice', 'rarity_spike', 'High', 'test')
    assert scoped_client.post('/alerts/' + str(alert['id']) + '/escalate').status_code == 409
    assert investigations.list_all() == []


def test_case_reference_migration_preserves_records_and_refuses_merges(live_client):
    from scripts.migrate_account_keys import migrate_case_references
    live_client.post('/ingest', json=body())
    record = {'analyst': 'Owner', 'notes': 'Keep evidence', 'history': [{'note': 'original'}]}
    revised, mappings = migrate_case_references({'alice': record}, event_store)
    assert len(mappings) == 1 and revised[next(iter(mappings.values()))] == record
    key = next(iter(mappings.values()))
    unchanged, mappings = migrate_case_references({'alice': record, key: {'notes': 'Other case'}}, event_store)
    assert mappings == {} and len(unchanged) == 2
