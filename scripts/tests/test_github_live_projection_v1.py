"""Live projection parity, malformed provenance and chronological history tests."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from backend.github_activity import normalize_activity, ACTIONS
from scripts import github_live_projection_v1 as projection
from scripts import shared_core_features as frozen, shared_core_live_guard as guard
from scripts import audit_clue_v2_live as audit


def row(kind='push', day='2026-10-20', activity_id=123, repo_id=99, scope='github-owner:77'):
    raw = {'id': activity_id, 'actor': {'id': 55, 'login': 'example[bot]', 'type': 'Bot'},
           'activity_type': kind, 'timestamp': day + 'T03:00:00Z',
           'before': '0' * 40, 'after': 'a' * 40, 'ref': 'refs/heads/main'}
    event = normalize_activity(raw, 'example/toy', repo_id)
    return {k: event[k] for k in ('source', 'timestamp', 'action', 'resource', 'event_id', 'metadata')} | {
        'source_account_id': scope, 'account_key': 'acct_' + 'a' * 64,
        'payload_digest': frozen.digest(raw), 'ingested_at': day + 'T03:05:00Z'}


@pytest.mark.parametrize('kind', sorted(projection.LABELS))
def test_actual_normalizer_output_is_supported_without_frozen_mapping_change(kind):
    native = row(kind)
    assert projection.LABELS == ACTIONS
    event = guard.project_live(native)
    assert event.issue is None and event.action == 'repository_activity:' + kind
    assert event.source == native['source'] and event.scope == native['source_account_id']
    assert event.account == native['account_key'] and event.reference == native['event_id']
    assert event.payload_digest == native['payload_digest']
    assert event.resource == frozen.project_live(native).resource
    with pytest.raises(ValueError):
        frozen.github_kind(native['action'])


@pytest.mark.parametrize('field,value,issue', [
    ('evidence_format', 'other_v1', 'unsupported_native_activity_provenance'),
    ('provider_endpoint', 'events', 'unsupported_native_activity_provenance'),
    ('provider_api_version', None, 'unsupported_native_activity_provenance'),
    ('repository_context_basis', 'guess', 'unsupported_native_activity_provenance'),
    ('activity_type', 'future_kind', 'unknown_action'),
    ('activity_type', ['push'], 'unknown_action'),
    ('repository_id', True, 'native_activity_identity_mismatch'),
    ('native_activity_id', 124, 'native_activity_identity_mismatch'),
    ('actor_id', 0, 'native_activity_identity_mismatch'),
    ('before', 'bad', 'invalid_native_activity_reference'),
    ('ref', 'main', 'invalid_native_activity_reference'),
])
def test_bad_native_metadata_is_an_invalid_day_not_guessed(field, value, issue):
    native = row()
    native['metadata'][field] = value
    assert guard.project_live(native).issue == issue


def test_display_label_alone_is_not_native_evidence():
    native = row()
    native['metadata'] = '{}'
    assert guard.project_live(native).issue == 'unknown_action'
    native = row()
    native['action'] = 'Repository force push'
    assert guard.project_live(native).issue == 'native_activity_label_mismatch'


@pytest.mark.parametrize('resource', ['', 'a/b/c', '../toy', 'owner/repo name'])
def test_resource_quality_is_not_overridden(resource):
    native = row()
    native['resource'] = resource
    assert guard.project_live(native).issue == 'missing_required_resource'


def test_json_metadata_and_existing_events_api_projection_remain_distinct():
    native = row()
    native['metadata'] = json.dumps(native['metadata'])
    assert guard.project_live(native).action == 'repository_activity:push'
    events_api = dict(native, event_id='9876', action='Code push (2 commits)', metadata='{}')
    assert guard.project_live(events_api) == frozen.project_live(events_api)
    assert guard.project_live(events_api).action == 'PushEvent'


def test_real_shaped_activity_reaches_live_history_without_adding_records():
    rows = [row(day=f'2026-10-{day:02}', activity_id=day) for day in range(20, 27)]
    before = deepcopy(rows)
    built, exclusions, labels = audit.closed_days(rows + [deepcopy(rows[0])],
                                                datetime(2026, 10, 30, tzinfo=timezone.utc))
    snapshots = audit.snapshots(built)
    assert rows == before
    assert sum(day.core.count for day in built.values()) == 7  # Native duplicate counted once.
    assert [s['status'] for s in snapshots] == ['cold_start'] * 5 + ['eligible'] * 2
    assert not exclusions and not labels
    assert snapshots[-1]['features']['unique_actions'] == 1


def test_scope_separation_and_conflicting_native_id_are_preserved():
    a = row()
    b = row(scope='github-owner:88')
    assert guard.project_live(a).resource != guard.project_live(b).resource
    built, _, _ = audit.closed_days([a, b], datetime(2026, 10, 30, tzinfo=timezone.utc))
    assert len(built) == 2
    conflict = dict(a, payload_digest='f' * 64)
    with pytest.raises(ValueError, match='Conflicting native event ID'):
        audit.closed_days([a, conflict], datetime(2026, 10, 30, tzinfo=timezone.utc))
