"""Synthetic tests: resource identity must not depend on the current actor."""
from copy import deepcopy
import hashlib
import json
import pytest

from scripts.resource_observability import resource, token


def aws():
    return {'eventSource': 's3.amazonaws.com', 'recipientAccountId': '123456789012',
            'requestParameters': {'bucketName': 'toy', 'key': 'folder/a.txt'}}


def test_clue_path_is_actor_independent_but_source_scoped():
    a = resource('clue-7119953', {'uid': 'a', 'params': {'path': 'files/report'}})
    b = resource('clue-7119953', {'uid': 'b', 'params': {'path': 'files/report'}})
    assert a == b
    assert a.object != token('aws', 'files/report')
    assert a.status == 'literal_path'
    assert a.container is None


def test_structured_hash_has_no_separator_collision():
    assert token('a:b', 'c') != token('a', 'b:c')


def test_s3_preserves_bucket_and_object_separately():
    event = aws()
    original = deepcopy(event)
    result = resource('aws_cloudtrail', event)
    assert result.status == 'object_key'
    assert result.object != result.container
    assert event == original
    del event['requestParameters']['key']
    bucket = resource('aws_cloudtrail', event)
    assert bucket.status == 'bucket_only'
    assert bucket.object is None
    assert bucket.container == result.container


@pytest.mark.parametrize('key', ['folder%2Fa.txt', 'folder/a.txt/', '/folder/a.txt',
                                  'folder/../folder/a.txt', 'Folder/a.txt'])
def test_s3_does_not_decode_or_resolve_keys(key):
    event = aws()
    first = resource('aws_cloudtrail', event)
    event['requestParameters']['key'] = key
    assert resource('aws_cloudtrail', event).object != first.object


@pytest.mark.parametrize('field,value', [('recipientAccountId', '222222222222'),
                                        ('requestParameters', {'bucketName': 'other', 'key': 'folder/a.txt'})])
def test_s3_scope_is_part_of_identity(field, value):
    event = aws()
    first = resource('aws_cloudtrail', event)
    event[field] = value
    second = resource('aws_cloudtrail', event)
    assert first.container != second.container
    assert first.object != second.object


@pytest.mark.parametrize('event,status', [
    ({}, 'unsupported_service'),
    ({'eventSource': 's3.amazonaws.com'}, 'missing_or_invalid_account_scope'),
    ({**aws(), 'recipientAccountId': 123456789012}, 'missing_or_invalid_account_scope'),
    ({**aws(), 'requestParameters': []}, 'missing_or_invalid_bucket'),
    ({**aws(), 'requestParameters': {'bucketName': 'toy', 'key': ''}}, 'missing_or_invalid_key'),
    ({**aws(), 'requestParameters': {'bucketName': 'toy', 'key': None}}, 'missing_or_invalid_key'),
])
def test_s3_missing_context_is_explicit(event, status):
    result = resource('aws_cloudtrail', event)
    assert result.status == status
    assert result.object is None


@pytest.mark.parametrize('params', [{}, {'path': ''}, {'path': None}, {'path': 3}, {'path': 'x' * 16385}])
def test_clue_missing_path_is_not_a_resource(params):
    assert resource('clue-7119953', {'params': params}).object is None


def test_unsupported_and_invalid_are_not_normal_fallbacks():
    assert resource('github_events', {}).status == 'unsupported_source'
    assert resource('aws_cloudtrail', None).status == 'invalid_event'
    assert resource('clue-7119953', {'params': []}).status == 'invalid_params'


def test_audit_filters_dates_population_and_anonymous_and_emits_aggregates_only():
    from scripts.audit_clue_resources import audit
    def event(uid, day, path='private-report', kind='name'):
        return {'time': f'2020-01-{day:02d}T12:00:00Z', 'uid': uid, 'uidType': kind,
                'params': {'path': path}}
    users = [hashlib.sha256(('clue-7119953:' + u).encode()).hexdigest() for u in ('a', 'b')]
    rows = [event('a', 2), event('b', 3), event('a', 2, 'private-second'),
            event('a', 1, 'before'), event('a', 4, 'after'),
            event('excluded', 2), event('a', 2, kind='ipaddress')]
    report = audit(rows, users, '2020-01-02', '2020-01-03')
    assert report['events'] == 3
    assert report['active_account_days'] == 2
    assert report['distinct_literal_path_tokens'] == 2
    assert report['tokens_seen_under_multiple_accounts'] == 1
    assert report['path_events_with_multi_account_literal_token'] == 2
    assert report['distinct_paths_per_frozen_account'] == {'min': 1, 'median': 1.5, 'max': 2}
    serialized = json.dumps(report)
    assert 'private-report' not in serialized and 'private-second' not in serialized
    assert all(u not in serialized for u in users)
    assert token('clue-7119953', 'path', 'private-report') not in serialized


def test_audit_missing_paths_remain_coverage_and_zero_paths_not_normal_score():
    from scripts.audit_clue_resources import audit
    user = hashlib.sha256(b'clue-7119953:a').hexdigest()
    result = audit([{'uid': 'a', 'uidType': 'name', 'time': '2020-01-02T12:00:00Z'}],
                   [user], '2020-01-02', '2020-01-02')
    assert result['resource_status_counts'] == {'missing_or_invalid_path': 1}
    assert result['accounts_with_observed_paths'] == 0
    assert 'score' not in result
