import hashlib
import hmac
import json
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from scripts import github_webhook_receiver as receiver

SECRET = b'private-test-secret-32-bytes-long!'


def payload(event='push'):
    result = {'repository': {'id': 123, 'full_name': 'example/toy'},
              'sender': {'id': 456, 'login': 'example-user', 'type': 'User'}}
    result.update({
        'push': {'ref': 'refs/heads/main', 'pusher': {'name': 'example-user'},
                 'commits': [], 'before': 'a' * 40, 'after': 'b' * 40},
        'ping': {'zen': 'example', 'hook_id': 10},
        'pull_request': {'action': 'opened', 'pull_request': {'id': 11}},
        'issues': {'action': 'opened', 'issue': {'id': 12}},
        'issue_comment': {'action': 'created', 'comment': {'id': 13}},
        'create': {'ref_type': 'branch', 'ref': 'test'},
        'delete': {'ref_type': 'branch', 'ref': 'test'},
    }[event])
    return result


def headers(body, event='push', delivery=None):
    return {'content-type': 'application/json', 'x-github-event': event,
            'x-github-delivery': delivery or str(uuid4()),
            'x-hub-signature-256': 'sha256=' + hmac.new(SECRET, body, hashlib.sha256).hexdigest()}


@pytest.fixture
def instance(tmp_path):
    database = tmp_path / 'github-webhooks.db'
    with TestClient(receiver.create_app(database, SECRET, 123, 'example/toy')) as client:
        yield client, database


@pytest.mark.parametrize('event', sorted(receiver.EVENTS))
def test_exact_bytes_stored_before_ack(instance, event):
    client, database = instance
    body = json.dumps(payload(event), indent=2).encode()
    result = client.post('/github/webhook', content=body, headers=headers(body, event))
    assert result.status_code == 200
    assert result.json() == {'stored': True, 'duplicate': False, 'native_event_time': 'not_asserted', 'scored': False}
    with sqlite3.connect(database) as db:
        row = db.execute('SELECT signed_body,body_sha256,event_type,actor_type FROM deliveries').fetchone()
    assert row == (body, hashlib.sha256(body).hexdigest(), event, 'User')


def test_signature_is_over_exact_bytes_and_rejection_does_not_store(instance):
    client, database = instance
    body = json.dumps(payload()).encode()
    result = client.post('/github/webhook', content=body + b' ', headers=headers(body))
    assert result.status_code == 401
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT count(*) FROM deliveries').fetchone()[0] == 0


def test_redelivery_and_conflicts(instance):
    client, database = instance
    body = json.dumps(payload()).encode()
    original_headers = headers(body)
    assert client.post('/github/webhook', content=body, headers=original_headers).status_code == 200
    assert client.post('/github/webhook', content=body, headers=original_headers).json()['duplicate'] is True
    assert client.post('/github/webhook', content=body, headers=headers(body)).status_code == 409
    changed = json.dumps({**payload(), 'ref': 'refs/heads/other'}).encode()
    assert client.post('/github/webhook', content=changed, headers=headers(changed, delivery=original_headers['x-github-delivery'])).status_code == 409
    # A different event header cannot silently count the same body twice.
    both = json.dumps(payload('create')).encode()
    assert client.post('/github/webhook', content=both, headers=headers(both, 'create')).status_code == 200
    assert client.post('/github/webhook', content=both, headers=headers(both, 'delete')).status_code == 409
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT count(*) FROM deliveries').fetchone()[0] == 2


@pytest.mark.parametrize('patch', [
    {'repository': {'id': 999, 'full_name': 'example/toy'}},
    {'repository': {'id': 123, 'full_name': 'other/repo'}},
    {'sender': {'id': True}}, {'sender': {}}, {'commits': None}, {'before': 123}, {'before': 'a' * 41},
])
def test_scope_and_shape_fail_closed(instance, patch):
    client, _ = instance
    body = json.dumps({**payload(), **patch}).encode()
    assert client.post('/github/webhook', content=body, headers=headers(body)).status_code == 422


@pytest.mark.parametrize('body', [b'[]', b'{', b'\xff', b'{"x":NaN}', b'{"x":1,"x":2}'])
def test_invalid_signed_json(instance, body):
    client, _ = instance
    assert client.post('/github/webhook', content=body, headers=headers(body)).status_code == 422


def test_headers_type_and_size(instance):
    client, _ = instance
    body = json.dumps(payload()).encode()
    for name, value, code in [('x-github-delivery', 'not-a-uuid', 400),
                              ('x-github-event', 'unknown', 400),
                              ('content-type', 'text/plain', 415),
                              ('content-encoding', 'gzip', 415)]:
        values = {**headers(body), name: value}
        assert client.post('/github/webhook', content=body, headers=values).status_code == code
    duplicate = list(headers(body).items()) + [('x-github-event', 'delete')]
    assert client.post('/github/webhook', content=body, headers=duplicate).status_code == 400
    huge = b'x' * (receiver.MAX_BODY + 1)
    assert client.post('/github/webhook', content=huge, headers=headers(huge)).status_code == 413


def test_storage_failure_is_not_acknowledged(instance, monkeypatch):
    client, _ = instance
    def unavailable(*args):
        raise sqlite3.OperationalError('test-only unavailable')
    monkeypatch.setattr(receiver, 'persist', unavailable)
    body = json.dumps(payload()).encode()
    result = client.post('/github/webhook', content=body, headers=headers(body))
    assert result.status_code == 503
    assert result.json() == {'detail': 'Evidence storage unavailable'}


def test_deduplication_survives_app_restart(instance):
    client, database = instance
    body = json.dumps(payload()).encode()
    values = headers(body)
    assert client.post('/github/webhook', content=body, headers=values).status_code == 200
    with TestClient(receiver.create_app(database, SECRET, 123, 'example/toy')) as restarted:
        assert restarted.post('/github/webhook', content=body, headers=values).json()['duplicate'] is True


def test_explicit_dedicated_storage_and_secret_required(tmp_path):
    with pytest.raises(ValueError):
        receiver.create_app(tmp_path / 'events.db', SECRET, 123, 'example/toy')
    with pytest.raises(ValueError):
        receiver.create_app(tmp_path / 'github-webhooks.db', b'short', 123, 'example/toy')
    assert not list(tmp_path.iterdir())
