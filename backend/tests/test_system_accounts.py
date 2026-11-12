"""Infrastructure context: three rules, declared-file fallback, triage precedence, queue order, feed collapse. Temp SQLite only."""
import json
import sqlite3

import pytest

from backend import alert_store, event_store as events
from backend.tests.test_baseline_alerts import put, sync
from workspace_next import case_store as cases, live_mirror as lm, queries, system_accounts as sa


@pytest.fixture
def db(monkeypatch, tmp_path):
    assert not events._PG, 'Run with DATABASE_URL=sqlite-local'
    monkeypatch.setattr(events, 'DB_PATH', tmp_path / 'events.db')
    events.init_db(); alert_store.init_alerts_db(); cases.init_db()
    return events.DB_PATH


def test_three_rules_and_non_matches():
    assert sa.is_infrastructure('cloudtrail.amazonaws.com', 'service')
    assert sa.is_infrastructure('AWSServiceRoleForResourceExplorer', 'role')
    assert sa.is_infrastructure('argus-readonly', 'IAMUser', labels=frozenset({'argus-readonly'}))
    assert not sa.is_infrastructure('argus-readonly', 'IAMUser')
    assert not sa.is_infrastructure('argus-ueba-actors-persona-02', 'role')
    assert not sa.is_infrastructure('some-token', 'service_token')


def test_declared_file_missing_or_bad_means_no_labels(tmp_path):
    assert sa.declared(tmp_path / 'preview.db') == frozenset()
    (tmp_path / sa.FILE).write_text('not json')
    assert sa.declared(tmp_path / 'preview.db') == frozenset()
    (tmp_path / sa.FILE).write_text(json.dumps({'basis': 'x', 'labels': ['a', 'b']}))
    assert sa.declared(tmp_path / 'preview.db') == {'a', 'b'}


def test_infrastructure_high_is_not_review_first_and_sorts_last(db, tmp_path):
    (tmp_path / sa.FILE).write_text(json.dumps({'basis': 'x', 'labels': ['declared-collector']}))
    for key, strong in (('infra', 60), ('work', 12)):
        put([(key, f'2026-10-{10 - i:02d}T02:00:00Z', 'Read', 'toy') for i in range(1, 7) for _ in range(4)]
            + [(key, '2026-10-10T02:00:00Z', 'Delete', 'secretsmanager/prod-key')] * strong)
    with sqlite3.connect(db) as con:
        con.execute("UPDATE events SET account_label='declared-collector' WHERE account_key='infra'")
        con.execute("UPDATE events SET account_label='workload-a' WHERE account_key='work'")
    sync()
    out = queries.findings(status='All')
    base = [r for r in out['findings'] if r['origin'] == 'baseline']
    by = {r['user_id']: r for r in base}
    assert by['infra']['severity'] == 'High' and by['infra']['triage'] == 'infrastructure_context' and by['infra']['infrastructure']
    assert by['infra']['triage_label'] == 'Context: monitoring infrastructure'
    assert by['work']['triage'] == 'review_first' and not by['work']['infrastructure']
    flags = [r['infrastructure'] for r in out['findings']]
    assert flags == sorted(flags)  # every non-infrastructure row precedes every infrastructure row
    assert base[0]['user_id'] == 'work'
    assert sum(out['triage_counts'].values()) == out['matched_in_scan']
    assert queries.findings(status='All', triage='infrastructure_context')['matched_in_scan'] == 1


def test_service_rule_needs_no_file(db):
    put([('s', f'2026-10-{10 - i:02d}T02:00:00Z', 'Read', 'toy') for i in range(1, 7) for _ in range(4)]
        + [('s', '2026-10-10T02:00:00Z', 'Delete', 'secretsmanager/prod-key')] * 60)
    with sqlite3.connect(db) as con:
        con.execute("UPDATE events SET account_label='x.amazonaws.com', account_kind='service'")
    sync()
    row = [r for r in queries.findings(status='All')['findings'] if r['origin'] == 'baseline'][0]
    assert row['infrastructure'] and row['triage'] == 'infrastructure_context'


def ev(label, action, n=0):
    return {'account_label': label, 'action': action, 'received_seconds_ago': n}


def test_feed_collapses_consecutive_repeats_only():
    out = lm.collapse([ev('a', 'Ping', 1), ev('a', 'Ping', 2), ev('a', 'Ping', 3)])
    assert len(out) == 1 and out[0]['count'] == 3 and out[0]['received_seconds_ago'] == 1  # latest kept
    assert [e['count'] for e in lm.collapse([ev('a', 'Ping'), ev('b', 'Ping'), ev('a', 'Ping')])] == [1, 1, 1]
