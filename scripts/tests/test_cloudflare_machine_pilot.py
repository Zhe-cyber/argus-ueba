from datetime import datetime
from pathlib import Path
import json
import pytest
from scripts import cloudflare_machine_pilot as p


def test_plan_deterministic_six_bounded_real_time_slots():
    rows=p.plan('2026-10-30');assert len(rows)==6 and rows==p.plan('2026-10-30')
    assert len({r['id'] for r in rows})==6
    for row in rows:
        a,b=map(datetime.fromisoformat,[row['due'],row['until']])
        assert a.utcoffset().total_seconds()==8*3600
        assert 8<=a.hour<b.hour+1<=20 and (b-a).total_seconds()==2700
    assert p.plan('2026-10-29')==p.plan('2026-11-14')==[]
    assert sum(len(p.plan('2026-11-'+str(i).zfill(2))) for i in range(1,14))==78


def test_config_rejects_source_and_scope_changes():
    cfg=p.pin_config({'schema':'cf_controlled_machine_pilot_v1','account':'account','app_id':'app',
                      'host':'argus-machine-lab.test.workers.dev','tokens':{f'persona-{n:02d}':{'id':str(n),'client_id':str(n)+'.access'} for n in range(1,7)},
                      'start':p.START,'end':p.END,'reconcile_end':p.RECONCILE_END,'model_activated':False})
    p.validate(cfg)
    changed=json.loads(json.dumps(cfg));changed['tokens']['persona-01']['id']='other'
    with pytest.raises(ValueError):p.validate(changed)
    changed=json.loads(json.dumps(cfg));changed['source_sha256']['scripts/cloudflare_machine_pilot.py']='different'
    with pytest.raises(ValueError):p.validate(changed)


def fixture_config(tmp_path,monkeypatch):
    monkeypatch.setattr(p.setup,'STATE',tmp_path)
    cfg=p.pin_config({'schema':'cf_controlled_machine_pilot_v1','account':'account','app_id':'app',
                      'host':'argus-machine-lab.test.workers.dev','tokens':{f'persona-{n:02d}':{'id':str(n),'client_id':str(n)+'.access'} for n in range(1,7)},
                      'start':p.START,'end':p.END,'reconcile_end':p.RECONCILE_END,'model_activated':False})
    (tmp_path/'pilot-config.json').write_text(json.dumps(cfg))
    class Backend:
        def __init__(self,url):pass
        def preflight(self):pass
    monkeypatch.setattr(p,'LocalBackend',Backend)
    monkeypatch.setattr(p,'collect',lambda *args:{'inserted':0})
    def load(path):
        n=int(path.stem[-2:]);return {'id':str(n),'client_id':str(n)+'.access','client_secret':'secret'}
    monkeypatch.setattr(p,'load_secret',load)
    return cfg


def test_claim_before_request_no_repeat_and_missed_windows(tmp_path,monkeypatch):
    fixture_config(tmp_path,monkeypatch)
    slots=p.plan('2026-10-30');slot=min(slots,key=lambda r:r['due']);now=datetime.fromisoformat(slot['due'])
    calls=[]
    class Session:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url,**kwargs):
            with p.database() as db:assert db.execute('SELECT status FROM actions WHERE action_id=?',(slot['id'],)).fetchone()[0]=='claimed_unknown'
            assert kwargs['allow_redirects'] is False
            calls.append(url)
            return type('Response',(),{'status_code':200,'headers':{'CF-Ray':'a'*16+'-KUL'},'text':'Argus machine workload: authenticated'})()
    monkeypatch.setattr(p.requests,'Session',Session)
    assert p.tick(now)['new_actions']==1
    assert p.tick(now)['new_actions']==0 and len(calls)==1
    late=datetime.fromisoformat('2026-10-30T20:30:00+08:00')
    result=p.tick(late)
    assert result['new_actions']==0 and result['action_states']['missed']==5


def test_timeout_claim_never_retries_and_expired_does_no_provider_work(tmp_path,monkeypatch):
    fixture_config(tmp_path,monkeypatch)
    now=datetime.fromisoformat(min(p.plan('2026-10-30'),key=lambda r:r['due'])['due'])
    calls=[]
    class Session:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,*args,**kwargs):calls.append(1);raise TimeoutError()
    monkeypatch.setattr(p.requests,'Session',Session)
    with pytest.raises(TimeoutError):p.tick(now)
    result=p.tick(now)
    assert result['new_actions']==0 and calls==[1]
    assert result['status']=='completed' and result['action_states']['claimed_unknown']==1
    assert result['historical_unknown']==1 and result['new_unknown']==0
    monkeypatch.setattr(p,'LocalBackend',lambda *args:pytest.fail('No backend/provider work after expiry'))
    assert p.tick(datetime.fromisoformat('2026-11-15T00:00:00+08:00'))['status']=='expired'


def test_old_unknown_is_preserved_while_later_requests_complete(tmp_path,monkeypatch):
    fixture_config(tmp_path,monkeypatch)
    first=min(p.plan('2026-10-30'),key=lambda r:r['due'])
    with p.database() as db:
        db.execute('INSERT INTO actions(action_id,day,persona,status,claimed_at) VALUES(?,?,?,?,?)',
                   (first['id'],first['day'],first['persona'],'claimed_unknown',first['due']))
    calls=[]
    class Session:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url,**kwargs):
            calls.append(url)
            return type('Response',(),{'status_code':200,'headers':{'CF-Ray':'b'*16+'-KUL'},
                                      'text':'Argus machine workload: authenticated'})()
    monkeypatch.setattr(p.requests,'Session',Session)
    slot=min(p.plan('2026-10-31'),key=lambda r:r['due'])
    result=p.tick(datetime.fromisoformat(slot['due']))
    assert result['status']=='completed' and result['new_actions']==1
    assert result['historical_unknown']==1 and result['action_states']['claimed_unknown']==1
    assert len(calls)==1 and slot['id'][:24] in calls[0]
    with p.database() as db:
        old=db.execute('SELECT status,ray_id,http_status,verified_at FROM actions WHERE action_id=?',(first['id'],)).fetchone()
    assert old==('claimed_unknown',None,None,None)


def test_journal_preserves_failure_when_latest_status_changes(tmp_path,monkeypatch):
    monkeypatch.setattr(p.setup,'STATE',tmp_path)
    p.journal({'status':'stopped','error_type':'TimeoutError'})
    p.journal({'status':'completed'})
    assert json.loads((tmp_path/'last-pilot-status.json').read_bytes())['status']=='completed'
    attempts=[json.loads(line) for line in (tmp_path/'pilot-attempts.jsonl').read_text().splitlines()]
    assert len(attempts)==2 and attempts[0]['error_type']=='TimeoutError'
