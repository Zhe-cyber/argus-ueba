from datetime import datetime, timezone
import hashlib
import json
import sqlite3

import pytest

from scripts.export_github_history import build, export

NOW = datetime(2026, 10, 29, 8, tzinfo=timezone.utc)
KEY = b'x' * 32


def record(**kwargs):
    return {'source': 'github_events', 'source_account_id': 'private-owner',
            'event_id': 'native1', 'payload_digest': 'a' * 64,
            'timestamp': '2026-10-28T03:00:00Z', 'user': 'private-login',
            'action': 'Code push (0 commits)', 'resource': 'private/repo',
            'metadata': json.dumps({'actor_id': 123}), **kwargs}


def test_legacy_zero_label_does_not_invent_commit_count():
    result = build([record()], KEY, NOW)
    row = result['rows'][0]
    assert row['features']['push_label_count'] == 1
    assert row['commit_observability']['unknown_pushes'] == 1
    assert 'all_push_commit_sum' not in row['commit_observability']
    text = json.dumps(result)
    assert all(secret not in text for secret in ['private-owner', 'private-login', 'private/repo', 'native1'])
    assert row['scoring_eligible'] is False


@pytest.mark.parametrize('count,known', [(0, 1), (2, 1), (None, 0), (True, 0), (-1, 0), ('2', 0)])
def test_known_count_requires_nonnegative_integer(count, known):
    row = build([record(metadata=json.dumps({'actor_id': 123, 'commits': count}))], KEY, NOW)['rows'][0]
    assert row['commit_observability']['known_pushes'] == known


def test_closed_my_day_weekend_partial_and_future():
    records = [record(timestamp='2026-10-23T16:00:00Z'),  # Saturday midnight MY
               record(event_id='2', timestamp='2026-10-28T16:00:00Z'),  # today MY
               record(event_id='3', timestamp='2026-10-30T00:00:00Z')]
    result = build(records, KEY, NOW)
    assert result['rows'][0]['day'] == '2026-10-24'
    assert result['rows'][0]['features']['off_hours_events'] == 1
    assert result['summary']['partial_day_events_excluded'] == 1
    assert sum(result['summary']['exclusions'].values()) == 1


def test_duplicate_and_conflicting_native_keys():
    result = build([record(), record()], KEY, NOW)
    assert result['summary']['closed_events'] == 1
    assert result['summary']['exclusions']['duplicate_native_key'] == 1
    with pytest.raises(ValueError, match='Conflicting'):
        build([record(), record(action='Issue comment')], KEY, NOW)


def test_invalid_dates_missing_evidence_empty_and_fallback():
    assert build([], KEY, NOW)['rows'] == []
    for patch in [{'timestamp': '2026-10-28T03:00:00'}, {'event_id': None}, {'payload_digest': None},
                  {'metadata': '[]'}, {'metadata': '{}', 'user': ''}]:
        assert build([record(**patch)], KEY, NOW)['rows'] == []
    result = build([record(metadata='{}')], KEY, NOW)
    assert result['rows'][0]['identity_basis'] == 'login_fallback_unverified'


def test_aliases_stable_per_key_and_identity_bases_do_not_merge():
    rows = build([record(), record(event_id='2', metadata='{}')], KEY, NOW)['rows']
    assert len(rows) == 2
    assert rows[0]['account'] != rows[1]['account']
    assert build([record()], KEY, NOW) == build([record()], KEY, NOW)
    assert build([record()], KEY, NOW) != build([record()], b'y' * 32, NOW)


def test_bot_hint_is_not_verified_provenance():
    row = build([record(user='worker[bot]')], KEY, NOW)['rows'][0]
    assert row['provenance_hints'] == {'bot_suffix_hint': 1}
    assert row['provenance'] == 'unverified'


def test_categories_and_missing_repository_remain_explicit():
    actions = ['Pull request', 'PR opened', 'Issue opened', 'Issue comment',
               'Branch/tag created', 'Branch/tag deleted', 'Repository starred']
    row = build([record(event_id=str(i), action=a, resource='') for i, a in enumerate(actions)], KEY, NOW)['rows'][0]
    assert row['features']['pull_request_label_count'] == 2
    assert row['features']['issue_label_count'] == 1
    assert row['features']['issue_comment_label_count'] == 1
    assert row['features']['ref_change_label_count'] == 2
    assert row['action_category_counts']['unclassified'] == 1
    assert row['missing_repository_events'] == len(actions)


def test_pr_review_is_not_a_pull_request_event():
    result = build([record(action='PR review')], KEY, NOW)
    assert result['contract']['profile'] == 'github_projection_daily_v2'
    assert result['rows'][0]['features']['pull_request_label_count'] == 0
    assert result['rows'][0]['action_category_counts'] == {'unclassified': 1}


def test_readonly_export_and_hashes(tmp_path):
    database, key = tmp_path / 'events.db', tmp_path / 'alias.key'
    r = record()
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, ' + ', '.join('"' + k + '" TEXT' for k in r) + ')')
        db.execute('INSERT INTO events (' + ', '.join('"' + k + '"' for k in r) + ') VALUES (' + ','.join('?' for _ in r) + ')', list(r.values()))
    before = database.read_bytes()
    key.write_bytes(KEY)
    output = tmp_path / 'export'
    manifest = export(database, output, key)
    assert database.read_bytes() == before
    assert hashlib.sha256((output / 'dataset.json').read_bytes()).hexdigest() == manifest['dataset_sha256']
    assert manifest['summary']['raw_verification_available'] is False
    with pytest.raises(ValueError, match='Fresh'):
        export(database, output, key)
