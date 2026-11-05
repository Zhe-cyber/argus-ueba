"""W33 validation descriptive report tests on handcrafted export rows."""
import hashlib
import json

import pytest

from scripts import clue_v2_features as features, report_clue_v2_validation as report


def eligible(account, day, share, mix=0.2, hours=0.3, volume=0.0):
    values = dict.fromkeys(features.FEATURES, 1)
    values.update(volume_log_ratio=volume, new_resource_share=share, action_mix_js_distance=mix,
                  hour_profile_js_distance=hours)
    unavailable = {} if share is not None else {'new_resource_share': 'no_resource_today'}
    return {'partition': 'validation', 'account': account, 'day': day, 'status': 'eligible',
            'features': values, 'unavailable': unavailable}


def rows():
    return [eligible('user-1', '2017-11-27', 0.0), eligible('user-1', '2017-11-28', 0.25), eligible('user-2', '2017-11-27', 0.5),
            eligible('user-3', '2017-12-03', 1.0, mix=1.0), eligible('user-4', '2017-11-29', None),
            {'partition': 'validation', 'account': 'user-5', 'day': '2017-11-30', 'status': 'cold_start',
             'features': None, 'unavailable': {}},
            {**eligible('fit-only', '2017-09-04', 0.9), 'partition': 'fit'},
            {**eligible('cal-only', '2017-12-04', 0.9), 'partition': 'calibration'}]


def test_statistics_use_only_validation_rows_with_higher_quantiles():
    result = report.describe(rows())
    assert result['validation_observed_rows'] == 6 and result['validation_observed_accounts'] == 5
    share = result['features']['new_resource_share']
    assert share['available_rows'] == 4 and share['accounts_with_value'] == 3
    assert share['unavailable_rows'] == {'cold_start': 1, 'no_resource_today': 1}
    assert (share['min'], share['p25'], share['median'], share['max']) == (0.0, 0.25, 0.5, 1.0)
    assert share['exact_zero_fraction'] == 0.25 and share['exact_one_fraction'] == 0.25
    assert share['distinct_values'] == 4
    mix = result['features']['action_mix_js_distance']
    assert mix['available_rows'] == 5 and mix['exact_one_fraction'] == 0.2
    assert 'exact_zero_fraction' not in result['features']['volume_log_ratio']


@pytest.mark.parametrize('bad', [
    {**eligible('x', '2017-12-04', 0.1)},                              # calibration date labelled validation
    {**eligible('x', '2018-01-15', 0.1)},                              # reserved date
    {**eligible('x', '2017-11-27', 0.1), 'partition': 'reserved'},
    {**eligible('user-1', '2017-11-27', 0.1)},                             # duplicate account-day
])
def test_non_validation_or_duplicate_observations_are_refused(bad):
    with pytest.raises(ValueError):
        report.describe(rows() + [bad])


def test_nonfinite_values_are_counted_not_summarised():
    data = rows()
    data[0]['features']['volume_log_ratio'] = float('nan')
    stats = report.describe(data)['features']['volume_log_ratio']
    assert stats['nonfinite_rows'] == 1 and stats['available_rows'] == 4


def write_export(directory, data, contract=None):
    directory.mkdir(parents=True)
    body = b''.join(json.dumps(r).encode() + b'\n' for r in data if r['partition'] == 'validation')
    (directory / 'rows-validation.jsonl').write_bytes(body)
    (directory / 'manifest.json').write_text(json.dumps({
        'schema': 'w33_pretest_export_v1', 'reserved_access': False,
        'partition_rows_sha256': {'validation': hashlib.sha256(body).hexdigest()},
        'feature_contract_sha256': contract or features.contract_sha256()}))


def test_report_file_is_aggregate_bound_and_exclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(report, 'ROOT', tmp_path)
    write_export(tmp_path / 'data/export', rows())
    output = tmp_path / 'results/clue-ae-v2/validation-feature-descriptives.md'
    report.report(tmp_path / 'data/export', output)
    text = output.read_text(encoding='utf-8')
    assert 'new_resource_share' in text and 'validation_rows_sha256' in text
    assert not any(account in text for account in ['user-1', 'user-2', 'user-3', 'user-4', 'user-5'])
    with pytest.raises(ValueError):
        report.report(tmp_path / 'data/export', output)


def test_report_refuses_mismatched_export(tmp_path, monkeypatch):
    monkeypatch.setattr(report, 'ROOT', tmp_path)
    write_export(tmp_path / 'data/export', rows(), contract='0' * 64)
    with pytest.raises(ValueError, match='binding'):
        report.report(tmp_path / 'data/export', tmp_path / 'results/out.md')


def test_validation_file_cannot_silently_ignore_other_partitions(tmp_path, monkeypatch):
    monkeypatch.setattr(report, 'ROOT', tmp_path)
    directory=tmp_path/'data/export';write_export(directory,rows())
    body=(directory/'rows-validation.jsonl').read_bytes()
    body+=json.dumps({**eligible('other','2017-12-04',0.1),'partition':'calibration'}).encode()+b'\n'
    (directory/'rows-validation.jsonl').write_bytes(body)
    manifest=json.loads((directory/'manifest.json').read_bytes())
    manifest['partition_rows_sha256']['validation']=hashlib.sha256(body).hexdigest()
    (directory/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='another partition'):
        report.report(directory,tmp_path/'results/out.md')
