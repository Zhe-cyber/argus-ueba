"""Post-pilot persona workloads: fake AWS/Cloudflare, temp ledgers only. No network or real secrets."""
from datetime import date, datetime, timedelta, timezone
import json
import sqlite3

import pytest

from scripts import ops_collect, ops_personas
from scripts import run_persona_history as history
from scripts.tests.test_persona_history import ACCOUNT, STACK, clock, provider  # noqa: F401  shared fakes

MY = timezone(timedelta(hours=8))


def make_config(tmp_path, **personas):
    cfg = {'schema': 'argus_ops_v1', 'backend_url': 'http://127.0.0.1:8020',
           'live_state_dir': str(tmp_path / 'connected'), 'status_dir': str(tmp_path / 'ops'),
           'collect_start_local': '2026-11-17', 'protected_paths': [str(tmp_path / 'pilot')],
           'providers': {'aws': {'enabled': True, 'account_id': ACCOUNT, 'queue_url': 'q', 'batches': 5},
                         'github': {'enabled': False}, 'cloudflare': {'enabled': False}},
           'personas': {'enabled': True, 'start_local': '2026-11-16', 'ledger_dir': str(tmp_path / 'ledger'),
                        'stack': STACK, 'cloudflare': {'enabled': False}, **personas}}
    path = tmp_path / 'ops.json'
    path.write_text(json.dumps(cfg), encoding='utf-8')
    return ops_collect.load_config(path)


def first_due(day):
    plan = ops_personas.plan_for(day)
    return datetime.fromisoformat(plan['actions'][0]['planned_utc'])


def test_plan_for_16_to_30_november_uses_v2_profiles_within_caps():
    ids = set()
    for offset in range(15):
        day = date(2026, 11, 16) + timedelta(days=offset)
        plan = ops_personas.plan_for(day)
        assert plan['schema'] == 'argus_controlled_workload_plan_v2' and plan['date_local'] == day.isoformat()
        assert plan['planned_actions'] + plan['reserved_sdk_calls'] <= history.MAX_RUN_CALLS
        per = {}
        for row in plan['actions']:
            per[row['persona']] = per.get(row['persona'], 0) + 1
            assert row['planned_local'].startswith(day.isoformat())
        assert all(n <= 5 for n in per.values())
        cf = ops_personas.cf_plan(day.isoformat())
        assert len(cf) == 6 and all(item['due'].date() == day for item in cf)
        assert not ids & {item['id'] for item in cf}
        ids |= {item['id'] for item in cf}
    assert sum(ops_personas.plan_for(date(2026, 11, 16) + timedelta(days=d))['planned_actions'] for d in range(15)) > 0


def test_aws_personas_run_after_15_november_on_their_own_ledger(tmp_path, clock, provider):
    cfg = make_config(tmp_path)
    clock.now = first_due(date(2026, 11, 16))
    doc = ops_personas.tick(cfg)
    assert doc['aws']['ok'] and doc['aws']['new_actions'] >= 1, doc
    assert (tmp_path / 'ledger' / 'ledger.db').is_file() and (tmp_path / 'ledger' / 'ops-ledger.json').is_file()
    assert any(name == 'get_caller_identity' for name, _ in provider.calls)
    before = list(provider.calls)
    assert ops_personas.tick(cfg)['aws']['state'] == 'no_due_actions'  # repeat is a no-op
    assert provider.calls == before
    status = json.loads((tmp_path / 'ops' / 'ops-personas-status.json').read_text(encoding='utf-8'))
    assert status['github'] == 'collection_only_no_persona_pushes'
    assert ACCOUNT not in json.dumps(status)


def test_not_started_before_16_november(tmp_path, clock, provider):
    cfg = make_config(tmp_path)
    clock.now = datetime(2026, 11, 15, 15, 59, tzinfo=timezone.utc)  # 23:59 MYT 15 Nov
    assert ops_personas.tick(cfg)['status'] == 'not_started'
    assert provider.calls == [] and not (tmp_path / 'ledger').exists()


def test_failed_attempt_is_never_retried_and_blocks(tmp_path, clock, provider):
    cfg = make_config(tmp_path)
    clock.now = first_due(date(2026, 11, 18))
    provider.fail = True
    (tmp_path / 'ops').mkdir()
    ops_collect.atomic_json(tmp_path / 'ops' / 'ops-status.json',
                            {'providers': {'aws': {'ok': True, 'last_ok_utc': clock.now.isoformat()}}})
    doc = ops_personas.tick(cfg)
    assert doc['aws'] == {'ok': False, 'state': 'stopped', 'error_kind': 'RuntimeError'}
    with sqlite3.connect(tmp_path / 'ledger' / 'ledger.db') as db:
        assert db.execute("SELECT count(*) FROM actions WHERE status='claimed_unknown'").fetchone()[0] >= 1
    provider.fail = False
    calls = len(provider.calls)
    clock.now += timedelta(minutes=1)
    assert ops_personas.tick(cfg)['aws']['state'] == 'blocked_unknown_claims_review_required'
    assert len(provider.calls) == calls


def test_ledger_cap_is_enforced(tmp_path, clock, provider):
    cfg = make_config(tmp_path)
    ledger = ops_personas.guard_ledger(cfg)
    with history.ledger(ledger / 'ledger.db') as db:
        db.execute('INSERT INTO runs VALUES(?,?,?)', ('full', '2026-11-16', history.MAX_PILOT_CALLS))
        db.commit()
    clock.now = first_due(date(2026, 11, 16))
    doc = ops_personas.tick(cfg)
    assert doc['aws']['state'] == 'stopped' and provider.calls == []


def test_actions_wait_for_healthy_collection_after_cutover(tmp_path, clock, provider):
    cfg = make_config(tmp_path)
    clock.now = first_due(date(2026, 11, 19))
    assert ops_personas.tick(cfg)['aws']['state'] == 'blocked_collection_not_ok'
    assert provider.calls == []


def test_refuses_the_pilot_ledger(tmp_path, clock, provider):
    clock.now = first_due(date(2026, 11, 16))
    pilot = make_config(tmp_path, ledger_dir=str(tmp_path / 'elsewhere' / 'persona-history-v1'))
    with pytest.raises(ValueError, match="pilot's ledger"):
        ops_personas.guard_ledger(pilot)
    unmarked = tmp_path / 'copied'
    unmarked.mkdir()
    (unmarked / 'ledger.db').write_bytes(b'')
    with pytest.raises(ValueError, match='not created by ops_personas'):
        ops_personas.guard_ledger(make_config(tmp_path, ledger_dir=str(unmarked)))
    with pytest.raises(ValueError, match='protected'):
        make_config(tmp_path, ledger_dir=str(tmp_path / 'pilot' / 'ledger'))
    assert provider.calls == []


# ---- Cloudflare -------------------------------------------------------------------------------

def cf_config(tmp_path, valid='2026-12-31T00:00:00+00:00'):
    app = 'b' * 8 + '-' + 'c' * 27
    (tmp_path / 'cf').mkdir(exist_ok=True)
    (tmp_path / 'cf' / 'pilot-config.json').write_text(json.dumps({'app_id': app}))  # synthetic machine-lab scope
    cfg = make_config(tmp_path, cloudflare={'enabled': True, 'state_dir': str(tmp_path / 'cf'),
                                            'tokens_valid_until_utc': valid})
    cfg['providers']['cloudflare'] = {'enabled': True, 'account_id': 'a' * 32, 'app_ids': [app]}
    return cfg


class FakeCf:
    def __init__(self, status=200):
        self.calls, self.status = [], status

    def loader(self, state_dir, persona):
        return 'argus-machine-lab.test.workers.dev', 'id-' + persona, 'FAKESECRET'

    def http(self, url, headers):
        self.calls.append(url)
        return self.status, f'{len(self.calls):016x}', self.status == 200


def test_cloudflare_rejected_token_stops_and_is_surfaced(tmp_path):
    cfg = cf_config(tmp_path)
    fake = FakeCf(401)
    ledger = ops_personas.guard_ledger(cfg)
    plan = sorted(ops_personas.cf_plan('2026-11-18'), key=lambda i: i['due'])
    first = ops_personas.run_cloudflare(cfg, ledger, plan[0]['due'] + timedelta(minutes=1), fake.loader, fake.http)
    assert first['state'] == 'token_expired_or_invalid' and len(fake.calls) == 1
    later = ops_personas.run_cloudflare(cfg, ledger, plan[-1]['due'] + timedelta(minutes=1), fake.loader, fake.http)
    assert later['state'] == 'token_expired_or_invalid' and len(fake.calls) == 1
    cfg['personas']['cloudflare']['reviewed_through_utc'] = (plan[-1]['due'] + timedelta(minutes=1)).isoformat()
    fake.status = 200  # owner renewed and reviewed: requests resume on the next window
    assert ops_personas.run_cloudflare(cfg, ledger, plan[-1]['due'] + timedelta(minutes=2), fake.loader, fake.http)['ok']


def test_cloudflare_needs_the_machine_app_in_collection(tmp_path):
    cfg = cf_config(tmp_path)
    cfg['providers']['cloudflare']['app_ids'] = ['d' * 8 + '-' + 'e' * 27]
    assert ops_collect.machine_app_collected(cfg) is False
    result = ops_personas.run_cloudflare(cfg, tmp_path, datetime(2026, 11, 16, 4, tzinfo=timezone.utc), FakeCf().loader, FakeCf().http)
    assert result['state'] == 'blocked_machine_app_not_collected'


def test_persona_start_before_16_november_is_refused(tmp_path):
    with pytest.raises(ValueError, match='2026-11-16'):
        make_config(tmp_path, start_local='2026-11-15')


def test_cloudflare_one_request_per_persona_day_then_capped(tmp_path):
    cfg = cf_config(tmp_path)
    fake = FakeCf()
    ledger = ops_personas.guard_ledger(cfg)
    end_of_day = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)  # 23:00 MYT: all windows passed
    for item in sorted(ops_personas.cf_plan('2026-11-16'), key=lambda i: i['due']):
        result = ops_personas.run_cloudflare(cfg, ledger, item['due'] + timedelta(minutes=1), fake.loader, fake.http)
    assert len(fake.calls) == 6 and result['action_states'] == {'api_ok_log_pending': 6}
    ops_personas.run_cloudflare(cfg, ledger, end_of_day, fake.loader, fake.http)
    assert len(fake.calls) == 6
    with sqlite3.connect(ledger / 'cloudflare-ledger.db') as db:
        assert 'FAKESECRET' not in str(db.execute('SELECT * FROM actions').fetchall())


def test_cloudflare_missed_windows_are_not_backfilled(tmp_path):
    cfg = cf_config(tmp_path)
    fake = FakeCf()
    ledger = ops_personas.guard_ledger(cfg)
    result = ops_personas.run_cloudflare(cfg, ledger, datetime(2026, 11, 16, 15, tzinfo=timezone.utc), fake.loader, fake.http)
    assert fake.calls == [] and result['action_states'] == {'missed': 6}


def test_cloudflare_error_blocks_without_retry(tmp_path):
    cfg = cf_config(tmp_path)
    fake = FakeCf(500)
    ledger = ops_personas.guard_ledger(cfg)
    plan = ops_personas.cf_plan('2026-11-17')
    first = ops_personas.run_cloudflare(cfg, ledger, plan[0]['due'] + timedelta(minutes=1), fake.loader, fake.http)
    assert first['ok'] is False and len(fake.calls) == 1
    later = ops_personas.run_cloudflare(cfg, ledger, max(i['due'] for i in plan) + timedelta(minutes=1), fake.loader, fake.http)
    assert later['state'] == 'blocked_unknown_or_error_review_required' and len(fake.calls) == 1


def test_cloudflare_expired_tokens_send_nothing(tmp_path):
    fake = FakeCf()
    for valid in (None, '2026-11-15T00:00:00+00:00'):
        cfg = cf_config(tmp_path, valid)
        result = ops_personas.run_cloudflare(cfg, tmp_path, datetime(2026, 11, 16, 4, tzinfo=timezone.utc), fake.loader, fake.http)
        assert result['state'] == 'tokens_expired_owner_must_renew'
    assert fake.calls == []


def test_cloudflare_verified_from_the_operational_store(tmp_path):
    cfg = cf_config(tmp_path)
    fake = FakeCf()
    ledger = ops_personas.guard_ledger(cfg)
    item = ops_personas.cf_plan('2026-11-16')[0]
    ops_personas.run_cloudflare(cfg, ledger, item['due'] + timedelta(minutes=1), fake.loader, fake.http)
    cfg['live_state_dir'].mkdir(parents=True)
    with sqlite3.connect(cfg['live_state_dir'] / 'events.db') as db:
        db.execute('CREATE TABLE events(source TEXT, event_id TEXT)')
        db.execute("INSERT INTO events VALUES('cloudflare_access', ?)", (f'{1:016x}',))
    result = ops_personas.run_cloudflare(cfg, ledger, item['due'] + timedelta(minutes=2), fake.loader, fake.http)
    assert result['newly_provider_verified'] == 1


def test_provider_isolation_between_aws_and_cloudflare(tmp_path, clock, provider):
    cfg = cf_config(tmp_path)
    clock.now = (ops_personas.cf_plan('2026-11-16')[0]['due'] + timedelta(minutes=1)).astimezone(timezone.utc)

    def broken_loader(*a):
        raise OSError('dpapi unavailable')

    doc = ops_personas.tick(cfg, cf_loader_fn=broken_loader, cf_http_fn=FakeCf().http)
    assert doc['aws']['ok'] is True and doc['cloudflare'] == {'ok': False, 'state': 'stopped', 'error_kind': 'OSError'}
    assert doc['status'] == 'attention_required'
