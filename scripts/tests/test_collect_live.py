"""No real provider or local backend access: verify acknowledgment boundaries."""
import json
from types import SimpleNamespace

import pytest

from scripts.collect_live import CollectionError, LocalBackend, aws_record, collect_aws, collect_cloudflare, consume_sqs, forward, local_api


ACCOUNT = '123456789012'
QUEUE = f'https://sqs.us-east-1.amazonaws.com/{ACCOUNT}/argus-events'


def envelope():
    return {'account': ACCOUNT, 'source': 'aws.s3', 'detail-type': 'AWS API Call via CloudTrail', 'detail': {
        'eventID': 'native-one', 'eventName': 'ListBuckets', 'eventTime': '2026-10-27T12:00:00Z',
        'recipientAccountId': ACCOUNT, 'userIdentity': {'accountId': ACCOUNT, 'userName': 'test'},
    }}


class Queue:
    def __init__(self, bodies, delete_error=False):
        self.messages = [{'Body': body, 'ReceiptHandle': f'receipt-{i}'} for i, body in enumerate(bodies)]
        self.deleted = []
        self.delete_error = delete_error

    def receive_message(self, **kwargs):
        return {'Messages': self.messages}

    def delete_message(self, **kwargs):
        if self.delete_error:
            raise RuntimeError('Injected transient SQS failure')
        self.deleted.append(kwargs['ReceiptHandle'])


class Backend:
    def __init__(self, result):
        self.result = result
        self.posts = []

    def post(self, *args):
        self.posts.append(args)
        return self.result


@pytest.mark.parametrize('url', ['https://example.com', 'http://192.168.1.2:8000',
    'http://localhost:8000', 'http://127.0.0.1:8000/path', 'http://127.0.0.1:8000?token=x',
    'http://user:password@127.0.0.1:8000', 'file:///tmp/file'])
def test_logs_cannot_be_forwarded_off_loopback(url):
    with pytest.raises(CollectionError):
        local_api(url)


def test_loopback_and_backend_readiness_checks(monkeypatch):
    assert local_api('http://127.0.0.1:8000/') == 'http://127.0.0.1:8000'
    backend = LocalBackend('http://127.0.0.1:8000')
    assert backend.session.trust_env is False
    response = SimpleNamespace(status_code=200, json=lambda: {'application_mode': 'live'})
    monkeypatch.setattr(backend.session, 'get', lambda *args, **kwargs: response)
    with pytest.raises(CollectionError, match='native-receipt'):
        backend.preflight()


@pytest.mark.parametrize('result,expected', [(False, 'inserted'), (True, 'duplicates')])
def test_acknowledge_only_committed_or_duplicate_receipt(result, expected):
    queue = Queue([json.dumps(envelope())])
    backend = Backend(result)
    counts = consume_sqs(queue, QUEUE, ACCOUNT, backend)
    assert counts[expected] == counts['acknowledged'] == 1
    assert queue.deleted == ['receipt-0']
    assert backend.posts[0][1] == ACCOUNT


def test_failed_post_malformed_and_wrong_account_are_retained():
    wrong = envelope()
    wrong['account'] = '999999999999'
    queue = Queue(['not json', json.dumps(wrong), json.dumps(envelope())])
    backend = Backend(None)
    counts = consume_sqs(queue, QUEUE, ACCOUNT, backend)
    assert counts['retained'] == 3
    assert counts['malformed'] == 2
    assert queue.deleted == []
    assert len(backend.posts) == 1


def test_delete_failure_is_retained_for_safe_retry():
    queue = Queue([json.dumps(envelope())], delete_error=True)
    counts = consume_sqs(queue, QUEUE, ACCOUNT, Backend(False))
    assert counts['inserted'] == counts['retained'] == 1
    assert counts['acknowledged'] == 0


def test_http_200_without_matching_receipt_is_not_success(monkeypatch):
    backend = LocalBackend('http://127.0.0.1:8000')
    response = SimpleNamespace(status_code=200, json=lambda: {'message': 'ok'})
    monkeypatch.setattr(backend.session, 'post', lambda *args, **kwargs: response)
    assert backend.post('aws_cloudtrail', ACCOUNT, envelope()['detail'], 'native-one') is None


def test_idless_or_timezone_missing_records_are_not_forwarded():
    backend = Backend(False)
    records = [{'created_at': '2026-10-27T12:00:00Z'},
               {'id': 'one', 'created_at': '2026-10-27T12:00:00'}]
    counts = forward(backend, 'github_events', 'repo-owner', records, 'id')
    assert counts['malformed'] == counts['retained'] == 2
    assert backend.posts == []


def test_cloudtrail_native_account_and_event_id_are_required():
    event = envelope()
    del event['detail']['eventID']
    assert aws_record(event, ACCOUNT) is None
    assert aws_record({'eventID': 'one', 'eventTime': '2026-10-27T12:00:00Z',
                       'eventName': 'ListBuckets', 'userIdentity': {}}, ACCOUNT) is None


def test_root_collector_is_refused_before_queue_access(monkeypatch):
    import boto3
    caller = SimpleNamespace(get_caller_identity=lambda: {'Account': ACCOUNT, 'Arn': f'arn:aws:iam::{ACCOUNT}:root'})
    def fake_client(service):
        assert service == 'sts', 'Root collector reached SQS'
        return caller
    monkeypatch.setattr(boto3, 'Session', lambda **kwargs: SimpleNamespace(client=fake_client))
    args = SimpleNamespace(queue_url=QUEUE, account_id=ACCOUNT, profile='test', batches=1)
    with pytest.raises(CollectionError, match='non-root'):
        collect_aws(args, Backend(False))


def test_cloudflare_invalid_matching_record_is_retained_not_silently_skipped(monkeypatch):
    from scripts import setup_cloudflare
    records = [{'app_uid': 'expected-app', 'user_email': 'test@example.com', 'allowed': 'true'},
               {'app_uid': 'different-app'}]
    monkeypatch.setattr(setup_cloudflare, 'load_token', lambda *_: 'dummy')
    monkeypatch.setattr(setup_cloudflare, 'Cloudflare', lambda *args: SimpleNamespace(call=lambda *args: records))
    counts = collect_cloudflare(SimpleNamespace(account_id='test-account', app_id='expected-app'), Backend(False))
    assert counts['received'] == 2
    assert counts['malformed'] == counts['retained'] == counts['skipped'] == 1
