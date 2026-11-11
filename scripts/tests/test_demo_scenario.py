"""L4 demo scenario: botocore Stubber and mocks only. No network, no credentials, no real AWS/Cloudflare."""
from datetime import datetime, timedelta, timezone
import io
import json
import re
import sqlite3

import boto3
from botocore.config import Config
from botocore.response import StreamingBody
from botocore.stub import Stubber
import pytest

from scripts import demo_scenario_live as live
from scripts import demo_scenario_sim as sim

MYT = timezone(timedelta(hours=8))
AFTER = datetime(2026, 11, 16, 9, tzinfo=MYT)
ACCOUNT = '123456789012'
RUNNER_ARN = f'arn:aws:iam::{ACCOUNT}:user/argus-lab/argus-ueba-actors-runner'
ARGS = ['--live', '--confirm', 'persona-02']


class FakeSession:
    """Real botocore clients wrapped in Stubbers; the test queues what each one should receive."""
    def __init__(self, identity_arn=RUNNER_ARN, s3_errors=None):
        self.stubs, self.s3_errors, self.identity_arn = {}, s3_errors or {}, identity_arn

    def client(self, service, config=None, **kw):
        c = boto3.session.Session(aws_access_key_id='x', aws_secret_access_key='y', region_name='us-east-1').client(
            service, config=Config(retries={'total_max_attempts': 1}), **{k: v for k, v in kw.items() if k.startswith('aws_')})
        st = Stubber(c)
        getattr(self, '_' + service)(st)
        st.activate()
        self.stubs[service] = st
        return c

    def _sts(self, st):
        st.add_response('get_caller_identity', {'UserId': 'U', 'Account': ACCOUNT, 'Arn': self.identity_arn})
        if self.identity_arn == RUNNER_ARN:
            st.add_response('assume_role', {'Credentials': {'AccessKeyId': 'A' * 16, 'SecretAccessKey': 'b' * 16, 'SessionToken': 'c' * 16,
                                                           'Expiration': datetime(2026, 11, 16, tzinfo=timezone.utc)}},
                            {'RoleArn': f'arn:aws:iam::{ACCOUNT}:role/argus-lab/argus-ueba-actors-persona-02',
                             'RoleSessionName': 'argus-demo-persona-02', 'DurationSeconds': 900})

    def _s3(self, st):
        for i, (n, op, sym) in enumerate(live.AWS_CALLS):
            bucket = f'argus-ueba-actors-{ACCOUNT}-{sym}'
            params = {'Bucket': bucket, 'ExpectedBucketOwner': ACCOUNT}
            if op == 'GetObject':
                params['Key'] = 'fixture.txt'
            method = {'GetBucketLocation': 'get_bucket_location', 'GetObject': 'get_object', 'ListObjectsV2': 'list_objects_v2'}[op]
            if i in self.s3_errors:
                st.add_client_error(method, service_error_code=self.s3_errors[i], http_status_code=403, expected_params=params)
            elif op == 'GetObject':
                st.add_response(method, {'Body': StreamingBody(io.BytesIO(b'x'), 1)}, params)
            else:
                st.add_response(method, {}, params)


def run(tmp_path, argv=ARGS, session=None, clock_now=AFTER, **kw):
    sleeps = []
    session = session or FakeSession()
    rc = live.main(argv, clock=lambda: clock_now, sleep=sleeps.append, session_factory=lambda profile: session,
                   out_dir=tmp_path, **kw)
    ledgers = sorted(tmp_path.glob('run-*.json'))
    return rc, sleeps, (json.loads(ledgers[0].read_text()) if ledgers else None), session


def no_session(profile):
    raise AssertionError('network/session must not be touched')


def test_dry_run_makes_zero_calls(capsys):
    assert live.main([], session_factory=no_session, cf_loader=no_session, http=no_session) == 0
    out = capsys.readouterr().out
    assert 'DRY RUN' in out and 'x12' in out and '35 S3 calls' in out
    assert live.main(['--cloudflare'], session_factory=no_session, cf_loader=no_session, http=no_session) == 0


def test_refuses_before_16_nov(capsys):
    rc = live.main(ARGS, clock=lambda: datetime(2026, 11, 15, 23, 59, tzinfo=MYT), session_factory=no_session,
                   cf_loader=no_session, http=no_session)
    assert rc != 0 and 'study is still open' in capsys.readouterr().err


def test_refuses_without_confirm(capsys):
    for argv in (['--live'], ['--live', '--confirm', 'persona-01']):
        assert live.main(argv, clock=lambda: AFTER, session_factory=no_session) != 0
    assert '--confirm persona-02' in capsys.readouterr().err


def test_full_run_counts_order_and_ledger(tmp_path):
    rc, sleeps, ledger, session = run(tmp_path)
    assert rc == 0
    session.stubs['sts'].assert_no_pending_responses()
    session.stubs['s3'].assert_no_pending_responses()  # exact params and order were enforced by the stubber
    assert len(live.AWS_CALLS) == 35 <= live.MAX_S3
    assert [c['step'] for c in ledger['calls']][:5] == [3, 3, 3, 3, 1] and ledger['calls'][-1]['step'] == 4
    assert sleeps == [2] * 34
    assert ledger['calls'][-1]['operation'] == 'ListObjectsV2'
    text = json.dumps(ledger)
    assert not re.search(r'\d{12}', text) and 'argus-ueba-actors-' not in text
    assert {c['bucket'] for c in ledger['calls']} == {'p04', 'p05', 'p06', 'confidential'}


def test_list_objects_access_denied_is_success(tmp_path):
    rc, _, ledger, _ = run(tmp_path, session=FakeSession(s3_errors={34: 'AccessDenied'}))
    assert rc == 0 and ledger['calls'][-1]['note'] == 'expected denial' and ledger['calls'][-1]['error_code'] == 'AccessDenied'


def test_list_objects_other_error_recorded_and_continues(tmp_path):
    rc, _, ledger, _ = run(tmp_path, session=FakeSession(s3_errors={34: 'SlowDown'}))
    assert rc == 0 and ledger['calls'][-1]['note'] == 'recorded, continue'


def test_unexpected_error_aborts_at_once(tmp_path):
    rc, _, ledger, _ = run(tmp_path, session=FakeSession(s3_errors={6: 'AccessDenied'}))
    assert rc == 1 and len(ledger['calls']) == 7 and 'unexpected error' in ledger['aborted']


def test_wrong_caller_makes_no_assume(tmp_path):
    rc, _, ledger, session = run(tmp_path, session=FakeSession(identity_arn=f'arn:aws:iam::{ACCOUNT}:user/someone-else'))
    assert rc == 1 and ledger['calls'] == [] and 'not the lab runner' in ledger['aborted']
    session.stubs['sts'].assert_no_pending_responses()


def test_s3_cap_enforced(tmp_path, monkeypatch):
    monkeypatch.setattr(live, 'MAX_S3', 10)
    rc, _, ledger, _ = run(tmp_path)
    assert rc == 1 and len(ledger['calls']) == 10 and ledger['aborted'] == 'S3 call cap reached'


def test_cloudflare_eight_gets_and_no_secret(tmp_path):
    seen = []
    def http(url, headers):
        seen.append(url)
        return 200, 'abc123abc123abcd'
    rc, sleeps, ledger, _ = run(tmp_path, argv=ARGS + ['--cloudflare'], http=http,
                                cf_loader=lambda state: ('argus-machine-lab.argus-lab-x1.workers.dev', 'cid', 'SECRET-VALUE'))
    assert rc == 0 and len(seen) == 8 and seen[0].endswith('/workloads/persona-02/demo-1') and ledger['cloudflare'] == 'done'
    assert sleeps.count(5) == 7
    assert 'SECRET-VALUE' not in json.dumps(ledger) and 'cid' not in json.dumps(ledger).replace('cloudflare', '')


def test_cloudflare_403_stops_only_cloudflare(tmp_path):
    codes = iter([200, 200, 403])
    rc, _, ledger, session = run(tmp_path, argv=ARGS + ['--cloudflare'], http=lambda u, h: (next(codes), 'ray'),
                                 cf_loader=lambda state: ('argus-machine-lab.argus-lab-x1.workers.dev', 'cid', 's'))
    assert rc == 0 and len(ledger['cloudflare_calls']) == 3 and 'HTTP 403' in ledger['cloudflare']
    assert len(ledger['calls']) == 35 and 'aborted' not in ledger
    session.stubs['s3'].assert_no_pending_responses()


def test_cloudflare_loader_failure_is_reported_not_fatal(tmp_path):
    def broken(state):
        raise FileNotFoundError('x')
    rc, _, ledger, _ = run(tmp_path, argv=ARGS + ['--cloudflare'], cf_loader=broken, http=no_session)
    assert rc == 0 and ledger['cloudflare'] == 'not started: FileNotFoundError'


# ---- simulated rehearsal ---------------------------------------------------------------------------

def _tpl(source, resource, kind):
    return {'user': 'u', 'timestamp': 't', 'source': source, 'action': 'x', 'resource': resource, 'ip_address': 'ip',
            'metadata': '{}', 'ingested_at': 'i', 'event_id': 'e', 'source_account_id': 's', 'payload_digest': 'd',
            'pipeline_result': '{}', 'account_key': 'k-' + kind, 'account_label': 'L', 'account_kind': kind, 'account_basis': 'b'}


def test_sim_rows_shape_counts_and_window():
    day = sim.closed_day(datetime(2026, 11, 11, 10, tzinfo=MYT))
    assert day.isoformat() == '2026-11-10'
    rows = sim.build_rows(_tpl('aws_cloudtrail', 'argus-ueba-actors-123456789012-p02', 'role'),
                          _tpl('cloudflare_access', 'h.workers.dev/workloads/persona-02/abc', 'service_token'), day)
    aws = [r for r in rows if r['source'] == 'aws_cloudtrail']
    cf = [r for r in rows if r['source'] == 'cloudflare_access']
    assert (len(aws), len(cf)) == (35, 8)
    count = lambda act, suf: sum(r['action'] == act and r['resource'].endswith('-' + suf) for r in aws)
    assert count('GetObject', 'confidential') == 12 and all(count('GetObject', s) == 6 for s in ('p04', 'p05', 'p06'))
    assert all(count('GetBucketLocation', s) == 1 for s in ('confidential', 'p04', 'p05', 'p06')) and count('ListObjectsV2', 'confidential') == 1
    assert all(r['event_id'].startswith('sim-') for r in rows) and len({r['event_id'] for r in rows}) == 43
    assert json.loads([r for r in aws if r['action'] == 'ListObjectsV2'][0]['metadata']) == {'simulated': True, 'scenario': 'L4', 'errorCode': 'AccessDenied'}
    assert json.loads(cf[0]['metadata']) == {'simulated': True, 'scenario': 'L4'}
    assert cf[0]['resource'].endswith('/workloads/persona-02/demo-1')
    for r in rows:
        t = datetime.strptime(r['timestamp'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).astimezone(MYT)
        assert t.date() == day and (21, 5) <= (t.hour, t.minute) <= (21, 25)
        assert r['account_key'].startswith('k-') and r['account_basis'] == 'b'


def test_sim_prepare_refuses_unmarked_and_copies_marked(tmp_path):
    src = tmp_path / 'demo'
    src.mkdir()
    db = src / 'preview.db'
    sqlite3.connect(db).execute('CREATE TABLE events (id INTEGER PRIMARY KEY, event_id TEXT)').connection.commit()
    with pytest.raises(SystemExit):
        sim.prepare(src, tmp_path / 'r1')  # no marker
    (src / 'workspace-copy.json').write_text(json.dumps({'not_live': False, 'copy_db': str(db)}))
    with pytest.raises(SystemExit):
        sim.prepare(src, tmp_path / 'r1')
    (src / 'workspace-copy.json').write_text(json.dumps({'not_live': True, 'copy_db': str(db.resolve())}))
    out = sim.prepare(src, tmp_path / 'r2')
    marker = json.loads((out.parent / 'workspace-copy.json').read_text())
    assert marker['not_live'] is True and marker['rehearsal'] is True and marker['copy_db'] == str(out)
    assert sqlite3.connect(db).execute("SELECT count(*) FROM events WHERE event_id LIKE 'sim-%'").fetchone()[0] == 0
