from datetime import datetime, timedelta, timezone
import json

import pytest

from backend import collector_status as s

NOW = datetime(2026,10,30,10,0,tzinfo=timezone.utc)


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value))


def test_missing_bad_and_oversized_receipts_never_infer_health(tmp_path):
    assert s.snapshot(None,NOW,900)['status']=='unavailable'
    path=tmp_path/'status.json';path.write_text('{bad json')
    assert s.read_status(path) is None
    path.write_bytes(b'x'*(s.MAX_STATUS_BYTES+1));assert s.read_status(path) is None
    assert s.read_status(tmp_path/'missing.json') is None


@pytest.mark.parametrize('timestamp',[None,'bad','2026-10-30T10:00:00',(NOW+timedelta(minutes=2)).isoformat()])
def test_invalid_or_future_time_is_not_recent(timestamp):
    assert s.snapshot({'at_utc':timestamp,'status':'completed'},NOW,900)['status']=='unavailable'


def test_unresolved_and_missed_counts_survive_staleness_without_raw_data():
    value={'at_utc':NOW.isoformat(),'status':'completed','action_states':{'claimed_unknown':1,'missed':2},
           'client_secret':'SENSITIVE_SENTINEL','raw':{'account':'SENSITIVE_SENTINEL'}}
    recent=s.snapshot(value,NOW,900)
    assert recent['status']=='attention' and recent['unresolved']==1 and recent['missed']==2
    stale=s.snapshot(value,NOW+timedelta(minutes=16),900)
    assert stale['status']=='stale' and stale['unresolved']==1
    assert 'SENSITIVE_SENTINEL' not in json.dumps(stale)


def test_pending_receipt_is_not_provider_verification_or_error():
    result=s.snapshot({'at_utc':NOW.isoformat(),'status':'completed','action_states':{'api_ok_activity_pending':2}},NOW,900)
    assert result['status']=='recent' and result['pending_receipts']==2 and result['unresolved']==0
    assert 'provider_verified' not in result


def test_provider_collector_and_machine_workload_are_independent(tmp_path):
    connected=tmp_path/'outside/live/connected';root=tmp_path/'source'
    shared={'at_utc':NOW.isoformat(),'status':'completed','phases':{'aws':{'ok':True},'github':{'ok':False},'cloudflare':{'ok':True},'actors':{'ok':True}}}
    write(connected.parent/'pilot-local-v1/last_tick.json',shared)
    write(root/'data/live/cloudflare-workload-lab-v1/last-pilot-status.json',{'at_utc':NOW.isoformat(),'status':'attention_required','action_states':{'claimed_unknown':1}})
    result=s.summaries(connected,root,NOW)
    assert result['cloudflare_access']['collector']['status']=='recent'
    assert result['cloudflare_access']['workload']['status']=='attention'
    assert result['github_events']['collector']['status']=='attention'
    assert result['github_events']['workload']['status']=='unavailable'
    assert result['aws_cloudtrail']['workload']['status']=='recent'


def test_missing_phase_never_inherits_outer_success(tmp_path):
    connected=tmp_path/'live/connected'
    write(connected.parent/'pilot-local-v1/last_tick.json',{'at_utc':NOW.isoformat(),'status':'completed'})
    result=s.summaries(connected,tmp_path,NOW)
    assert all(r['collector']['status']=='unavailable' for r in result.values())


@pytest.mark.parametrize('states',[{'claimed_unknown':True},{'missed':-1},{'raw_secret':1}])
def test_invalid_action_counts_fail_closed(states):
    assert s.snapshot({'at_utc':NOW.isoformat(),'status':'completed','action_states':states},NOW,900)['status']=='unavailable'
