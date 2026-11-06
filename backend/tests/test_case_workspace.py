"""Isolated case lifecycle, retries, concurrency and migration tests."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend import event_store as events, alert_store
from workspace_next import case_store as cases
from workspace_next.case_api import router


@pytest.fixture
def db(monkeypatch,tmp_path):
    assert not events._PG, 'Run these isolated tests with DATABASE_URL=sqlite-local'
    monkeypatch.setattr(events,'DB_PATH',tmp_path/'events.db')
    events.init_db(); alert_store.init_alerts_db(); cases.init_db()
    return events.DB_PATH


@pytest.fixture
def client(db):
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as client:
        yield client


def create(key='create',**kwargs):
    return cases.create('Suspicious activity','Analyst','Analyst',key,**kwargs)


def seed(account='account-aws',source='aws_cloudtrail'):
    with events._db() as con:
        cur = events._cursor(con)
        cur.execute('''INSERT INTO events ("user",timestamp,source,action,resource,
            ip_address,metadata,ingested_at,event_id,source_account_id,payload_digest,
            account_key,account_label,account_kind,account_basis)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (account,'2026-10-30T01:00:00Z',source,'Read','toy','', '{}',
             '2026-10-30T01:01:00Z','native-'+account,'namespace','digest-'+account,
             account,account,'role','native'))
        return cur.lastrowid


def test_distinct_cases_same_account_and_multi_source_case(db):
    aws,gh = seed(),seed('account-gh','github_events')
    first,second = create(),create('separate-episode')
    assert first['id'] != second['id']
    row=cases.link(first['id'],1,'Analyst','aws','account','account-aws','Related AWS account')
    row=cases.link(first['id'],row['version'],'Analyst','gh','account','account-gh','Related repository activity')
    row=cases.link(first['id'],row['version'],'Analyst','event','event',str(aws),'Selected evidence')
    cases.link(second['id'],1,'Analyst','second','account','account-aws','Separate episode')
    assert len(row['links']) == 3
    assert {r['snapshot']['source'] for r in row['links']} == {'aws_cloudtrail','github_events'}
    assert all(r['snapshot'].get('association','').endswith('not_person_ownership_proof') for r in row['links'] if r['kind']=='account')
    assert row['links'][-1]['snapshot']['payload_digest'] == 'digest-account-aws'
    assert cases.evidence(gh)['representation']=='normalized_event'


def test_retry_after_response_loss_is_exact_and_request_reuse_conflicts(db):
    first=create()
    assert create()==first
    with pytest.raises(cases.CaseConflict):
        create(notes='different')
    changed=cases.update(first['id'],1,'Analyst','edit',{'notes':'Evidence retained'})
    assert cases.update(first['id'],1,'Analyst','edit',{'notes':'Evidence retained'})==changed
    with pytest.raises(cases.CaseConflict):
        cases.update(first['id'],1,'Analyst','other',{'notes':'Stale replacement'})
    assert len(cases.get(first['id'])['history'])==2


def test_two_writers_only_one_wins(db):
    row=create()
    def write(i):
        try:
            cases.update(row['id'],1,'Analyst',f'write-{i}',{'notes':str(i)})
            return 'saved'
        except cases.CaseConflict:
            return 'conflict'
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(write,[1,2]))==['conflict','saved']
    assert cases.get(row['id'])['version']==2


def test_duplicate_association_retains_original_provenance(db):
    row=create(); seed()
    args=(row['id'],1,'Analyst','link','account','account-aws','Original reason')
    first=cases.link(*args)
    assert cases.link(*args)==first
    second=cases.link(row['id'],2,'Analyst','different-request','account','account-aws','Another reason')
    assert len(second['links'])==1
    assert second['links'][0]['reason']=='Original reason'


def test_closing_requires_reason_and_does_not_change_findings(db):
    finding=alert_store.create_alert('account-aws','rarity_spike','High','Rule facts')
    row=create()
    row=cases.link(row['id'],1,'Analyst','link','finding',str(finding['id']),'Review this finding')
    with pytest.raises(ValueError):
        cases.update(row['id'],2,'Analyst','bad-close',{'status':'Closed'})
    changes={'status':'Closed','resolution':'Expected or authorized activity','closing_reason':'Approved maintenance'}
    closed=cases.update(row['id'],2,'Analyst','close',changes)
    assert cases.update(row['id'],2,'Analyst','close',changes)==closed
    assert alert_store.get_alert(finding['id'])['status']=='Open'
    with pytest.raises(cases.CaseConflict):
        cases.update(row['id'],3,'Analyst','reopen',{'status':'In progress'})


def test_bad_link_rolls_back_version_and_audit(db):
    row=create()
    with pytest.raises(cases.CaseNotFound):
        cases.link(row['id'],1,'Analyst','bad','event','999','Unavailable event')
    assert cases.get(row['id'])==row


def test_priority_override_requires_audited_reason(db):
    row=create()
    with pytest.raises(ValueError):
        cases.update(row['id'],1,'Analyst','bad-priority',{'priority':'High'})
    assert cases.get(row['id'])==row
    changed=cases.update(row['id'],1,'Analyst','priority',
                         {'priority':'High','change_reason':'Sensitive account needs urgent review'})
    assert changed['history'][-1]['detail']['change_reason']=='Sensitive account needs urgent review'


def test_legacy_import_preserves_exact_record_and_is_atomic(db):
    original={'status':'Confirmed Insider','analyst':'Owner','notes':'Do not lose',
              'created_at':'old-created','updated_at':'old-updated',
              'history':[{'status':'Cleared','note':'Old reasoning'}],'ai_suggestion':'Legacy text'}
    rows=cases.import_legacy({'old-account':original},'legacy-json-v1')
    assert rows[0]['legacy']['record']==original
    assert rows[0]['notes']==original['notes'] and rows[0]['owner']=='Owner'
    assert rows[0]['status']=='New' and rows[0]['resolution'] is None
    assert cases.import_legacy({'old-account':original},'legacy-json-v1')==rows
    before=cases.list_cases()
    with pytest.raises(ValueError):
        cases.import_legacy({'a-valid':original,'z-invalid':{'history':'broken'}},'broken-import')
    assert cases.list_cases()==before
    with pytest.raises(cases.CaseConflict):
        cases.import_legacy({'old-account':{**original,'notes':'changed'}},'legacy-json-v1')


def test_pagination_no_loss_at_equal_timestamps(db):
    for i in range(7): create(str(i))
    with events._db() as con:
        con.execute("UPDATE analyst_cases SET updated_at='2026-10-30T00:00:00+00:00'")
    seen=[]; cursor=None
    while True:
        page=cases.list_cases(2,cursor)
        seen.extend(row['id'] for row in page['cases'])
        if not page['has_more']: break
        cursor=page['next_cursor']
    assert len(seen)==len(set(seen))==7


def test_api_lifecycle_and_error_contract(client):
    body={'title':'Review activity','owner':'Owner','actor':'Analyst','request_key':'api'}
    response=client.post('/cases',json=body)
    assert response.status_code==201
    row=response.json()
    assert client.get('/cases/'+row['id']).json()==row
    edit={'actor':'Analyst','request_key':'edit','expected_version':1,'changes':{'notes':'Reviewed'}}
    assert client.patch('/cases/'+row['id'],json=edit).status_code==200
    assert client.patch('/cases/'+row['id'],json={**edit,'request_key':'stale'}).status_code==409
    assert client.get('/cases/missing').status_code==404
    assert client.get('/events/999').status_code==404
    assert client.get('/cases?before_id=missing').status_code==422
    assert client.post('/cases',json={**body,'legacy':{}}).status_code==422
    assert client.patch('/cases/'+row['id'],json={**edit,'changes':{'status':'Confirmed Insider'}}).status_code==422


def test_sqlite_backup_import_restore_on_copy(db,tmp_path,monkeypatch):
    seed(); finding=alert_store.create_alert('account-aws','rarity_spike','High','Rule facts')
    source_bytes=db.read_bytes()
    backup=tmp_path/'backup.db'; working=tmp_path/'working.db'
    with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)
    with sqlite3.connect(backup) as src,sqlite3.connect(working) as dst:
        src.backup(dst)
    monkeypatch.setattr(events,'DB_PATH',working)
    imported=cases.import_legacy({'old':{'notes':'Original note','analyst':'Owner','history':[]}},'rehearsal')
    assert len(imported)==1
    with sqlite3.connect(working) as con:
        assert con.execute('SELECT COUNT(*) FROM events').fetchone()[0]==1
        assert con.execute('SELECT status FROM alerts WHERE id=?',(finding['id'],)).fetchone()[0]=='Open'
    with sqlite3.connect(backup) as src,sqlite3.connect(working) as dst:
        src.backup(dst)
    assert cases.list_cases()['cases']==[]
    assert db.read_bytes()==source_bytes
