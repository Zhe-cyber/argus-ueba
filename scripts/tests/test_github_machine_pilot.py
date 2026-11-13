from contextlib import nullcontext
from datetime import datetime,timedelta
import hashlib
import json

import pytest

from scripts import github_machine_pilot as p


@pytest.fixture
def configured(tmp_path,monkeypatch):
    monkeypatch.setattr(p.app,'STATE_DIR',tmp_path)
    proof=tmp_path/'commissioning.json';proof.write_text('{}');monkeypatch.setattr(p.lab,'RECEIPT',proof)
    cfg={'schema':'github_controlled_machine_pilot_v1','repo':p.app.REPO,'repo_id':5,'bot_actor_id':7,
         'owner_namespace':'github-owner:99','slug':'test-app','installation_id':10,
         'start':p.START,'end':p.END,'reconcile_end':p.RECONCILE_END,'max_writes_day':6,'max_writes_pilot':84,
         'model_activated':False,'commission_sha256':hashlib.sha256(proof.read_bytes()).hexdigest(),'source_sha256':p.pins()}
    cfg['scope_sha256']=p.digest({k:v for k,v in cfg.items() if k!='source_sha256'})
    p.validate(cfg)
    with p.database() as db:p.bind_scope(db,cfg)
    return cfg


def test_finite_deterministic_plan_limits_and_paths():
    allslots=[]
    day=datetime.fromisoformat(p.START).date()
    while day.isoformat()<=p.END:
        slots=p.plan(day.isoformat());assert slots==p.plan(day.isoformat()) and 2<=len(slots)<=6
        assert len({s['profile'] for s in slots})==len(slots)
        for s in slots:
            due,until=map(datetime.fromisoformat,[s['due'],s['until']])
            assert due.utcoffset().total_seconds()==28800 and 8<=due.hour<20
            assert until-due==timedelta(minutes=45)
            assert s['path']==f"workloads/{s['profile']}/{s['day']}.json"
        allslots+=slots;day+=timedelta(days=1)
    assert len(allslots)<=84 and len({s['id'] for s in allslots})==len(allslots)
    assert p.plan('2026-10-30')==p.plan('2026-11-14')==[]


def test_claim_and_write_once_with_native_sha_saved(configured,monkeypatch):
    slot=p.plan(p.START)[0];now=datetime.fromisoformat(slot['due']);calls=[]
    def api(method,path,token,body):
        with p.database() as db:assert db.execute('SELECT status FROM actions WHERE action_id=?',(slot['id'],)).fetchone()[0]=='claimed_unknown'
        calls.append((method,path,body));return {'commit':{'sha':'a'*40}}
    monkeypatch.setattr(p.app,'api',api)
    assert p.claim(configured,slot,now)=='claimed_unknown'
    p.perform(configured,slot,'test-token')
    assert p.claim(configured,slot,now) is None and len(calls)==1
    assert calls[0][0]=='PUT' and '/contents/workloads/' in calls[0][1] and 'sha' not in calls[0][2]
    with p.database() as db:
        row=db.execute('SELECT status,commit_sha FROM actions').fetchone()
        assert tuple(row)==('api_ok_identity_pending','a'*40)
    with pytest.raises(ValueError):p.perform(configured,slot,'test-token')


def test_unknown_outcome_never_retried_and_blocks_new_writes(configured,monkeypatch):
    slots=p.plan(p.START);first=slots[0];now=datetime.fromisoformat(first['due'])
    assert p.claim(configured,first,now)=='claimed_unknown'
    monkeypatch.setattr(p.app,'api',lambda *args:(_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(TimeoutError):p.perform(configured,first,'token')
    assert p.claim(configured,first,now) is None
    second=slots[1]
    assert p.claim(configured,second,datetime.fromisoformat(second['due'])) is None
    assert p.claim(configured,second,datetime.fromisoformat(second['until']))=='missed'


def test_not_due_missed_and_outside_plan_never_call_provider(configured,monkeypatch):
    slot=p.plan(p.START)[0];due=datetime.fromisoformat(slot['due'])
    assert p.claim(configured,slot,due-timedelta(seconds=1)) is None
    assert p.claim(configured,slot,datetime.fromisoformat(slot['until']))=='missed'
    monkeypatch.setattr(p.app,'api',lambda *args:pytest.fail('Unexpected cloud write'))
    with pytest.raises(ValueError):p.perform(configured,slot,'token')
    with pytest.raises(ValueError):p.perform(configured,{**slot,'path':'outside.json'},'token')


def test_reconcile_exact_identity_activity_and_duplicate_receipt(configured,monkeypatch):
    slot=p.plan(p.START)[0];now=datetime.fromisoformat(slot['due']);p.claim(configured,slot,now)
    with p.database() as db:db.execute("UPDATE actions SET status='api_ok_identity_pending',commit_sha=?",('a'*40,))
    native={'id':123,'activity_type':'push','actor':{'id':7},'after':'a'*40,'timestamp':now.isoformat()}
    def api(method,path,token):
        if path.endswith('/activity'):return [native]
        return {'sha':'a'*40,'author':{'type':'Bot','id':7,'login':'test-app[bot]'}}
    monkeypatch.setattr(p.app,'api',api)
    class Backend:
        def post_github_activity(self,*args):assert args[-1] is native;return True
    result=p.reconcile(configured,'token',Backend(),now)
    assert result['newly_provider_verified']==1 and result['inserted']==0
    assert p.reconcile(configured,'token',Backend(),now)['newly_provider_verified']==0
    assert len(list((p.state()/'native-activity').glob('*.json')))==1


def test_no_native_evidence_or_receipt_never_becomes_verified(configured,monkeypatch):
    slot=p.plan(p.START)[0];now=datetime.fromisoformat(slot['due']);p.claim(configured,slot,now)
    with p.database() as db:db.execute("UPDATE actions SET status='api_ok_activity_pending',commit_sha=?",('a'*40,))
    monkeypatch.setattr(p.app,'api',lambda *args:[])
    backend=type('Backend',(),{'post_github_activity':lambda *args:pytest.fail('No matching evidence')})()
    assert p.reconcile(configured,'token',backend,now)['newly_provider_verified']==0
    native={'id':123,'activity_type':'push','actor':{'id':7},'after':'a'*40}
    monkeypatch.setattr(p.app,'api',lambda *args:[native])
    backend.post_github_activity=lambda *args:None
    assert p.reconcile(configured,'token',backend,now)['newly_provider_verified']==0
    with p.database() as db:assert db.execute('SELECT status FROM actions').fetchone()[0]=='api_ok_activity_pending'


def test_config_and_ledger_scope_changes_fail_closed(configured):
    bad=json.loads(json.dumps(configured));bad['source_sha256']['scripts/github_machine_pilot.py']='changed'
    with pytest.raises(ValueError):p.validate(bad)
    bad=json.loads(json.dumps(configured));bad['max_writes_day']=99
    with pytest.raises(ValueError):p.validate(bad)
    with p.database() as db:
        with pytest.raises(ValueError):p.bind_scope(db,{**configured,'scope_sha256':'different'})


def test_expiry_does_no_backend_or_provider_work(monkeypatch):
    monkeypatch.setattr(p,'LocalBackend',lambda *_:pytest.fail('Expired access'))
    assert p.tick(datetime.fromisoformat('2026-11-15T00:00:00+08:00'))['status']=='expired'


def test_activity_cap_and_raw_archive_conflict_are_visible(configured,monkeypatch):
    monkeypatch.setattr(p.app,'api',lambda *args:[{}]*30)
    assert p.reconcile(configured,'token',None,datetime.now(p.MY))['activity_cap_hit'] is True
    raw={'id':1};p.archive_activity(raw)
    next((p.state()/'native-activity').iterdir()).write_bytes(b'corrupt')
    with pytest.raises(ValueError):p.archive_activity(raw)


def test_journal_keeps_failure_after_later_success(configured):
    p.journal({'status':'stopped_review_required','error_type':'TimeoutError'})
    p.journal({'status':'completed'})
    assert json.loads((p.state()/'last-pilot-status.json').read_bytes())['status']=='completed'
    lines=(p.state()/'pilot-attempts.jsonl').read_text().splitlines()
    assert len(lines)==2 and json.loads(lines[0])['error_type']=='TimeoutError'


@pytest.mark.parametrize('which,count',[('day',6),('pilot',84)])
def test_budget_exhaustion_prevents_another_claim(configured,which,count):
    slot=p.plan(p.START)[0]
    with p.database() as db:
        for i in range(count):
            db.execute('INSERT INTO actions(action_id,day,status) VALUES(?,?,?)',
                       (f'existing-{i}',slot['day'] if which=='day' else '2026-10-01','provider_verified'))
    with pytest.raises(ValueError,match='write cap'):
        p.claim(configured,slot,datetime.fromisoformat(slot['due']))
    with p.database() as db:assert db.execute('SELECT COUNT(*) FROM actions WHERE action_id=?',(slot['id'],)).fetchone()[0]==0
