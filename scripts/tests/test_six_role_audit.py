"""Independent audit regression with synthetic native records, never pilot data."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from scripts import audit_six_role_commissioning as audit, commission_six_roles as probe, run_persona_history as history
from scripts.tests.test_persona_history import clock, provider, ACCOUNT, STACK


@pytest.fixture
def native_probe(clock, provider, tmp_path, monkeypatch):
    ledger, connected = tmp_path / 'ledger', tmp_path / 'connected'
    connected.mkdir()
    probe.execute(probe.make_plan(ACCOUNT, STACK), ledger)
    with history.ledger(ledger / 'ledger.db') as db:
        db.row_factory = sqlite3.Row
        claims = [dict(row) for row in db.execute('SELECT * FROM actions')]
    with sqlite3.connect(connected / 'events.db') as db:
        db.execute('''CREATE TABLE events(source TEXT,source_account_id TEXT,event_id TEXT,
            timestamp TEXT,action TEXT,resource TEXT,ip_address TEXT,metadata TEXT)''')
        for i, row in enumerate(claims):
            plan = json.loads(row['plan'])
            metadata = {'requestID': row['request_id'], 'userIdentity': {'type': 'AssumedRole', 'principalId': row['principal_id'],
                         'arn': f"arn:aws:sts::{ACCOUNT}:assumed-role/{STACK}-{row['persona']}/argus-{row['persona']}"}}
            db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?)', ('aws_cloudtrail', ACCOUNT, f'native-{i}',
                       (clock.now + timedelta(seconds=2)).isoformat(), plan['operation'], plan['bucket'], '192.0.2.1', json.dumps(metadata)))
    history.audit(ledger, connected / 'events.db')
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return clock.now + timedelta(minutes=10)
    monkeypatch.setattr(audit, 'datetime', Clock)
    return {'ledger_dir': str(ledger), 'connected_dir': str(connected), 'account_id': ACCOUNT, 'stack': STACK}


def test_full_receipts_features_and_clock_offset_without_writes(native_probe):
    files = [audit.Path(native_probe['ledger_dir']) / 'ledger.db', audit.Path(native_probe['connected_dir']) / 'events.db']
    before = [p.read_bytes() for p in files]
    report = audit.audit(native_probe)
    assert report['status'] == 'complete' and report['independently_matched_native_receipts'] == 18
    assert len(report['role_diagnostics']) == 6
    assert all(r['features']['event_count'] == 3 and r['ip_observability']['valid_events'] == 3 for r in report['role_diagnostics'])
    assert report['cross_clock_sanity_tolerance_seconds'] == 60
    assert report['trained'] is False and report['activated'] is False
    assert ACCOUNT not in json.dumps(report) and '192.0.2.1' not in json.dumps(report)
    assert before == [p.read_bytes() for p in files]


@pytest.mark.parametrize('fault', ['clock_outside_bound', 'wrong_role', 'wrong_request', 'error', 'duplicate_native_id'])
def test_exact_identity_and_time_guards_remain_strict(native_probe, clock, fault):
    path = audit.Path(native_probe['connected_dir']) / 'events.db'
    with sqlite3.connect(path) as db:
        event_id, raw = db.execute('SELECT event_id,metadata FROM events LIMIT 1').fetchone()
        if fault == 'clock_outside_bound':
            db.execute('UPDATE events SET timestamp=? WHERE event_id=?', ((clock.now + timedelta(seconds=61)).isoformat(), event_id))
        elif fault == 'duplicate_native_id':
            db.execute("UPDATE events SET event_id='not-unique'")
        else:
            metadata = json.loads(raw)
            if fault == 'wrong_role': metadata['userIdentity']['arn'] = 'wrong'
            elif fault == 'wrong_request': metadata['requestID'] = 'wrong'
            else: metadata['errorCode'] = 'AccessDenied'
            db.execute('UPDATE events SET metadata=? WHERE event_id=?', (json.dumps(metadata), event_id))
    report = audit.audit(native_probe)
    assert report['status'] == 'pending'
