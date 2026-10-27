"""Public-data audit fixtures only; never download data or call live ingestion."""
from copy import deepcopy
import json
import zipfile

import pytest

from scripts import audit_public_cloud as public


def event(identifier='id-1', timestamp='2020-01-01T12:00:00Z', attack=False):
    record = {'eventID': identifier, 'eventTime': timestamp, 'eventName': 'GetObject',
              'recipientAccountId': '123456789012',
              'userIdentity': {'type': 'IAMUser', 'accountId': '123456789012', 'userName': 'fixture'},
              'requestParameters': {'bucketName': 'toy'}, 'sourceIPAddress': '203.0.113.1',
              'should_sample': attack}
    if attack: record['attack_name'] = 'FixtureScenario'
    return record


def write_zip(path, member, records):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, json.dumps({'Records': records}))


def test_duplicates_conflicts_and_cross_account_keys():
    normal = event()
    changed = deepcopy(normal)
    changed['eventName'] = 'HeadObject'
    other_account = deepcopy(normal)
    other_account['recipientAccountId'] = '111111111111'
    summary, native, _ = public.inspect([normal, deepcopy(normal), changed, other_account])
    assert len(native) == 2
    assert summary['issues']['duplicate_native_id'] == 2
    assert summary['issues']['conflicting_native_id'] == 1


def test_labels_are_strict_and_never_enter_features(monkeypatch):
    received = []
    original = public.parse_aws_cloudtrail
    def normalise(record):
        assert not public.LABELS & record.keys()
        received.append(record)
        return original(record)
    monkeypatch.setattr(public, 'parse_aws_cloudtrail', normalise)
    invalid = event('bad-label')
    invalid['should_sample'] = 'False'
    summary, _, _ = public.inspect([event(), event('attack', attack=True), invalid])
    assert summary['issues']['invalid_label'] == 1
    assert summary['benign_identity_days'] == 1
    assert summary['benign_identity_days_sharing_attacks'] == 1
    assert summary['benign_feature_diagnostics']['event_count']['max'] == 1
    assert len(received) == 3


def test_history_uses_prior_utc_day_without_manufacturing_days():
    records = [event(), event('id-2', '2020-01-02T00:30:00+01:00'), event('id-3', '2020-01-02T12:00:00Z')]
    summary, _, _ = public.inspect(records)
    assert summary['unique_days'] == 2
    assert summary['unique_events_by_day']['2020-01-01'] == 2
    assert summary['benign_identities_by_days_observed'] == {2: 1}
    assert summary['benign_feature_diagnostics']['new_action_count'] == {'min': 0.0, 'max': 1.0, 'positive_rows': 1, 'distinct_values': 2}


@pytest.mark.parametrize('fault', ['digest', 'path', 'shape', 'layout'])
def test_archive_safety_and_pinned_digest(tmp_path, fault):
    path = tmp_path / 'fixture.zip'
    member = '../records.json' if fault == 'path' else 'records.json'
    write_zip(path, member, [event()])
    if fault == 'shape':
        with zipfile.ZipFile(path, 'w') as archive: archive.writestr(member, '{"Records": {}}')
    with pytest.raises(ValueError):
        public.read_records(path, 'other.json' if fault == 'layout' else member,
                            '0' * 64 if fault == 'digest' else None)


def test_audit_reports_overlaps_and_nonchronological_test(tmp_path, monkeypatch):
    names = ['base_a.zip', 'train_labeled_a.zip', 'labeled_cloudtrail_a.zip']
    files = {}
    for name in names:
        path = tmp_path / name
        write_zip(path, 'records.json', [event()])
        files[name] = ('records.json', public.hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(public, 'FILES', files)
    report = public.audit(tmp_path)
    assert report['training_ready'] is False
    assert report['base_strictly_precedes_test'] is False
    assert all(pair['shared_native_ids'] == 1 and pair['shared_normalised_identity_days'] == 1
               for pair in report['cross_file_overlap'])


def test_clue_prefix_counts_named_pseudonyms_without_treating_ips_as_people(tmp_path):
    from scripts.audit_clue_prefix import inspect
    rows = [{'id': i, 'time': f'2020-01-0{i}T12:00:00Z', 'type': 'file_accessed',
             'uid': 'fixture', 'uidType': 'name' if i < 3 else 'ipaddress'} for i in range(1, 4)]
    path = tmp_path / 'prefix.zip'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('clue.json', ''.join(json.dumps(row) + '\n' for row in rows))
    report = inspect(path)
    assert report['sample_records'] == 3
    assert report['named_users'] == 1 and report['named_identity_days'] == 2
    assert report['training_ready'] is False
    assert 'fixture' not in json.dumps(report)


def test_clue_prefix_refuses_unexpected_member(tmp_path):
    from scripts.audit_clue_prefix import inspect
    path = tmp_path / 'prefix.zip'
    write_zip(path, '../clue.json', [event()])
    with pytest.raises(ValueError): inspect(path)
