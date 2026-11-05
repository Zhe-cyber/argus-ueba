"""W33 pre-test export: fit-only cohort, chronological nine-feature rows, coverage and gates.

Offline only. No training, scoring, scenario generation or evaluator invocation.
Two bounded passes over pre-test rows: pass 1 stops after fitting and fixes the
cohort; pass 2 replays warm-up..gap to build history and emit fit/validation/
calibration rows. Warm-up and gap days update history only and emit no rows.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import clue_v2_access as access, clue_v2_features as features, clue_v2_reader as reader
from scripts.shared_core_features import instant, project_clue

SCHEMA = 'w33_pretest_export_v1'
EXPORT_SOURCES = ['specs/W33-clue-ae-v2.md', 'scripts/export_clue_v2.py', 'scripts/tests/test_clue_v2_export.py',
                  'scripts/clue_v2_features.py', 'scripts/tests/test_clue_v2_features.py'] + reader.READER_SOURCES
PARTITIONS = ['warmup', 'fit', 'validation', 'calibration', 'gap_history_only']
ROW_PARTITIONS = ('fit', 'validation', 'calibration')
GATES = {'selected_accounts': 10, 'fit_nine_feature_rows': 1000,
         'validation_nine_feature_rows': 100, 'calibration_nine_feature_rows': 100}


def partition(day):
    access.check_day(day, 'pretest')
    for name in PARTITIONS:
        lo, hi = access.POLICY[name]
        if lo <= day <= hi:
            return name
    raise ValueError('Date outside declared pre-test partitions')


def _account_days(rows, end):
    """Pass 1: distinct original active fitting days per named account; nothing after `end`."""
    days = defaultdict(set)
    for row in rows:
        day = instant(row['time']).date().isoformat()
        if day > end:
            raise ValueError('Cohort pass received a row after fitting')
        if row.get('uidType') != 'name' or partition(day) != 'fit':
            continue
        event = project_clue(row)
        days[event.account].add(event.day)
    return days


def extract(rows, cohort):
    """Pass 2: chronological history for cohort accounts; rows only for fit/validation/calibration."""
    cohort = set(cohort)
    history, windows, output, current = features.History(), {}, [], None
    coverage = {name: Counter() for name in PARTITIONS}
    issues = {name: Counter() for name in PARTITIONS}
    accounts = {name: set() for name in ROW_PARTITIONS}

    def finish():
        part = partition(current)
        for account, day in sorted(windows.items()):
            coverage[part]['observed_days'] += 1
            coverage[part]['usable_days'] += day.usable
            issues[part].update(day.core.issues)
            if part in ROW_PARTITIONS:
                snapshot = history.snapshot(day)
                coverage[part][snapshot['status']] += 1
                coverage[part]['five_feature_eligible'] += snapshot['five_feature_eligible']
                coverage[part]['nine_feature_eligible'] += snapshot['nine_feature_eligible']
                coverage[part]['no_resource_today'] += 'new_resource_share' in snapshot['unavailable']
                if snapshot['nine_feature_eligible']:
                    accounts[part].add(account)
                output.append({'partition': part, 'account': account, 'day': current, **snapshot})
        for day in windows.values():
            history.commit_original(day)

    for row in rows:
        day = instant(row['time']).date().isoformat()
        partition(day)
        if current is not None and day < current:
            raise ValueError('Cross-day reversal')
        if current is not None and day != current:
            finish()
            windows = {}
        current = day
        if row.get('uidType') != 'name':
            continue
        event = project_clue(row)
        if event.account in cohort:
            windows.setdefault(event.account, features.V2Day()).add(event)
    if current is not None:
        finish()
    summary = {name: dict(coverage[name]) for name in PARTITIONS}
    for name in PARTITIONS:
        summary[name]['issue_events'] = dict(issues[name])
    for name in ROW_PARTITIONS:
        summary[name]['nine_feature_accounts'] = len(accounts[name])
    return output, summary


def gates(cohort, summary):
    observed = {'selected_accounts': len(cohort),
                'fit_nine_feature_rows': summary['fit'].get('nine_feature_eligible', 0),
                'validation_nine_feature_rows': summary['validation'].get('nine_feature_eligible', 0),
                'calibration_nine_feature_rows': summary['calibration'].get('nine_feature_eligible', 0)}
    result = {name: {'required': GATES[name], 'observed': observed[name], 'pass': observed[name] >= GATES[name]}
              for name in GATES}
    return result, all(item['pass'] for item in result.values())


def _write(path, payload):
    with path.open('xb') as handle:
        handle.write(payload)


def export(output, stream, binding):
    """`stream(end)` yields pre-test native rows up to `end`; `binding` describes what was verified."""
    output = Path(output).resolve()
    if output.exists() or not output.is_relative_to((ROOT / 'data').resolve()):
        raise ValueError('New private directory below checkout data required')
    sources = reader.source_hashes(EXPORT_SOURCES)
    fit_end = access.POLICY['fit'][1]
    active = features.fitting_activity({account: sorted(days) for account, days in _account_days(stream(fit_end), fit_end).items()})
    cohort = features.select_cohort(active)
    rows, summary = extract(stream(reader.PRETEST_END), cohort['selected'])
    if reader.source_hashes(EXPORT_SOURCES) != sources:
        raise ValueError('Export sources changed during extraction')
    gate_results, gates_pass = gates(cohort['selected'], summary)
    encoded = {part: b''.join(access.canonical(row) + b'\n' for row in rows if row['partition'] == part)
               for part in ROW_PARTITIONS}
    cohort_document = {'profile': features.PROFILE, **cohort}
    cohort_bytes = access.canonical(cohort_document) + b'\n'
    manifest = {'schema': SCHEMA, 'profile': features.PROFILE,
                'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'binding': binding, 'source_sha256': sources,
                'feature_contract_sha256': features.contract_sha256(), 'features': features.FEATURES,
                'policy': access.POLICY,
                'cohort': {key: value for key, value in cohort.items() if key != 'selected'},
                'cohort_file_sha256': hashlib.sha256(cohort_bytes).hexdigest(),
                'partition_rows_sha256': {part: hashlib.sha256(data).hexdigest() for part, data in encoded.items()},
                'coverage': summary, 'engineering_gates': gate_results, 'engineering_gates_pass': gates_pass,
                'reserved_access': False, 'training_performed': False,
                'status': 'pretest_export_not_release' if gates_pass else 'pretest_export_gate_no_go'}
    output.mkdir(parents=True)
    _write(output / 'cohort.json', cohort_bytes)
    for part, data in encoded.items():
        _write(output / f'rows-{part}.jsonl', data)
    _write(output / 'manifest.json', access.canonical(manifest) + b'\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader-receipt', required=True)
    parser.add_argument('--availability', required=True, help='Successful monthly check bound to the same reader receipt')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        document, archive = reader.verify_reader(args.reader_receipt)
        availability_sha = reader.verify_availability(args.availability, document)
        binding = {'reader_receipt_path': str(Path(args.reader_receipt).resolve()),
                   'reader_receipt_sha256': document['receipt_sha256'],
                   'foundation_receipt_sha256': document['foundation']['receipt_sha256'],
                   'archive_sha256': access.ARCHIVE_SHA,
                   'availability_file_sha256': availability_sha}
        manifest = export(args.out, lambda end: reader.pretest_events(archive, end), binding)
        print(json.dumps({'status': manifest['status'], 'cohort': manifest['cohort'],
                          'engineering_gates': manifest['engineering_gates'], 'reserved_access': False}))
        return 0 if manifest['engineering_gates_pass'] else 2
    except (OSError, ValueError, KeyError, TypeError):
        print('W33 pre-test export failed closed; no reserved rows were read.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
