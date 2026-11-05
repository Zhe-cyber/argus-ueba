import pytest
from scripts import github_lab_workload as lab


def test_native_bot_attribution_is_not_commit_author_name():
    data = {'sha':'abc','author':{'type':'Bot','id':77,'login':'argus-workload-lab-test[bot]'}}
    assert lab.check_commit(data,'abc','argus-workload-lab-test') == 77
    for patch in [{'sha':'different'}, {'author':{'type':'User','id':77,'login':'argus-workload-lab-test[bot]'}},
                  {'author':{'type':'Bot','id':77,'login':'other[bot]'}}]:
        with pytest.raises(ValueError):
            lab.check_commit({**data, **patch},'abc','argus-workload-lab-test')


def test_event_matching_needs_native_repo_actor_and_commit():
    receipt = {'repo_id':5,'bot_actor_id':7,'commit_sha':'abc'}
    event = {'id':'native','type':'PushEvent','repo':{'id':5},'actor':{'id':7},'payload':{'head':'abc'}}
    assert lab.matches(event,receipt)
    assert not lab.matches({**event,'repo':{'id':6}},receipt)
    assert not lab.matches({**event,'actor':{'id':8}},receipt)
    assert not lab.matches({**event,'payload':{'head':'other'}},receipt)
    assert not lab.matches({**event,'type':'CreateEvent'},receipt)
    assert lab.matches({**event,'payload':{'commits':[{'sha':'abc'}]}},receipt)


def test_existing_claim_blocks_repeat_before_network(tmp_path, monkeypatch):
    claim=tmp_path/'commission.json';claim.write_text('{"status":"claimed_unknown"}')
    monkeypatch.setattr(lab,'RECEIPT',claim)
    monkeypatch.setattr(lab,'context',lambda:pytest.fail('No network call permitted'))
    with pytest.raises(ValueError):
        lab.commission()


def test_reconcile_waits_for_real_event_and_preserves_provider_payload(tmp_path,monkeypatch):
    claim=tmp_path/'commissioning.json'
    receipt={'status':'commit_verified_event_pending','repo_id':5,'repo':lab.app.REPO,
             'bot_actor_id':7,'commit_sha':'abc'}
    import json
    claim.write_text(json.dumps(receipt))
    monkeypatch.setattr(lab,'RECEIPT',claim)
    monkeypatch.setattr(lab.app,'STATE_DIR',tmp_path)
    monkeypatch.setattr(lab,'context',lambda:({'repo_id':5},'token'))
    events=[];posts=[]
    def api(method,path,token=None,body=None):
        return events if path.endswith('/activity') else {'owner':{'id':99},'id':5,'full_name':lab.app.REPO,'private':True}
    monkeypatch.setattr(lab.app,'api',api)
    class Backend:
        def __init__(self,url):assert url=='http://127.0.0.1:8013'
        def preflight(self):pass
        def post_github_activity(self,*args):posts.append(args);return False
    monkeypatch.setattr(lab,'LocalBackend',Backend)
    assert lab.reconcile()['status']=='awaiting_native_activity'
    assert posts==[]
    event={'id':123,'activity_type':'push','actor':{'id':7},
           'after':'abc','timestamp':'2026-10-30T01:00:00Z'}
    events.append(event)
    assert lab.reconcile()['status']=='ingested'
    assert posts==[('github-owner:99',lab.app.REPO,5,event)]
    saved=json.loads(claim.read_text())
    assert saved['event_timestamp']==event['timestamp']
    assert saved['event_id']=='repository-activity:5:123'
    assert saved['collection_authority']=='repository_activity_only'
    assert len(list((tmp_path/'native-activity').glob('*.json')))==1
    monkeypatch.setattr(lab.app,'api',lambda *args:pytest.fail('No second poll after receipt'))
    assert lab.reconcile()['new_events']==0


def test_native_activity_requires_actor_commit_and_kind():
    receipt={'bot_actor_id':7,'commit_sha':'abc'}
    event={'actor':{'id':7},'activity_type':'push','after':'abc'}
    assert lab.matches_activity(event,receipt)
    for patch in [{'actor':{'id':8}},{'after':'other'},{'activity_type':'force_push'}]:
        assert not lab.matches_activity({**event,**patch},receipt)
