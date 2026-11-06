"""W33 validation-only descriptive report for features 6-9. Descriptive, never a selection input.

Reads the private pre-test export, uses only original validation rows
(27 Nov-3 Dec 2017), and writes aggregate statistics without account identifiers.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import clue_v2_access as access, clue_v2_features as features, clue_v2_reader as reader

REPORTED = features.FEATURES[5:]
BOUNDED = ('new_resource_share', 'action_mix_js_distance', 'hour_profile_js_distance')
QUANTILES = [('p05', 0.05), ('p25', 0.25), ('median', 0.5), ('p75', 0.75), ('p95', 0.95)]
REPORT_SOURCES = ['scripts/report_clue_v2_validation.py', 'scripts/tests/test_clue_v2_validation_report.py']
DEFAULT_OUTPUT = 'results/clue-ae-v2/validation-feature-descriptives.md'


def validation_rows(rows):
    """Original validation observations only; any mislabelled or reserved row fails closed."""
    selected = []
    for row in rows:
        part = row.get('partition')
        if part not in ('fit', 'validation', 'calibration'):
            raise ValueError('Unexpected partition in pre-test export')
        if part != 'validation':
            continue
        access.check_day(row.get('day'), 'validation_report')
        if not isinstance(row.get('account'), str) or row.get('status') not in ('eligible', 'cold_start', 'invalid_input'):
            raise ValueError('Invalid validation row')
        selected.append(row)
    if len({(row['account'], row['day']) for row in selected}) != len(selected):
        raise ValueError('Duplicate validation account-day')
    return selected


def describe(rows):
    rows = validation_rows(rows)
    accounts = {row['account'] for row in rows}
    result = {'validation_observed_rows': len(rows), 'validation_observed_accounts': len(accounts),
              'status_counts': dict(sorted(Counter(row['status'] for row in rows).items())), 'features': {}}
    for name in REPORTED:
        values, reasons, nonfinite, covered = [], Counter(), 0, set()
        for row in rows:
            if row['status'] != 'eligible':
                reasons[row['status']] += 1
                continue
            value = row['features'][name]
            if value is None:
                reasons[row['unavailable'].get(name, 'unavailable')] += 1
            elif not isinstance(value, (int, float)) or not math.isfinite(value):
                nonfinite += 1
            else:
                values.append(float(value)); covered.add(row['account'])
        stats = {'available_rows': len(values), 'unavailable_rows': dict(sorted(reasons.items())),
                 'nonfinite_rows': nonfinite, 'accounts_with_value': len(covered),
                 'distinct_values': len(set(values))}
        if values:
            array = numpy.asarray(values, dtype=numpy.float64)
            stats['min'], stats['max'] = float(array.min()), float(array.max())
            for label, q in QUANTILES:
                stats[label] = float(numpy.quantile(array, q, method='higher'))
            if name in BOUNDED:
                stats['exact_zero_fraction'] = float(numpy.mean(array == 0.0))
                stats['exact_one_fraction'] = float(numpy.mean(array == 1.0))
        result['features'][name] = stats
    return result


def markdown(result, hashes):
    lines = ['# W33 validation-only feature descriptives (features 6–9)', '',
             'Validation evidence only (original days 27 November–3 December 2017), not independent',
             'evaluation. Descriptive: no scenario recall, method selection, feature change or threshold',
             'tuning may be based on this report. Quantiles use NumPy `method="higher"`. No account',
             'identifiers are reported.', '',
             f"Observed validation account-days: {result['validation_observed_rows']} across "
             f"{result['validation_observed_accounts']} accounts; status counts: {json.dumps(result['status_counts'])}.", '',
             '| Feature | Available | Unavailable (reason: rows) | Nonfinite | Accounts | Distinct | Min | P05 | P25 | Median | P75 | P95 | Max | =0 | =1 |',
             '|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name in REPORTED:
        s = result['features'][name]
        fmt = lambda key: f'{s[key]:.6g}' if key in s else '—'
        lines.append(f"| {name} | {s['available_rows']} | {json.dumps(s['unavailable_rows'])} | {s['nonfinite_rows']} | "
                     f"{s['accounts_with_value']} | {s['distinct_values']} | {fmt('min')} | {fmt('p05')} | {fmt('p25')} | "
                     f"{fmt('median')} | {fmt('p75')} | {fmt('p95')} | {fmt('max')} | "
                     f"{fmt('exact_zero_fraction')} | {fmt('exact_one_fraction')} |")
    lines += ['', '## Bindings', '']
    lines += [f'- {key}: `{value}`' for key, value in sorted(hashes.items()) if not isinstance(value, dict)]
    lines += [f'- source {name}: `{value}`' for name, value in sorted(hashes['source_sha256'].items())]
    return '\n'.join(lines) + '\n'


def report(export_dir, output=None):
    export_dir = Path(export_dir).resolve()
    output = Path(output or ROOT / DEFAULT_OUTPUT).resolve()
    if output.exists() or not output.is_relative_to(ROOT.resolve()):
        raise ValueError('New report path inside the checkout required')
    manifest_bytes = (export_dir / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    rows_bytes = (export_dir / 'rows-validation.jsonl').read_bytes()
    if (manifest.get('schema') != 'w33_pretest_export_v1' or manifest.get('reserved_access') is not False
            or hashlib.sha256(rows_bytes).hexdigest() != manifest['partition_rows_sha256']['validation']
            or manifest.get('feature_contract_sha256') != features.contract_sha256()):
        raise ValueError('Validation export binding differs')
    rows = [json.loads(line) for line in rows_bytes.splitlines() if line]
    if any(row.get('partition') != 'validation' for row in rows):
        raise ValueError('Validation row file contains another partition')
    result = describe(rows)
    hashes = {'export_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
              'validation_rows_sha256': hashlib.sha256(rows_bytes).hexdigest(),
              'feature_contract_sha256': features.contract_sha256(),
              'source_sha256': reader.source_hashes(REPORT_SOURCES)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(markdown(result, hashes))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', required=True)
    parser.add_argument('--out')
    args = parser.parse_args()
    try:
        result = report(args.export, args.out)
        print(json.dumps({'validation_observed_rows': result['validation_observed_rows'], 'written': True}))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print('W33 validation report failed closed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
