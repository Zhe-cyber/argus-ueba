"""Live coverage policy tests on a synthetic ledger and event store built from the real frozen plan."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3

import pytest

from scripts import live_coverage_policy as policy
from scripts.live_history_readiness import PROFILE_SHA

ACCOUNT, STACK = '123456789012', 'argus-ueba-actors'
DAY = '2026-11-02'
NOW = datetime(2026, 11, 3, 4, 0, tzinfo=timezone.utc)  # 3 Nov 12:00 MYT: 2 Nov is closed
MYT = timezone(timedelta(hours=8))


def key(persona):
    return 'acct_' + hashlib.sha256(persona.encode()).hexdigest()


def arn(persona):
    return f'arn:aws:sts::{ACCOUNT}:assumed-role/{STACK}-{persona}/argus-{persona}'


def empty_stores(tmp_path):
    ledger, events = tmp_path / 'ledger.db', tmp_path / 'events.db'
    with sqlite3.connect(ledger) as db:
        db.execute('CREATE TABLE scope (id INTEGER PRIMARY KEY CHECK(id=1), contract TEXT NOT NULL)')
        db.execute('CREATE TABLE actions (action_id TEXT PRIMARY KEY, day TEXT, persona TEXT, plan TEXT, status TEXT, '
                   'request_id TEXT, principal_id TEXT, native_event_id TEXT)')
        db.execute('INSERT INTO scope VALUES (1, ?)', (json.dumps([ACCOUNT, STACK, PROFILE_SHA], separators=(',', ':')),))
    with sqlite3.connect(events) as db:
        db.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, source, source_account_id, account_key, event_id, '
                   'timestamp, action, resource, metadata, ingested_at)')
    return ledger, events


def add_day(ledger, events, day, outcome, ingest_delay=timedelta(minutes=5), account_key=key):
    """outcome(persona, index, n) -> 'verified' | 'missed' | 'claimed_unmatched' | 'absent'."""
    by_persona = {}
    for action in policy.planned_actions(day, ACCOUNT, STACK).values():
        by_persona.setdefault(action['persona'], []).append(action)
    with sqlite3.connect(ledger) as led, sqlite3.connect(events) as ev:
        for persona, actions in by_persona.items():
            for index, action in enumerate(actions):
                kind = outcome(persona, index, len(actions))
                if kind == 'absent':
                    continue
                plan = json.dumps({f: action[f] for f in policy.FIELDS})
                if kind == 'missed':
                    led.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?)',
                                (action['action_id'], day, persona, plan, 'missed', None, None, None))
                    continue
                native = f'native-{action["action_id"][:12]}'
                led.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?)', (action['action_id'], day, persona, plan,
                            'provider_verified', 'req-' + native, 'pid-' + persona, native))
                if kind == 'verified':
                    stamp = datetime.fromisoformat(action['planned_utc']) + timedelta(seconds=30)
                    meta = {'requestID': 'req-' + native, 'userIdentity': {
                        'principalId': 'pid-' + persona, 'type': 'AssumedRole', 'arn': arn(persona)}}
                    ev.execute('INSERT INTO events (source,source_account_id,account_key,event_id,timestamp,action,'
                               'resource,metadata,ingested_at) VALUES (?,?,?,?,?,?,?,?,?)',
                               ('aws_cloudtrail', ACCOUNT, account_key(persona), native, stamp.isoformat(),
                                action['operation'], action['bucket'], json.dumps(meta),
                                (stamp + ingest_delay).isoformat()))
    return by_persona


def statuses(coverage):
    return {(c['day'], c['persona']): c for c in coverage}


def test_usable_requires_ninety_percent_native_verified_and_no_unresolved(tmp_path):
    ledger, events = empty_stores(tmp_path)
    plan = add_day(ledger, events, DAY, lambda p, i, n: 'missed' if (p == 'persona-02' and i == 0) else
                   'claimed_unmatched' if (p == 'persona-03' and i == 0) else 'verified')
    cells = statuses(policy.persona_day_coverage(ledger, events, ACCOUNT, STACK, DAY, NOW))
    one = cells[DAY, 'persona-01']
    assert one['status'] == 'usable' and one['verified'] == one['planned'] == len(plan['persona-01'])
    assert len(one['verified_native_event_ids']) == one['verified']
    two = cells[DAY, 'persona-02']
    assert two['missed'] == 1 and two['status'] == ('usable' if (two['planned'] - 1) * 10 >= two['planned'] * 9 else 'incomplete')
    assert cells[DAY, 'persona-03']['unresolved'] == 1 and cells[DAY, 'persona-03']['status'] == 'incomplete'


def test_receipts_ingested_after_the_cutoff_are_not_yet_available(tmp_path):
    ledger, events = empty_stores(tmp_path)
    add_day(ledger, events, DAY, lambda p, i, n: 'verified', ingest_delay=timedelta(days=1, hours=6))
    cells = policy.persona_day_coverage(ledger, events, ACCOUNT, STACK, DAY, NOW)
    day_cells = [c for c in cells if c['day'] == DAY]
    assert all(c['status'] == 'incomplete' and c['verified'] == 0 and c['not_yet_ingested'] == c['planned']
               for c in day_cells)


def test_cutoffs_must_be_aware_and_offsets_are_equivalent(tmp_path):
    ledger, events = empty_stores(tmp_path)
    add_day(ledger, events, DAY, lambda p, i, n: 'verified')
    with pytest.raises(ValueError, match='Aware'):
        policy.persona_day_coverage(ledger, events, ACCOUNT, STACK, DAY, datetime(2026, 11, 3, 12, 0))
    with pytest.raises(ValueError, match='Aware'):
        policy.persona_account_keys(events, ACCOUNT, STACK, datetime(2026, 11, 3, 12, 0))
    utc = policy.persona_day_coverage(ledger, events, ACCOUNT, STACK, DAY, NOW)
    myt = policy.persona_day_coverage(ledger, events, ACCOUNT, STACK, DAY, NOW.astimezone(MYT))
    assert utc == myt


def test_missing_ledger_rows_count_against_the_frozen_denominator(tmp_path):
    ledger, events = empty_stores(tmp_path)
    add_day(ledger, events, DAY, lambda p, i, n: 'absent' if p == 'persona-04' else 'verified')
    cell = statuses(policy.persona_day_coverage(ledger, events, ACCOUNT, STACK, DAY, NOW))[DAY, 'persona-04']
    assert cell['missing'] == cell['planned'] > 0 and cell['status'] == 'incomplete'


def test_substituted_case_actions_are_partitioned_before_plan_validation(tmp_path):
    ledger, events = empty_stores(tmp_path)
    add_day(ledger, events, '2026-11-13', lambda p, i, n: 'verified')
    case_plan = policy.planned_actions('2026-11-14', ACCOUNT, STACK)
    p06 = f'{STACK}-{ACCOUNT}-p06'
    with sqlite3.connect(ledger) as led:
        for action in case_plan.values():
            changed = dict(action)
            if action['persona'] == 'persona-01' and action['operation'] == 'GetObject':
                changed.update(bucket=p06, symbolic_bucket='p06')  # declared V3 substitution
            led.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?)', (action['action_id'], '2026-11-14',
                        action['persona'], json.dumps({f: changed[f] for f in policy.FIELDS}), 'missed', None, None, None))
    # 15 Nov: persona-01 has no planned GetObject (unavailable slot); no replacement action is created.
    cells = statuses(policy.persona_day_coverage(ledger, events, ACCOUNT, STACK, '2026-11-15',
                                                 datetime(2026, 11, 16, 4, 0, tzinfo=timezone.utc)))
    assert cells['2026-11-13', 'persona-01']['status'] == 'usable'  # earlier valid days survive
    assert {c['status'] for (d, _), c in cells.items() if d in ('2026-11-14', '2026-11-15')} == {'excluded_case_date'}
    assert cells['2026-11-14', 'persona-01']['case_actions'] == sum(a['persona'] == 'persona-01' for a in case_plan.values())
    assert cells['2026-11-15', 'persona-01']['case_actions'] == 0 and cells['2026-11-14', 'persona-01']['planned'] == 0


def test_open_and_idle_days_are_never_usable(tmp_path, monkeypatch):
    ledger, events = empty_stores(tmp_path)
    add_day(ledger, events, DAY, lambda p, i, n: 'verified')
    open_day = statuses(policy.persona_day_coverage(ledger, events, ACCOUNT, STACK, DAY,
                                                    datetime(2026, 11, 2, 4, 0, tzinfo=timezone.utc)))
    assert {c['status'] for (d, _), c in open_day.items() if d == DAY} == {'not_closed'}
    real = policy.planned_actions
    monkeypatch.setattr(policy, 'planned_actions', lambda d, a, s: {} if d == '2026-11-01' else real(d, a, s))
    cells = statuses(policy.persona_day_coverage(ledger, events, ACCOUNT, STACK, DAY, NOW))
    assert cells['2026-11-01', 'persona-01']['status'] == 'planned_idle'


def test_commissioning_rows_are_outside_the_denominator_and_exclude_the_day(tmp_path):
    ledger, events = empty_stores(tmp_path)
    add_day(ledger, events, DAY, lambda p, i, n: 'verified')
    with sqlite3.connect(ledger) as db:
        db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?)', ('commission-1', DAY, 'persona-05', json.dumps(
            {'purpose': policy.COMMISSIONING, 'operation': 'GetObject'}), 'provider_verified', 'r', 'p', 'native-c1'))
    cells = statuses(policy.persona_day_coverage(ledger, events, ACCOUNT, STACK, DAY, NOW))
    five = cells[DAY, 'persona-05']
    assert five['commissioning_actions'] == 1 and five['status'] == 'excluded_commissioning'
    assert five['verified'] == five['planned'] and cells[DAY, 'persona-01']['status'] == 'usable'


def test_plan_tampering_and_wrong_scope_fail_closed(tmp_path):
    ledger, events = empty_stores(tmp_path)
    plan = add_day(ledger, events, DAY, lambda p, i, n: 'verified')
    with sqlite3.connect(ledger) as db:
        action = plan['persona-01'][0]
        db.execute('UPDATE actions SET plan=? WHERE action_id=?',
                   (json.dumps({**{f: action[f] for f in policy.FIELDS}, 'operation': 'PutObject'}), action['action_id']))
    with pytest.raises(ValueError, match='frozen plan'):
        policy.persona_day_coverage(ledger, events, ACCOUNT, STACK, DAY, NOW)
    with pytest.raises(ValueError):
        policy.persona_day_coverage(ledger, events, '999999999999', STACK, DAY, NOW)


def test_persona_keys_need_verified_arns_valid_keys_and_the_cutoff(tmp_path):
    ledger, events = empty_stores(tmp_path)
    add_day(ledger, events, DAY, lambda p, i, n: 'verified')
    mapping, diagnostics = policy.persona_account_keys(events, ACCOUNT, STACK, NOW)
    assert mapping == {p: key(p) for p in policy.PERSONAS} and diagnostics['unavailable_personas'] == []
    with sqlite3.connect(events) as db:  # a lookalike IAM-user ARN is ignored
        db.execute("INSERT INTO events (source,source_account_id,account_key,event_id,timestamp,action,resource,metadata,"
                   "ingested_at) VALUES ('aws_cloudtrail',?,?,'x','2026-11-02T01:00:00Z','GetObject','b',?,'2026-11-02T01:05:00Z')",
                   (ACCOUNT, key('other'), json.dumps({'userIdentity': {'type': 'IAMUser', 'arn': 'arn:aws:iam::1:user/persona-01'}})))
    assert policy.persona_account_keys(events, ACCOUNT, STACK, NOW)[0] == mapping
    with sqlite3.connect(events) as db:  # the same role ARN on a second valid key is ambiguous
        db.execute("INSERT INTO events (source,source_account_id,account_key,event_id,timestamp,action,resource,metadata,"
                   "ingested_at) VALUES ('aws_cloudtrail',?,?,'y','2026-11-02T01:00:00Z','GetObject','b',?,'2026-11-02T01:05:00Z')",
                   (ACCOUNT, key('clash'), json.dumps({'userIdentity': {'type': 'AssumedRole', 'arn': arn('persona-01')}})))
    with pytest.raises(ValueError, match='more than one'):
        policy.persona_account_keys(events, ACCOUNT, STACK, NOW)


@pytest.mark.parametrize('bad_key', [None, '', 'acct_persona-01', 'acct_' + 'A' * 64, 'user_' + 'a' * 64])
def test_null_or_malformed_account_keys_never_map(tmp_path, bad_key):
    ledger, events = empty_stores(tmp_path)
    add_day(ledger, events, DAY, lambda p, i, n: 'verified' if p == 'persona-01' else 'absent',
            account_key=lambda persona: bad_key)
    mapping, diagnostics = policy.persona_account_keys(events, ACCOUNT, STACK, NOW)
    assert 'persona-01' not in mapping and 'persona-01' in diagnostics['unavailable_personas']
    assert diagnostics['invalid_key_rows']['persona-01'] >= 1
    assert all(k is not None for k in mapping.values())


def test_late_ingested_role_rows_do_not_map_before_the_cutoff(tmp_path):
    ledger, events = empty_stores(tmp_path)
    add_day(ledger, events, DAY, lambda p, i, n: 'verified', ingest_delay=timedelta(days=2))
    mapping, diagnostics = policy.persona_account_keys(events, ACCOUNT, STACK, NOW)
    assert mapping == {} and sum(diagnostics['late_or_unparseable_rows'].values()) > 0


def test_policy_is_versioned_and_hashed():
    assert policy.POLICY['version'] == 2 and len(policy.policy_sha256()) == 64
    assert policy.POLICY['history_start_local'] == '2026-10-30'
    assert policy.POLICY['excluded_dates_local'] == ['2026-11-14', '2026-11-15']
