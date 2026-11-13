"""Operational collector: fake providers and temp folders only. No network, no real credentials."""
from datetime import datetime, timedelta, timezone
import json
import re
import sqlite3
from types import SimpleNamespace

import pytest

from scripts import collect_live, ops_collect
from backend.tests.test_live_mode import cloud_event, live_client  # noqa: F401  shared live fixture

ACCOUNT = '123456789012'
QUEUE = f'https://sqs.us-east-1.amazonaws.com/{ACCOUNT}/argus-events'
NOW = datetime(2026, 11, 17, 2, tzinfo=timezone.utc)  # 10:00 MYT, 17 Nov


def make_config(tmp_path, **overrides):
    cfg = {'schema': 'argus_ops_v1', 'backend_url': 'http://127.0.0.1:8020',
           'live_state_dir': str(tmp_path / 'connected'), 'status_dir': str(tmp_path / 'ops'),
           'collect_start_local': '2026-11-17', 'protected_paths': [str(tmp_path / 'pilot')],
           'intervals_minutes': {'aws': 5, 'github': 30, 'cloudflare': 30},
           'providers': {'aws': {'enabled': True, 'account_id': ACCOUNT, 'queue_url': QUEUE, 'batches': 5},
                         'github': {'enabled': True, 'repos': ['owner/repo']},
                         'cloudflare': {'enabled': True, 'account_id': 'a' * 32, 'app_ids': ['b' * 8 + '-' + 'c' * 27]}},
           'personas': {'enabled': False, 'start_local': '2026-11-16', 'ledger_dir': str(tmp_path / 'ledger')}}
    cfg.update(overrides)
    path = tmp_path / 'ops.json'
    path.write_text(json.dumps(cfg), encoding='utf-8')
    return ops_collect.load_config(path)


class ReadyBackend:
    def __init__(self, url):
        self.url = url

    def preflight(self):
        pass


def counts(**kw):
    return {'received': 0, 'inserted': 0, 'duplicates': 0, 'retained': 0, 'malformed': 0, 'skipped': 0,
            'acknowledged': 0, **kw}


def test_one_failing_provider_does_not_stop_the_others(tmp_path):
    cfg = make_config(tmp_path)
    called = []

    def ok(name, **kw):
        def run(cfg, backend):
            called.append(name)
            return counts(**kw)
        return run

    def broken(cfg, backend):
        called.append('github')
        raise RuntimeError(f'secret detail {ACCOUNT}')

    doc = ops_collect.tick(cfg, NOW, {'aws': ok('aws', received=3, inserted=3, acknowledged=3),
                                      'github': broken, 'cloudflare': ok('cloudflare', received=1, duplicates=1)},
                           ReadyBackend)
    assert called == ['aws', 'github', 'cloudflare']
    p = doc['providers']
    assert p['aws']['ok'] and p['aws']['inserted'] == 3 and p['aws']['error_kind'] is None
    assert p['github'] == {'last_run_utc': NOW.isoformat(), 'state': 'ran', 'ok': False,
                           'error_kind': 'RuntimeError', 'received': 0, 'inserted': 0}
    assert p['cloudflare']['ok'] and p['cloudflare']['duplicates'] == 1
    assert doc['status'] == 'partial_failure'
    text = (tmp_path / 'ops' / 'ops-status.json').read_text(encoding='utf-8')
    assert json.loads(text) == doc
    assert 'secret detail' not in text and not re.search(r'\d{12}', text)


def test_status_keeps_last_ok_and_respects_intervals(tmp_path):
    cfg = make_config(tmp_path)
    runs = []
    runner = lambda cfg, backend: runs.append(1) or counts()
    all_ok = {'aws': runner, 'github': runner, 'cloudflare': runner}
    ops_collect.tick(cfg, NOW, all_ok, ReadyBackend)
    later = NOW + timedelta(minutes=5)
    fail = lambda cfg, backend: (_ for _ in ()).throw(TimeoutError())
    doc = ops_collect.tick(cfg, later, {**all_ok, 'aws': fail}, ReadyBackend)
    assert doc['providers']['aws']['ok'] is False and doc['providers']['aws']['last_ok_utc'] == NOW.isoformat()
    assert doc['providers']['github']['state'] == 'not_due' and doc['providers']['github']['ok'] is True
    assert len(runs) == 3  # GitHub and Cloudflare waited for their 30-minute interval
    doc = ops_collect.tick(cfg, NOW + timedelta(minutes=30), all_ok, ReadyBackend)
    assert all(p['state'] == 'ran' and p['ok'] for p in doc['providers'].values())


def test_backend_down_consumes_nothing(tmp_path):
    cfg = make_config(tmp_path)

    class Down(ReadyBackend):
        def preflight(self):
            raise collect_live.CollectionError('not ready')

    doc = ops_collect.tick(cfg, NOW, {n: lambda *a: pytest.fail('provider called') for n in ops_collect.PROVIDERS}, Down)
    assert {p['error_kind'] for p in doc['providers'].values()} == {'backend_unavailable'}


def test_nothing_runs_while_the_pilot_owns_collection(tmp_path):
    cfg = make_config(tmp_path)
    doc = ops_collect.tick(cfg, datetime(2026, 11, 16, 15, 59, tzinfo=timezone.utc),  # 23:59 MYT 16 Nov
                           {n: lambda *a: pytest.fail('provider called') for n in ops_collect.PROVIDERS},
                           lambda url: pytest.fail('backend contacted'))
    assert doc['status'] == 'not_started_pilot_owns_collection'


def test_disabled_provider_is_skipped(tmp_path):
    cfg = make_config(tmp_path)
    cfg['providers']['cloudflare']['enabled'] = False
    doc = ops_collect.tick(cfg, NOW, {'aws': lambda *a: counts(), 'github': lambda *a: counts(),
                                      'cloudflare': lambda *a: pytest.fail('disabled provider called')}, ReadyBackend)
    assert doc['providers']['cloudflare'] == {'state': 'disabled'} and doc['status'] == 'completed'


def test_retained_records_are_not_ok(tmp_path):
    cfg = make_config(tmp_path)
    doc = ops_collect.tick(cfg, NOW, {'aws': lambda *a: counts(received=2, retained=1, inserted=1),
                                      'github': lambda *a: counts(), 'cloudflare': lambda *a: counts()}, ReadyBackend)
    assert doc['providers']['aws']['ok'] is False and doc['providers']['aws']['error_kind'] == 'records_retained_for_retry'


@pytest.mark.parametrize('key', ['live_state_dir', 'status_dir'])
def test_refuses_to_write_inside_protected_pilot_checkout(tmp_path, key):
    with pytest.raises(ValueError, match='protected'):
        make_config(tmp_path, **{key: str(tmp_path / 'pilot' / 'data')})


def test_aws_runner_reuses_the_existing_fetcher_end_to_end(tmp_path, monkeypatch):
    """The real collect_live.collect_aws path with a fake boto3 session and fake backend."""
    import boto3
    cfg = make_config(tmp_path)
    body = json.dumps({'account': ACCOUNT, 'source': 'aws.s3', 'detail-type': 'AWS API Call via CloudTrail',
                       'detail': {'eventID': 'e1', 'eventName': 'GetObject', 'eventTime': '2026-11-17T01:00:00Z',
                                  'recipientAccountId': ACCOUNT, 'userIdentity': {'accountId': ACCOUNT}}})
    deleted = []

    class Client:
        def __init__(self, name):
            self.name = name

        def get_caller_identity(self):
            return {'Account': ACCOUNT, 'Arn': f'arn:aws:iam::{ACCOUNT}:user/collector'}

        def get_queue_attributes(self, **kw):
            return {'Attributes': {'QueueArn': f'arn:aws:sqs:us-east-1:{ACCOUNT}:argus-events',
                                   'RedrivePolicy': json.dumps({'deadLetterTargetArn': f'arn:aws:sqs:us-east-1:{ACCOUNT}:dlq'})}}

        def receive_message(self, **kw):
            return {'Messages': [] if deleted else [{'Body': body, 'ReceiptHandle': 'r1'}]}

        def delete_message(self, **kw):
            deleted.append(kw['ReceiptHandle'])

    monkeypatch.setattr(boto3, 'Session', lambda **kw: SimpleNamespace(client=Client))

    class Backend(ReadyBackend):
        def post(self, source, namespace, record, native_id):
            assert (source, native_id) == ('aws_cloudtrail', 'e1')
            return False

    doc = ops_collect.tick(cfg, NOW, {**ops_collect.RUNNERS, 'github': lambda *a: counts(),
                                      'cloudflare': lambda *a: counts()}, Backend)
    assert doc['providers']['aws']['inserted'] == 1 and doc['providers']['aws']['acknowledged'] == 1
    assert deleted == ['r1']


def test_github_and_cloudflare_runners_map_config_to_existing_fetchers(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    cfg['providers']['github']['repos'] = ['owner/a', 'owner/b']
    seen = []
    monkeypatch.setattr(collect_live, 'collect_github',
                        lambda args, backend: seen.append(('gh', args.repo, args.revision_dir.name)) or counts(received=2, inserted=1))
    monkeypatch.setattr(collect_live, 'collect_cloudflare',
                        lambda args, backend: seen.append(('cf', args.app_id)) or counts(received=1))
    assert ops_collect.run_github(cfg, None)['inserted'] == 2
    assert ops_collect.run_cloudflare(cfg, None)['received'] == 1
    assert seen == [('gh', 'owner/a', 'github-event-revisions'), ('gh', 'owner/b', 'github-event-revisions'),
                    ('cf', cfg['providers']['cloudflare']['app_ids'][0])]


def test_init_copies_a_read_only_source_once(tmp_path):
    cfg = make_config(tmp_path)
    source = tmp_path / 'pilot' / 'events.db'
    source.parent.mkdir()
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE events(id INTEGER)')
        db.executemany('INSERT INTO events VALUES(?)', [(1,), (2,)])
    before = source.read_bytes()
    assert ops_collect.init_store(cfg, source) == {'status': 'initialized', 'events_copied': 2}
    assert source.read_bytes() == before
    with pytest.raises(ValueError, match='already exists'):
        ops_collect.init_store(cfg, source)


def test_serve_refuses_an_empty_store(tmp_path):
    with pytest.raises(ValueError, match='init first'):
        ops_collect.serve(make_config(tmp_path))


def test_tracked_template_loads_and_has_no_identifiers():
    from pathlib import Path
    path = Path(ops_collect.ROOT) / 'config' / 'ops.json'
    text = path.read_text(encoding='utf-8')
    assert not re.search(r'\d{12}|@|[a-f0-9]{32}', text)
    cfg = json.loads(text)
    assert cfg['schema'] == 'argus_ops_v1' and cfg['personas']['enabled'] is False
    with pytest.raises(ValueError, match='12-digit'):  # an unfilled template never runs
        ops_collect.load_config(path)


class RedeliveringQueue:
    """SQS-like: a message stays queued (and is redelivered) until deleted."""
    def __init__(self, body, fail_delete_once=False):
        self.body, self.queued, self.fail_delete_once, self.hidden = body, True, fail_delete_once, False

    def receive(self):  # visibility timeout: a received message reappears only on a later pass
        if not self.queued or self.hidden:
            return []
        self.hidden = True
        return [{'Body': self.body, 'ReceiptHandle': 'r1'}]

    def delete(self):
        if self.fail_delete_once:
            self.fail_delete_once = False
            raise RuntimeError('transient delete failure')
        self.queued = False


@pytest.mark.parametrize('failure', ['ingest_timeout', 'delete_failure'])
def test_redelivered_message_gets_duplicate_receipt_and_is_deleted_once(tmp_path, monkeypatch, failure):
    import boto3
    cfg = make_config(tmp_path)
    body = json.dumps({'account': ACCOUNT, 'source': 'aws.s3', 'detail-type': 'AWS API Call via CloudTrail',
                       'detail': {'eventID': 'e1', 'eventName': 'GetObject', 'eventTime': '2026-11-17T01:00:00Z',
                                  'recipientAccountId': ACCOUNT, 'userIdentity': {'accountId': ACCOUNT}}})
    queue = RedeliveringQueue(body, fail_delete_once=failure == 'delete_failure')

    class Client:
        def __init__(self, name):
            pass

        def get_caller_identity(self):
            return {'Account': ACCOUNT, 'Arn': f'arn:aws:iam::{ACCOUNT}:user/collector'}

        def get_queue_attributes(self, **kw):
            return {'Attributes': {'QueueArn': f'arn:aws:sqs:us-east-1:{ACCOUNT}:argus-events',
                                   'RedrivePolicy': json.dumps({'deadLetterTargetArn': f'arn:aws:sqs:us-east-1:{ACCOUNT}:dlq'})}}

        def receive_message(self, **kw):
            return {'Messages': queue.receive()}

        def delete_message(self, **kw):
            queue.delete()

    monkeypatch.setattr(boto3, 'Session', lambda **kw: SimpleNamespace(client=Client))
    store, timeouts = set(), [failure == 'ingest_timeout']

    class IdempotentBackend(ReadyBackend):
        def post(self, source, namespace, record, native_id):  # mirrors /ingest's (source, event id) receipt
            if timeouts and timeouts.pop():
                return None  # no durable receipt seen by the client
            duplicate = (source, native_id) in store
            store.add((source, native_id))
            return duplicate

    others = {'github': lambda *a: counts(), 'cloudflare': lambda *a: counts()}
    first = ops_collect.tick(cfg, NOW, {**ops_collect.RUNNERS, **others}, IdempotentBackend)['providers']['aws']
    assert first['ok'] is False and first['retained'] == 1 and queue.queued
    queue.hidden = False  # visibility timeout expired: redelivered
    second = ops_collect.tick(cfg, NOW + timedelta(minutes=5), {**ops_collect.RUNNERS, **others}, IdempotentBackend)['providers']['aws']
    assert second['ok'] and second['acknowledged'] == 1 and not queue.queued
    assert second['duplicates'] == (1 if failure == 'delete_failure' else 0)
    assert store == {('aws_cloudtrail', 'e1')}  # one stored event, never a double insert


def test_full_page_is_flagged_and_staleness_reported(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    monkeypatch.setattr(collect_live, 'collect_github', lambda args, backend: counts(received=100, skipped=100))
    monkeypatch.setattr(collect_live, 'collect_cloudflare', lambda args, backend: counts(received=7))
    doc = ops_collect.tick(cfg, NOW, {**ops_collect.RUNNERS, 'aws': lambda *a: counts()}, ReadyBackend)
    assert doc['providers']['github']['possibly_truncated'] is True
    assert doc['providers']['cloudflare']['possibly_truncated'] is False
    later = ops_collect.tick(cfg, NOW + timedelta(minutes=10), {'aws': lambda *a: (_ for _ in ()).throw(OSError()),
                             'github': lambda *a: counts(), 'cloudflare': lambda *a: counts()}, ReadyBackend)
    assert later['providers']['aws']['minutes_since_last_ok'] == 10.0
    assert later['providers']['github']['minutes_since_last_ok'] == 10.0  # not due yet; last success 10 min ago


def test_persona_summary_is_surfaced_in_ops_status(tmp_path):
    cfg = make_config(tmp_path)
    (tmp_path / 'ops').mkdir()
    ops_collect.atomic_json(tmp_path / 'ops' / 'ops-personas-status.json',
                            {'at_utc': NOW.isoformat(), 'status': 'attention_required',
                             'cloudflare': {'ok': False, 'state': 'token_expired_or_invalid'}})
    doc = ops_collect.tick(cfg, NOW, {n: lambda *a: counts() for n in ops_collect.PROVIDERS}, ReadyBackend)
    assert doc['personas']['cloudflare']['state'] == 'token_expired_or_invalid'


def test_machine_ingest_interface_is_not_behind_sign_in(live_client):
    """The collectors post to backend.main (/ and /ingest) with no cookie; workspace sign-in is never installed there."""
    from backend.main import app
    assert not hasattr(app.state, 'auth')
    root = live_client.get('/')
    assert root.status_code == 200 and root.json()['ingestion_protocol'] == 'native-receipt-v1'
    assert root.json()['application_mode'] == 'live'
    receipt = live_client.post('/ingest', json={**cloud_event(), 'source_account_id': ACCOUNT})
    assert receipt.status_code == 200 and receipt.json()['duplicate'] is False
    assert live_client.post('/ingest', json={**cloud_event(), 'source_account_id': ACCOUNT}).json()['duplicate'] is True
