import pytest
from backend import alert_store, event_store, identity_links
from workspace_next import case_store as cases, queries
from backend.tests.test_case_workspace import db, client, create, seed


def test_server_filters_reach_beyond_old_100_row_limit(client):
    first=alert_store.create_alert('old-account','rarity_spike','High','Older security finding')
    for i in range(120): alert_store.create_alert('new-account','new_user','Low',str(i))
    rows=client.get('/findings?category=security').json()
    assert [row['id'] for row in rows['findings']]==[first['id']]
    observed=client.get('/findings?category=observation&limit=100').json()
    assert len(observed['findings'])==100 and observed['has_more']
    cursor=observed['next_cursor']
    remaining=client.get('/findings',params={'category':'observation','limit':100,'before_time':cursor[0],'before_id':cursor[1]}).json()
    assert len(remaining['findings'])==20 and not remaining['has_more']


def test_native_namespace_and_utc_timeline_filters(client):
    a,b=seed(),seed('github-account','github_events')
    row=create()
    row=cases.link(row['id'],1,'Reviewer','a','account','account-aws','AWS context')
    cases.link(row['id'],row['version'],'Reviewer','b','account','github-account','GitHub context')
    with event_store._db() as con:
        con.execute('UPDATE events SET timestamp=? WHERE id=?',('2026-10-30T09:30:00+08:00',a))
        con.execute('UPDATE events SET timestamp=? WHERE id=?',('2026-10-30T01:00:00Z',b))
    result=client.get('/cases/'+row['id']+'/timeline').json()
    assert [r['id'] for r in result['events']]==[a,b]
    assert all(r['evidence_relation']=='related_account_activity' for r in result['events'])
    assert {r['source'] for r in result['events']}=={'aws_cloudtrail','github_events'}
    filtered=client.get('/cases/'+row['id']+'/timeline',params={'start':'2026-10-30T01:15:00Z','end':'2026-10-30T01:31:00Z'}).json()
    assert [r['id'] for r in filtered['events']]==[a]
    assert client.get('/cases/'+row['id']+'/timeline?start=not-a-date').status_code==422


def test_invalid_timestamps_and_scan_cap_are_visible(client,monkeypatch):
    ids=[seed('account-'+str(i)) for i in range(4)]
    row=create()
    for i,event_id in enumerate(ids): row=cases.link(row['id'],row['version'],'Analyst','e'+str(i),'event',str(event_id),'Evidence')
    with event_store._db() as con: con.execute('UPDATE events SET timestamp=? WHERE id=?',('bad',ids[-1]))
    monkeypatch.setattr(queries,'SCAN_LIMIT',3)
    result=client.get('/cases/'+row['id']+'/timeline').json()
    assert result['scan_capped'] and result['invalid_timestamps']==1
    assert len(result['events'])==2


def test_atomic_finding_case_creation_retry_and_mismatched_scope(client):
    seed()
    finding=alert_store.create_alert('account-aws','rarity_spike','High','Investigate')
    body={'actor':'Analyst','owner':'Owner','title':'Case','request_key':'from-finding',
          'finding_id':finding['id'],'include_account':True,'reason':'Review evidence'}
    first=client.post('/cases/from-finding',json=body)
    assert first.status_code==201
    assert len(first.json()['links'])==2
    assert client.post('/cases/from-finding',json=body).json()==first.json()
    assert client.post('/cases/from-finding',json={**body,'include_account':False}).status_code==409
    assert alert_store.get_alert(finding['id'])['status']=='Open'
    assert client.post('/cases/from-finding',json={**body,'request_key':'bad','finding_id':9999}).status_code==404
    assert len(cases.list_cases()['cases'])==1


def test_missing_account_does_not_leave_orphan_case(client):
    finding=alert_store.create_alert('unattributed','rarity_spike','High','Legacy finding')
    body={'actor':'Analyst','title':'Case','request_key':'missing-scope','finding_id':finding['id'],
          'include_account':True,'reason':'Related context'}
    assert client.post('/cases/from-finding',json=body).status_code==404
    assert cases.list_cases()['cases']==[]


def test_mapping_revocation_preserves_historical_case_scope(client,monkeypatch):
    seed('gh','github_events')
    current={'id':'mapping-1','account_key':'gh','effective_status':'approved',
             'account':{'source':'github_events'},'approved_by':'Analyst','evidence':'Verified ownership'}
    monkeypatch.setattr(identity_links,'person_view',lambda _: {'display_name':'Person','links':[current]})
    row=create()
    row=cases.link(row['id'],1,'Analyst','person','person','person-1','Approved linked accounts')
    current['effective_status']='revoked'
    result=client.get('/cases/'+row['id']+'/timeline').json()
    assert len(result['events'])==1
    assert result['mapping_provenance'][0]['current_status']=='revoked'
    assert row['links'][0]['snapshot']['approved_links'][0]['effective_status']=='approved'
