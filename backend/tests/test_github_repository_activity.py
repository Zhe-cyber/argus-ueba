import copy

import pytest

from backend.github_activity import normalize_activity
from backend.account_identity import identify
from backend.normalizer import normalize
from backend.tests.test_live_mode import live_client


def activity():
    return {'id': 123, 'actor': {'id': 77, 'login': 'lab[bot]', 'type': 'Bot'},
            'activity_type': 'push', 'timestamp': '2026-10-30T01:00:00Z',
            'before': '0'*40, 'after': 'a'*40, 'ref': 'refs/heads/main'}


def body():
    return {'source_account_id': 'github-owner:99', 'repository': 'owner/toy',
            'repository_id': 5, 'event': activity()}


def test_activity_identity_shared_with_native_actor_but_receipt_ids_separate():
    raw=activity(); preserved=copy.deepcopy(raw)
    row=normalize_activity(raw,'owner/toy',5);row['source_account_id']='github-owner:99'
    event=normalize({'id':'123','type':'PushEvent','created_at':raw['timestamp'],
                     'actor':raw['actor'],'repo':{'name':'owner/toy'},'payload':{}},'github_events')
    event['source_account_id']='github-owner:99'
    assert identify(row)['account_key']==identify(event)['account_key']
    assert row['event_id']=='repository-activity:5:123' and row['event_id']!=event['event_id']
    assert row['raw']==raw==preserved
    assert row['resource']=='owner/toy' and row['ip_address']==''
    assert row['metadata']['evidence_format']=='github_repository_activity_v1'
    assert 'commits' not in row['metadata'] and row['action']=='Repository push'


@pytest.mark.parametrize('patch',[{'id':True},{'actor':{}},{'timestamp':'2026-10-30T01:00:00'},
    {'after':'not-a-commit'},{'activity_type':'unexpected'},{'ref':'main'}])
def test_malformed_activity_rejected(patch):
    with pytest.raises(ValueError):normalize_activity({**activity(),**patch},'owner/toy',5)


def test_activity_endpoint_receipts_retry_conflicts_and_no_fake_scores(live_client,monkeypatch):
    from backend import main
    monkeypatch.setenv('ARGUS_ACCOUNT_KEYS','source-principal-v1')
    monkeypatch.setattr(main.cloud_ae_scorer,'score_user',lambda *_:None)
    url='/ingest/github-repository-activity'
    first=live_client.post(url,json=body());assert first.status_code==200,first.text
    result=first.json();assert result['duplicate'] is False
    assert result['event_id']=='repository-activity:5:123'
    assert result['raw']==body()['event'] and result['ae_live_score'] is None
    second=live_client.post(url,json=body());assert second.json()['duplicate'] is True
    changed=body();changed['event']['after']='b'*40
    assert live_client.post(url,json=changed).status_code==409
    users=live_client.get('/users').json()['users'];assert len(users)==1
    assert users[0]['risk_level']=='Unknown'
    events=live_client.get('/users/'+users[0]['user']+'/events').json()
    assert len(events)==1 and events[0]['resource']=='owner/toy'


def test_activity_request_rejects_invalid_repository_context(live_client):
    for field,value in [('repository_id',True),('repository','../toy'),('source_account_id','wrong')]:
        request=body();request[field]=value
        assert live_client.post('/ingest/github-repository-activity',json=request).status_code==422
