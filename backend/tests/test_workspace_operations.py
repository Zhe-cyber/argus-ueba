import json
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from backend import alert_store
from workspace_next import operations
from backend.tests.test_case_workspace import db, create, seed


def test_missing_receipt_never_implies_healthy_collection(db):
    seed()
    result=operations.connections()
    assert result['mode']=='snapshot_unavailable'
    assert result['sources'][0]['event_count']==1
    assert result['sources'][0]['collector']['status']=='unavailable'
    assert result['coverage']=='observed_activity_only_completeness_unknown'


def test_snapshot_is_bounded_sanitized_and_labels_its_capture(tmp_path):
    path=tmp_path/'snapshot.json'
    path.write_text(json.dumps({'captured_at':'2026-10-31T08:00:00+08:00','sources':{
        'aws_cloudtrail':{'collector':{'status':'attention','last_checked_at':'2026-10-31T00:00:00Z',
            'unresolved':2,'missed':-1,'token':'must-not-leak','path':'private'},
            'workload':{'status':'invented','last_checked_at':None}},'azure_ad':{'secret':'not configured'}}}))
    result=operations.read_snapshot(path)
    assert result['captured_at']=='2026-10-31T00:00:00+00:00'
    assert 'azure_ad' not in result['sources']
    check=result['sources']['aws_cloudtrail']['collector']
    assert check=={'status':'attention','last_checked_at':'2026-10-31T00:00:00+00:00','unresolved':2,'age_seconds_at_capture':0}
    assert 'token' not in json.dumps(result) and 'private' not in json.dumps(result)
    path.write_text('x'*65537)
    assert operations.read_snapshot(path)['mode']=='snapshot_unavailable'


def test_overview_keeps_observations_out_of_security_count(db,tmp_path):
    for kind in ['rarity_spike','anomalous_behavior','ae_critical','new_user','legacy']:
        alert_store.create_alert('a',kind,'Low','Example')
    create()
    snapshot=tmp_path/'snapshot.json'
    snapshot.write_text(json.dumps({'captured_at':'2026-10-31T00:00:00Z','sources':{
        'cloudflare_access':{'collector':{'status':'attention','last_checked_at':None},
                             'workload':{'status':'stale','last_checked_at':None}}}}))
    value=operations.overview(snapshot)
    assert value['open_security_findings']==3 and value['open_observations']==1
    assert value['active_cases']==1
    assert value['sources_needing_review_at_capture']==1
    assert value['scoring']=='not_enabled_in_workspace_preview'


def test_activity_latest_is_utc_not_text_sort_and_sources_stay_real(db):
    from backend import event_store
    a,b=seed(),seed('second')
    with event_store._db() as con:
        con.execute('UPDATE events SET timestamp=? WHERE id=?',('2026-10-31T10:00:00+08:00',a))
        con.execute('UPDATE events SET timestamp=? WHERE id=?',('2026-10-31T03:00:00Z',b))
    result=operations.connections()
    assert len(result['sources'])==1
    assert result['sources'][0]['latest_observed_in_scan']=='2026-10-31T03:00:00+00:00'


def test_app_refuses_unmarked_database(db,monkeypatch):
    from workspace_next.app import create_app
    monkeypatch.setenv('ARGUS_WORKSPACE_COPY_DB',str(db))
    with pytest.raises(RuntimeError,match='marker'): create_app()


def test_marked_preview_routes_do_not_require_live_backend(db,monkeypatch,tmp_path):
    import sqlite3
    from workspace_next.app import create_app
    copied=tmp_path/'preview.db'
    with sqlite3.connect(db) as source,sqlite3.connect(copied) as target: source.backup(target)
    (tmp_path/'workspace-copy.json').write_text(json.dumps({'not_live':True,'copy_db':str(copied.resolve())}))
    monkeypatch.setenv('ARGUS_WORKSPACE_COPY_DB',str(copied))
    # Restore global store path after the isolated app factory mutates it.
    from backend import event_store
    monkeypatch.setattr(event_store,'DB_PATH',db)
    from backend.tests.auth_helpers import sign_in
    with TestClient(create_app()) as client:
        assert client.get('/workspace/overview').status_code==401
        sign_in(client,tmp_path/'auth'/'users.json')
        assert client.get('/workspace/connections').json()['mode']=='snapshot_unavailable'
        assert client.get('/workspace/overview').json()['active_cases']==0
        assert client.get('/ingest').status_code==404


def test_outer_activity_window_is_not_a_failure_or_running_claim():
    cfg={'start':'2026-10-31','end':'2026-11-13'}
    def status(at): return operations.activity_window(cfg,datetime.fromisoformat(at))['status']
    assert status('2026-10-30T21:30:00+00:00')=='outside_hours'  # 05:30 MYT
    assert status('2026-10-31T00:00:00+00:00')=='within_hours'  # 08:00 MYT
    assert status('2026-10-31T12:00:00+00:00')=='outside_hours' # 20:00 MYT
    assert status('2026-10-29T21:00:00+00:00')=='not_started'
    assert status('2026-11-14T01:00:00+00:00')=='ended'
    assert operations.activity_window(None,datetime.now().astimezone())['status']=='unavailable'


def test_read_only_daily_history_separates_previous_unknowns(tmp_path):
    import sqlite3
    path=tmp_path/'history.db'
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE actions(day TEXT,status TEXT)')
        con.executemany('INSERT INTO actions VALUES(?,?)',[
            ('2026-10-30','claimed_unknown'),('2026-10-30','missed'),
            ('2026-10-30','missed'),('2026-10-30','provider_verified')])
    before=path.read_bytes()
    result=operations.workload_history(path,'2026-10-31')
    assert result['available']
    assert result['today']=={'unresolved':0,'missed':0,'verified':0,'pending_receipts':0}
    assert result['prior_days']['unresolved']==1 and result['prior_days']['missed']==2
    assert path.read_bytes()==before


def test_historical_annotation_does_not_hide_current_failure(db,tmp_path):
    path=tmp_path/'snapshot.json'
    today={'unresolved':0,'missed':0,'verified':0,'pending_receipts':0}
    value={'captured_at':'2026-10-30T21:30:00Z','sources':{'cloudflare_access':{
        'collector':{'status':'recent','last_checked_at':'2026-10-30T21:29:00Z'},
        'workload':{'status':'attention','last_checked_at':'2026-10-30T21:29:00Z'},
        'latest_run_status':'attention_required',
        'activity_window':{'status':'within_hours','start_date':'2026-10-30','end_date':'2026-11-13'},
        'workload_history':{'available':True,'day':'2026-10-31','today':today,
                            'prior_days':{**today,'unresolved':1,'missed':2}}}}}
    path.write_text(json.dumps(value))
    connections=operations.connections(path)
    assert len(connections['sources'])==1
    source=connections['sources'][0]
    assert source['activity_window']['status']=='outside_hours' # Supplied label is not trusted.
    assert source['workload']['attention_scope']=='historical'
    value['sources']['cloudflare_access']['latest_run_status']='stopped'
    path.write_text(json.dumps(value))
    assert 'attention_scope' not in operations.connections(path)['sources'][0]['workload']


def test_multiple_provider_histories_survive_sanitization(tmp_path):
    period={'unresolved':0,'missed':0,'verified':0,'pending_receipts':0}
    sources={key:{'workload_history':{'available':True,'day':'2026-10-31','today':period,'prior_days':period}}
             for key in operations.PROVIDERS}
    path=tmp_path/'snapshot.json'
    path.write_text(json.dumps({'captured_at':'2026-10-30T21:30:00Z','sources':sources}))
    parsed=operations.read_snapshot(path)
    assert set(parsed['sources'])==set(operations.PROVIDERS)
    assert all(row['workload_history']['available'] for row in parsed['sources'].values())
