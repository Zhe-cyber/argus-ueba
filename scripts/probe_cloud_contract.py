"""Offline feature counterexamples and optional CLUE projection; never a training adapter."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.cloud_feature_extractor import CLOUD_FEATURES, aggregate_window
from backend.normalizer import parse_aws_cloudtrail, parse_cloudflare_access, parse_github_events
from scripts.audit_clue_prefix import inspect, prefix_lines


def probes():
    base = {'eventTime': '2020-01-06T12:00:00Z', 'eventName': 'GetObject',
            'eventSource': 's3.amazonaws.com', 'userIdentity': {'type': 'IAMUser', 'userName': 'fixture'},
            'requestParameters': {'bucketName': 'toy', 'key': 'one.txt'}, 'sourceIPAddress': '203.0.113.1'}
    denied = parse_aws_cloudtrail({**base, 'errorCode': 'AccessDenied'})
    allowed = parse_aws_cloudtrail(base)
    other_key = parse_aws_cloudtrail({**base, 'requestParameters': {'bucketName': 'toy', 'key': 'two.txt'}})
    sts = parse_aws_cloudtrail({**base, 'eventName': 'GetCallerIdentity', 'eventSource': 'sts.amazonaws.com', 'requestParameters': {}})
    cf = parse_cloudflare_access({'action': 'login', 'allowed': False, 'created_at': base['eventTime'],
                                  'user_email': 'fixture@example.invalid', 'app_domain': 'toy.example.invalid'})
    gh = parse_github_events({'id': 'fixture', 'type': 'PushEvent', 'created_at': base['eventTime'],
                              'actor': {'login': 'fixture'}, 'repo': {'name': 'fixture/toy'},
                              'payload': {'size': 1}})
    # Minimal diagnostic projection only. This does not register a CLUE normalizer.
    clue = {'source': 'clue_lds_diagnostic', 'user': 'fixture', 'timestamp': base['eventTime'],
            'action': 'file_accessed', 'resource': '/opaque/pseudonymous/path', 'ip_address': '', 'metadata': {}}
    return {'aws_denied_error_events': aggregate_window([denied], history=[])['error_events'],
            'aws_success_error_events': aggregate_window([allowed], history=[])['error_events'],
            'aws_two_keys_unique_resources': aggregate_window([allowed, other_key], history=[])['unique_resources'],
            'aws_sts_get_caller_identity_iam_sts_events': aggregate_window([sts], history=[])['iam_sts_events'],
            'cloudflare_denied_error_events': aggregate_window([cf], history=[])['error_events'],
            'github_ip_field_present': bool(gh['ip_address']),
            'github_unique_ips_value': aggregate_window([gh], history=[])['unique_ips'],
            'clue_file_access_data_exfil_events': aggregate_window([clue], history=[])['data_exfil_events'],
            'first_day_new_action_count': aggregate_window([allowed], history=[])['new_action_count'],
            'later_day_same_action_count': aggregate_window([allowed], history=[allowed])['new_action_count'],
            'training_ready': False, 'runtime_changed': False}


def clue_projection(path):
    structure = inspect(path)  # Validate the bounded schema/times first.
    _, _, lines = prefix_lines(path)
    days = defaultdict(lambda: defaultdict(list))
    fields = Counter()
    for line in lines:
        row = json.loads(line)
        if row['uidType'] != 'name':
            continue
        params = row.get('params')
        params = params if isinstance(params, dict) else {}
        resource = params.get('path')
        resource = resource if isinstance(resource, str) else ''
        fields['named_events'] += 1
        fields['events_with_path'] += bool(resource)
        fields['events_with_location'] += isinstance(row.get('location'), dict)
        fields['events_with_ip_address_field'] += bool(row.get('ip_address'))
        instant = datetime.fromisoformat(row['time'].replace('Z', '+00:00')).astimezone(timezone.utc)
        event = {'source': 'clue_lds_diagnostic', 'timestamp': instant.isoformat(),
                 'user': row['uid'], 'action': row['type'], 'resource': resource,
                 'ip_address': '', 'metadata': {}}
        days[row['uid']][instant.date().isoformat()].append(event)
    vectors = []
    for by_day in days.values():
        history = []
        for _, window in sorted(by_day.items()):
            vectors.append(aggregate_window(window, history=history))
            history.extend(window)
    diagnostics = {}
    for name in CLOUD_FEATURES:
        values = [row[name] for row in vectors]
        diagnostics[name] = {'positive_rows': sum(v > 0 for v in values),
                             'distinct_values': len(set(values)),
                             'min': min(values) if values else None, 'max': max(values) if values else None}
    return {'sample_sha256': structure['prefix_sha256'], 'identity_days': len(vectors),
            'field_coverage': dict(fields), 'frozen_feature_diagnostics': diagnostics,
            'training_ready': False,
            'limitations': 'Naive diagnostic projection only, not an approved adapter. Missing IPs become zero '
                          'solely to demonstrate the existing extractor mismatch. No model input file is emitted.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clue-prefix')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    report = {'schema_version': 1, 'fixture_probes': probes()}
    if args.clue_prefix:
        report['clue_diagnostic'] = clue_projection(args.clue_prefix)
    with Path(args.out).open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print(json.dumps({'probes_completed': True, 'clue_sample_checked': bool(args.clue_prefix), 'training_ready': False}))
