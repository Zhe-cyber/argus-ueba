"""Document compatibility counterexamples without changing the frozen extractor."""
import json
import zipfile

from scripts.probe_cloud_contract import clue_projection, probes


def test_frozen_contract_counterexamples_are_reproducible():
    result = probes()
    assert result['aws_denied_error_events'] == result['aws_success_error_events'] == 0
    assert result['aws_two_keys_unique_resources'] == 1
    assert result['aws_sts_get_caller_identity_iam_sts_events'] == 0
    assert result['cloudflare_denied_error_events'] == 1
    assert result['github_ip_field_present'] is False and result['github_unique_ips_value'] == 0
    assert result['clue_file_access_data_exfil_events'] == 0
    assert result['first_day_new_action_count'] == 1 and result['later_day_same_action_count'] == 0
    assert result['runtime_changed'] is False and result['training_ready'] is False


def test_projection_preserves_missingness_in_report_and_excludes_anonymous_users(tmp_path):
    events = [{'id': i, 'time': f'2020-01-0{i}T12:00:00Z', 'uid': 'fixture',
               'uidType': 'name' if i < 3 else 'ipaddress', 'type': 'file_accessed',
               'params': {'path': '/opaque/path'}} for i in range(1, 4)]
    path = tmp_path / 'prefix.zip'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('clue.json', ''.join(json.dumps(row) + '\n' for row in events))
    result = clue_projection(path)
    assert result['identity_days'] == 2
    assert result['field_coverage']['named_events'] == 2
    assert result['field_coverage']['events_with_ip_address_field'] == 0
    assert result['frozen_feature_diagnostics']['unique_ips']['positive_rows'] == 0
    assert result['training_ready'] is False
