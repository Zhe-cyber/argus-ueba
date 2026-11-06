from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from zipfile import ZipFile
import pytest
from scripts import shared_core_features as f, shared_core_scenarios as scenarios
from scripts.shared_core_reader import development_events
from scripts.export_shared_core_development import export


def row(day='2017-07-15', action='file_accessed', uid='a', native=1, params=None, hour=10):
    return {'id': native, 'uidType': 'name', 'uid': uid, 'type': action,
            'time': day + f'T{hour:02d}:00:00Z', 'params': {'path': '/space/file'} if params is None else params}


def bucket(rows, synthetic=False):
    result = f.Day()
    for event in rows:
        result.add(f.project_clue(event, synthetic=synthetic))
    return result


def warm(history, uid='a'):
    for index in range(5):
        history.commit_original(bucket([row(f'2017-07-{8 + index:02d}', uid=uid, native=index + 1)]))


def test_weekend_time_only_and_exact_boundaries():
    assert f.project_clue(row(hour=10)).off_hours is False  # Saturday
    assert f.project_clue(row(hour=7)).off_hours is False
    assert f.project_clue(row(hour=19)).off_hours is True
    assert f.project_clue(row(hour=6)).off_hours is True


@pytest.mark.parametrize('action,params', [
    ('file_copied', {'oldpath': '/old/file', 'newpath': '/new/file'}),
    ('file_renamed', {'newpath': '/new/file'}),
    ('restored_from_trashbin', {'filePath': '/new/file'}),
    ('shared_link', {'fileTarget': '/new/file'}),
])
def test_native_primary_resource_fields(action, params):
    event = f.project_clue(row(action=action, params=params))
    assert event.resource == f.digest(['clue', '7119953', 'namespace', 'new'])
    assert event.issue is None


def test_resource_is_not_invented_from_uid_or_run_metadata():
    a = f.project_clue(row()); b = f.project_clue(row(uid='other'))
    assert a.resource == b.resource
    assert f.project_clue(row(action='file_created', params={'run': 'opaque'})).issue == 'missing_required_resource'
    assert f.project_clue(row(action='login_attempt', params={'user': 'a'})).resource is None
    assert f.namespace_path('/a/../b') == 'a'


def test_dedup_conflict_and_no_cross_account_day_pooling():
    original = row(); day = bucket([original])
    assert day.add(f.project_clue(original)) is False and day.count == 1
    changed = row(params={'path': '/different/file'})
    with pytest.raises(ValueError, match='Conflicting'):
        day.add(f.project_clue(changed))
    with pytest.raises(ValueError, match='Cannot mix'):
        day.add(f.project_clue(row(uid='other', native=2)))
    with pytest.raises(ValueError, match='Cannot mix'):
        day.add(f.project_clue(row(day='2017-07-16', native=2)))


def test_cold_start_counts_observed_days_and_never_zero_fills():
    history = f.History()
    for index, date in enumerate(['2017-07-01', '2017-07-03', '2017-07-07', '2017-07-10', '2017-07-12']):
        day = bucket([row(date, native=index + 1)])
        assert history.snapshot(day)['features'] is None
        history.commit_original(day)
    assert history.snapshot(bucket([row()]))['eligible'] is True
    with pytest.raises(ValueError, match='advance'):
        history.commit_original(bucket([row('2017-07-12')]))


def test_same_snapshot_variants_cannot_contaminate_next_day_history():
    history = f.History(); warm(history)
    original = bucket([row()])
    variant = bucket([row(action='permission_changed')])
    assert history.snapshot(variant)['features']['new_action_count'] == 1
    assert history.snapshot(original)['features']['new_action_count'] == 0
    history.commit_original(original)
    next_day = bucket([row('2017-07-16', action='permission_changed')])
    assert history.snapshot(next_day)['features']['new_action_count'] == 1


def test_resource_gap_makes_whole_day_incompatible_without_dropping_events():
    history = f.History(); warm(history)
    day = bucket([row(), row(action='file_written', params={'run': 1}, native=2)])
    result = history.snapshot(day)
    assert not result['cold_start'] and not result['eligible'] and result['features'] is None
    assert day.count == 2 and result['issues'] == {'missing_required_resource': 1}


def live(source, action, resource='repo/name', metadata=None, timestamp='2026-10-30T01:00:00Z'):
    return {'source': source, 'source_account_id': 'scope', 'account_key': 'acct_' + 'a' * 64,
            'event_id': 'event', 'payload_digest': 'b' * 64, 'timestamp': timestamp,
            'action': action, 'resource': resource, 'metadata': metadata or {}}


def test_github_mapping_preserves_review_and_rejects_unknown_labels():
    assert f.github_kind('PR review') == 'PullRequestReviewEvent'
    assert f.github_kind('PR opened') == 'PullRequestEvent'
    assert f.github_kind('Code push (2 commits)') == 'PushEvent'
    with pytest.raises(ValueError):
        f.github_kind('Unrecognised action')
    assert f.project_live(live('github_events', 'Unrecognised action')).issue == 'unknown_action'


def test_live_timezone_and_cloudflare_action_do_not_infer_login_success():
    event = f.project_live(live('cloudflare_access', 'login (denied)', resource='app.example.com'))
    assert event.action == 'login' and event.issue is None and event.off_hours is False
    late = f.project_live(live('cloudflare_access', 'login', resource='app.example.com', timestamp='2026-10-30T16:01:00Z'))
    assert late.day == '2026-10-31' and late.off_hours
    assert f.project_live(live('cloudflare_access', 'access')).issue == 'native_action_missing_or_default_ambiguous'


def test_live_aws_resource_policy_and_unattributed_input_fail_closed():
    valid = f.project_live(live('aws_cloudtrail', 'GetObject', 'toy-bucket', {'eventSource': 's3.amazonaws.com'}))
    assert valid.issue is None and valid.action == 's3.amazonaws.com:GetObject'
    uncertain = f.project_live(live('aws_cloudtrail', 'AssumeRole', "{'roleArn': 'arn:example'}", {'eventSource': 'sts.amazonaws.com'}))
    assert uncertain.issue == 'unsupported_service_resource_semantics'
    invalid = live('github_events', 'Code push'); invalid['account_key'] = 'a display label'
    with pytest.raises(ValueError):
        f.project_live(invalid)


def test_native_scenario_transformations_are_deterministic_and_leave_originals_untouched():
    original = [row(native=1), row(native=2, action='login_successful', params={})]
    saved = deepcopy(original)
    mass, status = scenarios.generate('mass_access', original, 'account', '2017-07-15', set())
    assert status == 'generated' and len(mass) == 6
    assert sum(event['type'] == 'file_accessed' for event in mass) == 5
    assert scenarios.generate('mass_access', original, 'account', '2017-07-15', set())[0] == mass
    assert original == saved
    assert bucket(mass, synthetic=True).count == 6
    new, _ = scenarios.generate('new_action', original, 'account', '2017-07-15', set())
    assert sum(event['type'] == 'permission_changed' for event in new) == 5
    assert len({event['id'] for event in new}) == len(new)
    assert scenarios.generate('new_action', original, 'account', '2017-07-15', {'permission_changed'})[0] is None


def test_off_hours_and_switch_keep_day_and_target_history_semantics():
    rows = [row(native=1), row(native=2, hour=11)]
    shifted, _ = scenarios.generate('off_hours', rows, 'account', '2017-07-15', set())
    assert all(f.instant(event['time']).date().isoformat() == '2017-07-15' for event in shifted)
    assert bucket(shifted, synthetic=True).features(set())['off_hours_fraction'] == 1
    assert scenarios.generate('off_hours', [row(hour=2)], 'a', '2017-07-15', set())[0] is None
    donor = [row(uid='donor', native=9, action='permission_changed')]
    switched, _ = scenarios.generate('account_switch', rows, 'a', '2017-07-15', set(), donor=donor)
    assert switched[0]['uid'] == 'a' and donor[0]['uid'] == 'donor'
    assert bucket(switched, synthetic=True).features({'file_accessed'})['new_action_count'] == 1
    pairs = scenarios.pairs([str(index) for index in range(55)])
    assert len(pairs) == 27 and len({account for pair in pairs for account in pair}) == 54
    assert pairs == scenarios.pairs([str(index) for index in reversed(range(55))])


def zip_rows(path, rows, member='clue.json'):
    with ZipFile(path, 'w') as archive:
        archive.writestr(member, ''.join(json.dumps(event) + '\n' for event in rows))


def test_reader_stops_before_boundary_and_refuses_reserved_access(tmp_path):
    path = tmp_path / 'test.zip'
    zip_rows(path, [row('2017-08-09', native=1), row('2017-08-10', native=2), row('2017-08-11', native=3)])
    assert [event['id'] for event in development_events(path)] == [1]
    with pytest.raises(ValueError, match='Reserved'):
        list(development_events(path, end_exclusive='2017-08-25'))


def test_reader_rejects_unsafe_member_and_cross_day_reversal(tmp_path):
    path = tmp_path / 'test.zip'; zip_rows(path, [row()], '../clue.json')
    with pytest.raises(ValueError, match='member'):
        list(development_events(path))
    zip_rows(path, [row('2017-07-15', native=1), row('2017-07-14', native=2)])
    with pytest.raises(ValueError, match='reversal'):
        list(development_events(path))


def test_export_excludes_reserved_dates_without_using_them_for_history():
    rows = [row(f'2017-07-{8 + index:02d}', native=index + 1) for index in range(5)] + [row()]
    account = f.project_clue(rows[0]).account
    first = export(rows, {account})
    second = export(rows + [row('2017-08-11', action='permission_changed', native=100)], {account})
    assert first == second and first['reserved_access'] is False
    assert first['rows'][-1]['features']['event_count'] == 1
