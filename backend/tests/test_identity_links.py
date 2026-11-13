from datetime import timedelta
from backend import identity_links as links, event_store
from backend.tests.test_account_identity import scoped_client, live_client, body


def github(client, actor=123, label='same@example.com', native='github1'):
    return client.post('/ingest', json={'source': 'github_events', 'source_account_id': 'org/repo',
        'event': {'id': native, 'type': 'PushEvent', 'actor': {'id': actor, 'login': label},
                  'repo': {'name': 'org/repo'}, 'payload': {}, 'created_at': '2026-10-30T03:00:00Z'}}).json()['account_key']


def cloudflare(client):
    return client.post('/ingest', json={'source': 'cloudflare_access', 'source_account_id': 'cf-account',
        'event': {'ray_id': 'cf1', 'user_id': 'native-cf-identity', 'user_email': 'same@example.com',
                  'action': 'login', 'allowed': True, 'app_domain': 'app.example.com',
                  'created_at': '2026-10-30T10:00:00+08:00'}}).json()['account_key']


def person(client, name='Owner'):
    response = client.post('/identities', json={'display_name': name, 'recorded_by': 'Analyst'})
    assert response.status_code == 200
    return response.json()['id']


def approve(client, pid, key, **extra):
    return client.post('/identities/' + pid + '/links', json={'account_key': key,
        'recorded_by': 'Owner', 'evidence': 'Explicit owner confirmation', **extra})


def test_cloudflare_service_token_is_observed_but_not_a_human_link(scoped_client):
    response = scoped_client.post('/ingest', json={'source':'cloudflare_access','source_account_id':'cf-account',
        'event':{'ray_id':'machine-native-ray','connection':'nonidentity','user_id':'',
                 'user_email':'a'*32+'.access','action':'login','allowed':True,
                 'app_domain':'machine.example.test','created_at':'2026-10-30T03:00:00Z'}})
    assert response.status_code == 200
    key = response.json()['account_key']
    assert key in event_store.account_directory()
    assert key not in {a['account_key'] for a in links.available_accounts()}
    assert approve(scoped_client, person(scoped_client), key).status_code == 409


def test_only_approved_native_links_join_without_changing_scores(scoped_client):
    gh, cf = github(scoped_client), cloudflare(scoped_client)
    unrelated = github(scoped_client, actor=999, native='unrelated')
    before = scoped_client.get('/stats').json()
    pid = person(scoped_client)
    assert scoped_client.get('/identities/' + pid + '/timeline').json()['events'] == []
    assert approve(scoped_client, pid, gh).status_code == 200
    assert approve(scoped_client, pid, cf).status_code == 200
    result = scoped_client.get('/identities/' + pid + '/timeline').json()
    assert [row['source'] for row in result['events']] == ['github_events', 'cloudflare_access']
    assert {row['account_key'] for row in result['events']} == {gh, cf}
    assert unrelated not in {row['account_key'] for row in result['events']}
    assert 'aws_cloudtrail' in result['unlinked_sources']
    assert result['score_policy'] == 'per_account_no_person_score'
    assert scoped_client.get('/stats').json() == before


def test_duplicate_approval_is_idempotent_and_other_person_cannot_claim_account(scoped_client):
    key = github(scoped_client); first, second = person(scoped_client), person(scoped_client, 'Other')
    a = approve(scoped_client, first, key).json()
    assert approve(scoped_client, first, key).json() == a
    assert approve(scoped_client, second, key).status_code == 409
    detail = scoped_client.get('/identities/' + first).json()
    assert detail['active_links'] == 1
    assert [entry['action'] for entry in detail['audit']].count('link_approved') == 1


def test_revocation_removes_events_preserves_history_and_allows_reviewed_reassignment(scoped_client):
    key = github(scoped_client); pid = person(scoped_client)
    link = approve(scoped_client, pid, key).json()
    url = '/identities/links/' + link['id'] + '/revoke'
    assert scoped_client.post(url, json={'recorded_by': 'Analyst', 'reason': 'Ownership changed'}).status_code == 200
    assert scoped_client.get('/identities/' + pid + '/timeline').json()['events'] == []
    detail = scoped_client.get('/identities/' + pid).json()
    assert detail['links'][0]['evidence'] == 'Explicit owner confirmation'
    assert detail['links'][0]['effective_status'] == 'revoked'
    assert approve(scoped_client, person(scoped_client, 'Other'), key).status_code == 200


def test_expired_link_excluded_on_read_and_new_approval_is_audited(scoped_client, monkeypatch):
    key = github(scoped_client); pid = person(scoped_client); at = links.now()
    assert approve(scoped_client, pid, key, expires_at=(at + timedelta(hours=1)).isoformat()).status_code == 200
    monkeypatch.setattr(links, 'now', lambda: at + timedelta(hours=2))
    assert scoped_client.get('/identities/' + pid).json()['links'][0]['effective_status'] == 'expired'
    assert scoped_client.get('/identities/' + pid + '/timeline').json()['events'] == []
    assert approve(scoped_client, person(scoped_client, 'Other'), key).status_code == 200
    assert 'link_expired' in [row['action'] for row in scoped_client.get('/identities/' + pid).json()['audit']]


def test_missing_account_does_not_turn_into_another_matching_label(scoped_client):
    key = github(scoped_client); pid = person(scoped_client); approve(scoped_client, pid, key)
    event_store.delete_event_store_user(key)
    github(scoped_client, actor=999, native='replacement')
    assert scoped_client.get('/identities/' + pid + '/timeline').json()['events'] == []
    assert scoped_client.get('/identities/' + pid).json()['links'][0]['effective_status'] == 'missing_account'


def test_no_aws_root_role_or_implicit_pending_approval(scoped_client):
    key = scoped_client.post('/ingest', json=body()).json()['account_key']
    pid = person(scoped_client)
    assert approve(scoped_client, pid, key).status_code == 409
    gh = github(scoped_client)
    assert approve(scoped_client, pid, gh, status='pending').status_code == 422
    assert approve(scoped_client, pid, gh, recorded_by=' ').status_code == 409
    assert scoped_client.get('/identities/' + pid).json()['active_links'] == 0
