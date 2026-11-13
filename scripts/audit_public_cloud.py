"""Inspect pinned Ariel archives offline; never ingest, train or execute upstream code."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.normalizer import parse_aws_cloudtrail
from backend.cloud_feature_extractor import CLOUD_FEATURES, aggregate_window

REVISION = '18d3f248f4def592f4e86152c3fcb54506fbcbf6'
FILES = {
    'base_a.zip': ('base.json', '01cf810464b0818d4fb2c42b468eeac26192c8a339e73200cbc27d7346f52f64'),
    'train_labeled_a.zip': ('train_labeled.json', '09694486a5336f6771b8062e9fe269779bb91ec100214ba5f40b31f5c49b8183'),
    'labeled_cloudtrail_a.zip': ('merged_cloudtrail.json', 'd5dce3dbdb61ffb935e16cb4728aaca933daa42201a672dfad7387fd168f6eb0'),
}
LABELS = {'should_sample', 'attack_name'}


def read_records(path, member, expected_hash=None):
    path = Path(path)
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Archive exceeds inspection size bound')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_hash is not None and digest != expected_hash:
        raise ValueError('Pinned archive digest differs')
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) != 1 or entries[0].filename != member:
            raise ValueError('Unexpected archive layout')
        info = entries[0]
        parts = PurePosixPath(info.filename)
        if parts.is_absolute() or '..' in parts.parts or '\\' in info.filename:
            raise ValueError('Unsafe archive path')
        if info.file_size > 128 * 1024 * 1024 or info.flag_bits & 1:
            raise ValueError('Oversized or encrypted member')
        # Read in memory; no archive path is extracted or executed.
        with archive.open(info) as handle:
            payload = handle.read(128 * 1024 * 1024 + 1)
        if len(payload) > 128 * 1024 * 1024:
            raise ValueError('Expanded payload exceeds inspection bound')
    data = json.loads(payload)
    records = data.get('Records') if isinstance(data, dict) else None
    if not isinstance(records, list) or len(records) > 100_000 or any(not isinstance(r, dict) for r in records):
        raise ValueError('Expected a bounded Records array')
    return records, digest


def inspect(records):
    dates, types, labels, issues, scenarios = Counter(), Counter(), Counter(), Counter(), Counter()
    raw_errors = 0
    native, normalised, role_issuers = {}, {}, set()
    times, benign_times = [], []
    benign = defaultdict(lambda: defaultdict(list))
    all_user_days, attack_user_days = set(), set()
    for record in records:
        raw_errors += bool(record.get('errorCode'))
        identity = record.get('userIdentity')
        identity = identity if isinstance(identity, dict) else {}
        types[str(identity.get('type', 'missing'))] += 1
        label = record.get('should_sample')
        if type(label) is not bool:
            issues['invalid_label'] += 1
            labels['invalid'] += 1
        else:
            labels['attack' if label else 'benign'] += 1
        scenario = record.get('attack_name')
        if (label is True and (not isinstance(scenario, str) or not scenario.strip())) or (label is False and scenario):
            issues['label_scenario_mismatch'] += 1
        if label is True:
            # Count scenario strings only as aggregate labels, never as features.
            scenarios[str(scenario)] += 1
        account = record.get('recipientAccountId') or identity.get('accountId')
        event_id = record.get('eventID')
        if not isinstance(account, str) or not account:
            issues['missing_account'] += 1
        if not isinstance(event_id, str) or not event_id:
            issues['missing_event_id'] += 1
            continue
        key = (account, event_id)
        payload_hash = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if key in native:
            issues['duplicate_native_id'] += 1
            if native[key] != payload_hash:
                issues['conflicting_native_id'] += 1
            continue
        native[key] = payload_hash
        try:
            timestamp = datetime.fromisoformat(record['eventTime'].replace('Z', '+00:00'))
            if timestamp.tzinfo is None:
                raise ValueError('Timezone missing')
            timestamp = timestamp.astimezone(timezone.utc)
        except (ValueError, TypeError, KeyError, AttributeError):
            issues['invalid_timestamp'] += 1
            continue
        dates[timestamp.date().isoformat()] += 1
        times.append(timestamp.isoformat())
        # Strip evaluation labels before passing through the shared normalizer.
        clean = {k: v for k, v in record.items() if k not in LABELS}
        try:
            event = parse_aws_cloudtrail(clean)
        except Exception:
            issues['normalizer_failure'] += 1
            continue
        if not event['user'] or not account or not event['action']:
            issues['unusable_identity_or_action'] += 1
            continue
        user = (account, event['user'])
        issuer = identity.get('sessionContext', {}).get('sessionIssuer', {})
        if identity.get('type') == 'AssumedRole' and issuer.get('arn'):
            role_issuers.add(issuer['arn'])
        try:
            ipaddress.ip_address(event['ip_address'])
        except ValueError:
            issues['non_ip_address_value'] += 1
        event['timestamp'] = timestamp.isoformat()
        normalised[key] = (user, timestamp.isoformat(), label)
        pair = (user, timestamp.date().isoformat())
        all_user_days.add(pair)
        if label is True:
            attack_user_days.add(pair)
        elif label is False:
            benign[user][pair[1]].append(event)
            benign_times.append(timestamp.isoformat())
    feature_rows, users_by_day = [], defaultdict(set)
    normal_day_counts = Counter()
    benign_windows_with_attacks = 0
    for user, days in benign.items():
        normal_day_counts[len(days)] += 1
        history = []
        for day, events in sorted(days.items()):
            if (user, day) in attack_user_days:
                benign_windows_with_attacks += 1
            ordered = sorted(events, key=lambda e: e['timestamp'])
            feature_rows.append(aggregate_window(ordered, history=history))
            history.extend(ordered)
            users_by_day[day].add(user)
    features = {}
    for name in CLOUD_FEATURES:
        values = [r[name] for r in feature_rows]
        features[name] = {'min': min(values) if values else None, 'max': max(values) if values else None,
                          'positive_rows': sum(v > 0 for v in values), 'distinct_values': len(set(values))}
    summary = {'raw_records': len(records), 'unique_native_events': len(native), 'raw_labels': dict(labels),
               'raw_records_with_error_code': raw_errors,
               'identity_types': dict(types), 'issues': dict(issues), 'unique_days': len(dates),
               'unique_events_by_day': dict(sorted(dates.items())),
               'first_event_utc': min(times) if times else None, 'last_event_utc': max(times) if times else None,
               'first_usable_benign_utc': min(benign_times) if benign_times else None,
               'last_usable_benign_utc': max(benign_times) if benign_times else None,
               'usable_normalised_events': len(normalised),
               'usable_normalised_identities': len({v[0] for v in normalised.values()}),
               'assumed_role_issuer_count': len(role_issuers),
               'benign_identity_days': len(feature_rows),
               'benign_identities_by_days_observed': dict(sorted(normal_day_counts.items())),
               'benign_identities_by_day': {d: len(users) for d, users in sorted(users_by_day.items())},
               'benign_identity_days_sharing_attacks': benign_windows_with_attacks,
               'attack_identity_days': len(attack_user_days), 'scenario_counts': dict(scenarios),
               'benign_feature_diagnostics': features}
    return summary, native, normalised


def audit(directory):
    directory = Path(directory)
    summaries, natives, normalised = {}, {}, {}
    for name, (member, digest) in FILES.items():
        records, actual = read_records(directory / name, member, digest)
        summary, native, events = inspect(records)
        summary['sha256'] = actual
        summaries[name], natives[name], normalised[name] = summary, native, events
    overlaps = []
    names = list(FILES)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            shared = natives[left].keys() & natives[right].keys()
            left_days = {(user, time[:10]) for user, time, _ in normalised[left].values()}
            right_days = {(user, time[:10]) for user, time, _ in normalised[right].values()}
            overlaps.append({'left': left, 'right': right, 'shared_native_ids': len(shared),
                             'changed_shared_payloads': sum(natives[left][key] != natives[right][key] for key in shared),
                             'shared_normalised_identity_days': len(left_days & right_days)})
    normal = summaries['base_a.zip']
    tests = summaries['labeled_cloudtrail_a.zip']
    chronology = bool(normal['last_event_utc'] and tests['first_event_utc']
                      and normal['last_event_utc'] < tests['first_event_utc'])
    blockers = ['No explicit licence file/usage terms found at the pinned revision; permission unresolved.',
                'Closed-day collection coverage is not documented.']
    if normal['unique_days'] < 5:
        blockers.append('Benign-only base has fewer than five UTC dates.')
    if not chronology:
        blockers.append('Published test does not strictly follow the benign baseline in time.')
    if any(s['issues'].get('conflicting_native_id') or s['issues'].get('invalid_label')
           or s['issues'].get('label_scenario_mismatch') for s in summaries.values()):
        blockers.append('Conflicting records or invalid labels require review.')
    if any(pair['shared_native_ids'] or pair['shared_normalised_identity_days'] for pair in overlaps):
        blockers.append('Cross-file native-ID or identity-day overlap requires a split policy.')
    return {'schema_version': 1, 'repository': 'https://github.com/ArielCyber/cloud_log_sampling',
            'revision': REVISION, 'files': summaries, 'cross_file_overlap': overlaps,
            'base_strictly_precedes_test': chronology,
            'normalizer_code_sha256': hashlib.sha256((ROOT / 'backend/normalizer.py').read_bytes()).hexdigest(),
            'feature_code_sha256': hashlib.sha256((ROOT / 'backend/cloud_feature_extractor.py').read_bytes()).hexdigest(),
            'training_ready': False,
            'blockers': blockers,
            'limitations': ['Counts refer to AWS principals/sessions, not independently identified human/application users.',
                            'Feature diagnostics are audit-only; no vectors are exported for training.',
                            'Mixed-set benign-only vectors omit attack actions; they do not represent complete mixed-day evaluation inputs.',
                            'Public records never enter the live event store; no model is trained or activated.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        output = Path(args.out)
        if output.exists():
            raise ValueError('Use a new report path')
        report = audit(args.directory)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
        print(json.dumps({'training_ready': report['training_ready'], 'files_inspected': len(report['files']),
                          'raw_records': sum(r['raw_records'] for r in report['files'].values()),
                          'base_utc_days': report['files']['base_a.zip']['unique_days']}))
    except Exception:
        parser.exit(1, 'Public audit stopped; check pinned archives, bounded JSON and a new output path. No raw events displayed.\n')
