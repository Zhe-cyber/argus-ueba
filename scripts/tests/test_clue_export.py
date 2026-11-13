from copy import deepcopy
import json
import zipfile

import pytest

from scripts.clue_features import FEATURES, SHARING, Window
from scripts import export_clue_dataset as clue


def event(i, day, user='fixture', action='file_accessed', kind='name'):
    return {'id': i, 'time': f'2020-01-{day:02d}T12:00:00Z', 'uid': user,
            'uidType': kind, 'type': action, 'params': {'path': '/opaque/path'}}


def archive(path, events):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('clue.json', ''.join(json.dumps(e)+'\n' for e in events))


def test_native_categories_and_attempt_is_not_failure():
    window = Window()
    actions = ['file_accessed', 'login_attempt', 'login_successful', 'permission_changed',
               'unreviewed_action', 'public_share_accessed', *sorted(SHARING)]
    for i, action in enumerate(actions): window.add(event(i+1, 6, action=action))
    values = window.finish({'file_accessed'})
    assert list(values) == FEATURES and len(values) == 10
    assert values['event_count'] == len(actions)
    assert values['sharing_events'] == 8 and values['login_attempt_events'] == 1
    assert values['permission_change_events'] == 1 and values['unique_paths'] == 1
    assert values['new_action_count'] == len(actions)-1
    assert window.unknown_actions == 1
    assert 'error_events' not in values and 'unique_ips' not in values


def test_export_native_days_boundaries_privacy_history_and_unknown_coverage(tmp_path):
    path = tmp_path/'prefix.zip'
    rows = [event(1, 1), event(2, 2), event(3, 2, kind='ipaddress'),
            event(4, 3, action='unreviewed_action'), event(5, 4)]
    archive(path, rows)
    output = tmp_path/'features.json'
    result = clue.export(path, output)
    assert len(result['rows']) == 4
    assert [r['features']['new_action_count'] for r in result['rows']] == [1, 0, 1, 0]
    assert [r['capture_boundary'] for r in result['rows']] == [True, False, False, True]
    assert result['rows'][2]['coverage']['unknown_action_events'] == 1
    assert result['provenance']['excluded_ip_identity_events'] == 1
    assert '/opaque/path' not in output.read_text() and '"fixture"' not in output.read_text()
    with pytest.raises(ValueError): clue.export(path, output)


@pytest.mark.parametrize('fault', ['duplicate_id', 'missing_timezone', 'invalid_identity', 'oversized_line'])
def test_reader_refuses_invalid_prefix_data(tmp_path, fault):
    rows = [event(1, 1), event(2, 2)]
    if fault == 'duplicate_id': rows[1]['id'] = 1
    elif fault == 'missing_timezone': rows[1]['time'] = '2020-01-02T12:00:00'
    elif fault == 'invalid_identity': rows[1]['uidType'] = 'invented'
    else: rows[1]['params']['path'] = 'x'*300000
    path = tmp_path/'prefix.zip'
    archive(path, rows)
    with pytest.raises(ValueError): list(clue.Prefix(path).events())


def test_preserves_out_of_order_times_and_flags_cross_day_reversal(tmp_path):
    path = tmp_path/'prefix.zip'
    archive(path, [event(1, 2), event(2, 1), event(3, 3)])
    result = clue.export(path, tmp_path/'features.json')
    assert result['provenance']['first_capture_day'] == '2020-01-01'
    assert result['provenance']['day_reversal_events'] == 1
    assert clue.readiness(result, ['2020-01-02','2020-01-08','2020-01-09','2020-01-10','2020-01-11'])['operationally_ready'] is False


def document():
    rows = []
    for d in range(1, 13):
        for user in range(6):
            rows.append({'user': str(user), 'date': f'2020-01-{d:02d}', 'capture_boundary': d in (1,12),
                         'features': dict.fromkeys(FEATURES, 1),
                         'coverage': {'unknown_action_events': 0, 'missing_required_paths': 0}})
    return {'profile': clue.PROFILE, 'features': FEATURES, 'rows': rows,
            'provenance': {'last_capture_day': '2020-01-12'}}


def test_fitting_only_population_and_chronological_readiness():
    data = document()
    cutoffs = ['2020-01-02','2020-01-07','2020-01-08','2020-01-09','2020-01-11']
    result = clue.readiness(data, cutoffs)
    assert result['operationally_ready'] is True
    assert result['eligible_fitting_users'] == 6
    assert [p['rows'] for p in result['partitions']] == [6,30,6,6,12]
    # Extra future-only users cannot change the selected fitting population.
    extra = deepcopy(data['rows'][-7])
    extra['user'], extra['date'], extra['capture_boundary'] = 'future-only', '2020-01-10', False
    data['rows'].append(extra)
    other = clue.readiness(data, cutoffs)
    assert other['eligible_fitting_users'] == 6 and other['partitions'] == result['partitions']
    assert other['excluded_population_rows'] == 1
    assert clue.readiness(data, cutoffs[:-1] + ['2020-01-12'])['operationally_ready'] is False
    data['rows'][7]['coverage']['missing_required_paths'] = 1
    assert clue.readiness(data, cutoffs)['operationally_ready'] is False


def test_stream_limits_stop_at_whole_record_and_boundaries(tmp_path, monkeypatch):
    path = tmp_path/'prefix.zip'
    archive(path, [event(i, i) for i in range(1,5)])
    monkeypatch.setattr(clue, 'MAX_EVENTS', 2)
    prefix = clue.Prefix(path)
    assert len(list(prefix.events())) == 2 and prefix.stop_reason == 'event_limit'
    with pytest.raises(ValueError): clue.readiness(document(), ['2020-01-02']*5)
