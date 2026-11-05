"""W33 clue_ae_v2 training: preregistration, one B/C fit each, C-norm references, BL, thresholds.

Offline only. Reads the bound pre-test export (fit/validation/calibration rows);
no archive access, scenarios, reserved data or live activation. W33 permits one
real B and one real C fit for the whole experiment: an experiment-level exclusive
claim under data/ blocks any second fit, whatever preregistration path is used.
A failed attempt stays claimed and disclosed; another fit needs a new, explicit
prospective decision outside this module, never a new receipt alone.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import clue_v2_access as access, clue_v2_features as features, clue_v2_reader as reader
from scripts import export_clue_v2 as exporter

PREREG_SCHEMA = 'w33_training_preregistration_v1'
TRAINING_SOURCES = ['specs/W33-clue-ae-v2.md', 'scripts/train_clue_v2.py', 'scripts/tests/test_clue_v2_training.py',
                    'scripts/export_clue_v2.py', 'scripts/clue_v2_features.py', 'scripts/clue_v2_reader.py']
COUNT_COLUMNS = [0, 1, 2, 4]  # event_count, unique_actions, unique_resources, new_action_count
METHOD = {
    'profile': features.PROFILE, 'features': features.FEATURES,
    'detectors': {'B': {'columns': features.FEATURES[:5], 'architecture': [5, 16, 8, 3, 8, 16, 5]},
                  'C': {'columns': features.FEATURES, 'architecture': [9, 16, 8, 3, 8, 16, 9]}},
    'training_rows': 'common nine-feature-eligible fit rows; B selects its five columns',
    'validation_rows': 'common nine-feature-eligible validation rows',
    'row_order': 'UTC date, then account UTF-8 bytes',
    'transform': 'log1p on event_count/unique_actions/unique_resources/new_action_count only; '
                 'fit-only StandardScaler ddof=0, scale 1 for zero variance; float64 then float32 inputs',
    'activation': 'LeakyReLU(0.1) hidden, linear output', 'loss': 'mean MSE',
    'optimizer': {'name': 'Adam', 'lr': 0.001, 'betas': [0.9, 0.999], 'eps': 1e-8, 'weight_decay': 0, 'amsgrad': False},
    'batch_size': 64, 'drop_last': False, 'epochs_max': 100, 'patience': 10, 'tie_rule': 'strict improvement only',
    'seed': 42, 'threads': 1, 'deterministic_algorithms': True, 'device': 'cpu',
    'scoring': 'canonical single-row CPU float32 mean squared reconstruction error',
    'c_norm': {'reference_rows': 'all C-eligible original fit days per account, final restored C checkpoint',
               'min_reference_days': 5, 'median': 'midpoint', 'floor': 1e-8, 'fallback': 'none (unavailable)'},
    'baseline': 'BL = max(0, z_1..z_9) on C fit-only scaled float32 inputs',
    'thresholds': {'budgets': [0.01, 0.05], 'quantile': 'numpy higher at 1-budget', 'rule': 'score > threshold',
                   'min_calibration_rows': 100, 'detectors': ['B', 'C', 'C_norm', 'BL']},
    'engineering_gates': {'selected_accounts': 10, 'fit_rows': 1000, 'validation_rows': 100, 'calibration_rows': 100},
    'experiment_claim': 'data/processed/clue-ae-v2/w33-bc-fit-claim.json',
}
GATE_KEYS = {'selected_accounts': 'selected_accounts', 'fit_rows': 'fit_nine_feature_rows',
             'validation_rows': 'validation_nine_feature_rows', 'calibration_rows': 'calibration_nine_feature_rows'}
COUNT_FEATURES = ['event_count', 'unique_actions', 'unique_resources', 'new_action_count']
UNIT_FEATURES = ['off_hours_fraction', 'new_resource_share', 'action_mix_js_distance', 'hour_profile_js_distance']


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def private_new(path):
    path = Path(path).resolve()
    if path.exists() or not path.is_relative_to((ROOT / 'data').resolve()):
        raise ValueError('New private output below checkout data required')
    return path


def environment():
    return {'python': sys.version.split()[0], **{name: version(name) for name in ['torch', 'numpy', 'scikit-learn']}}


def check_row(row):
    """Eligibility flags and numeric invariants of one exported row; fail closed on any mismatch."""
    status, five, nine, values = row.get('status'), row.get('five_feature_eligible'), row.get('nine_feature_eligible'), row.get('features')
    if status not in ('eligible', 'cold_start', 'invalid_input') or type(five) is not bool or type(nine) is not bool:
        raise ValueError('Row status/eligibility flags invalid')
    if status != 'eligible':
        if values is not None or five or nine:
            raise ValueError('Unscorable rows must not carry vectors or eligibility')
        return
    # Canonical export JSON sorts keys; column order is imposed explicitly in matrix().
    if not five or not isinstance(values, dict) or set(values) != set(features.FEATURES):
        raise ValueError('Eligible row contract mismatch')
    if type(row.get('prior_usable_days')) is not int or row['prior_usable_days'] < features.K:
        raise ValueError('Eligible row below cold-start history')
    if (values['new_resource_share'] is None) == nine:
        raise ValueError('Nine-feature flag disagrees with feature 7 availability')
    for name in COUNT_FEATURES:
        if type(values[name]) is not int or values[name] < 0:
            raise ValueError(f'Invalid count {name}')
    for name, value in values.items():
        if value is None and name == 'new_resource_share':
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'Invalid {name}')
        if name in UNIT_FEATURES and not 0 <= value <= 1:
            raise ValueError(f'{name} outside [0,1]')
    if (not 1 <= values['unique_actions'] <= values['event_count'] or values['unique_resources'] > values['event_count']
            or values['new_action_count'] > values['unique_actions']):
        raise ValueError('Feature count invariant failed')


def verify_provenance(manifest):
    """The export must come from the currently bound producer chain; no archive is reopened."""
    expected = reader.source_hashes(exporter.EXPORT_SOURCES)
    if manifest.get('source_sha256') != expected:
        raise ValueError('Export producer sources missing or changed since export')
    binding = manifest.get('binding')
    keys = {'reader_receipt_path', 'reader_receipt_sha256', 'foundation_receipt_sha256', 'archive_sha256',
            'availability_file_sha256'}
    if not isinstance(binding, dict) or set(binding) != keys or binding['archive_sha256'] != access.ARCHIVE_SHA:
        raise ValueError('Export reader/availability binding missing or invalid')
    receipt = json.loads(Path(binding['reader_receipt_path']).read_bytes())
    if (receipt.get('receipt_sha256') != binding['reader_receipt_sha256']
            or receipt.get('foundation', {}).get('receipt_sha256') != binding['foundation_receipt_sha256']):
        raise ValueError('Export reader receipt binding differs')
    return {'source_sha256': expected, 'binding': binding}


def load_export(export_dir):
    """Verify provenance, file hashes, rows and recomputed gates. Returns (manifest, sha, cohort, rows, counts)."""
    export_dir = Path(export_dir).resolve()
    manifest_bytes = (export_dir / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    if (manifest.get('schema') != 'w33_pretest_export_v1' or manifest.get('profile') != features.PROFILE
            or manifest.get('features') != features.FEATURES or manifest.get('reserved_access') is not False
            or manifest.get('feature_contract_sha256') != features.contract_sha256()
            or manifest.get('engineering_gates_pass') is not True or manifest.get('policy') != access.POLICY):
        raise ValueError('Export is not a gate-passing W33 pre-test export')
    verify_provenance(manifest)
    cohort_bytes = (export_dir / 'cohort.json').read_bytes()
    if sha_bytes(cohort_bytes) != manifest['cohort_file_sha256']:
        raise ValueError('Cohort file differs from export manifest')
    selected = json.loads(cohort_bytes)['selected']
    if not isinstance(selected, list) or len(set(selected)) != len(selected) or not all(isinstance(a, str) for a in selected):
        raise ValueError('Cohort must be a list of unique accounts')
    cohort = set(selected)
    rows, seen = {}, set()
    for part in ('fit', 'validation', 'calibration'):
        data = (export_dir / f'rows-{part}.jsonl').read_bytes()
        if sha_bytes(data) != manifest['partition_rows_sha256'][part]:
            raise ValueError(f'{part} rows differ from export manifest')
        lo, hi = access.POLICY[part]
        rows[part] = []
        for line in data.splitlines():
            row = json.loads(line)
            if row.get('partition') != part or not lo <= row.get('day', '') <= hi or row.get('account') not in cohort:
                raise ValueError('Row outside its declared partition or cohort')
            if (row['account'], row['day']) in seen:
                raise ValueError('Duplicate account-day')
            seen.add((row['account'], row['day']))
            check_row(row)
            rows[part].append(row)
    counts = enforce_gates(manifest, selected, rows)
    return manifest, sha_bytes(manifest_bytes), selected, rows, counts


def enforce_gates(manifest, selected, rows):
    """Recount W33 minima from verified files and require agreement with the manifest's claims."""
    counts = {'selected_accounts': len(selected),
              **{f'{part}_rows': sum(row['nine_feature_eligible'] for row in rows[part])
                 for part in ('fit', 'validation', 'calibration')}}
    claimed = manifest.get('engineering_gates', {})
    for name, value in counts.items():
        if claimed.get(GATE_KEYS[name], {}).get('observed') != value:
            raise ValueError(f'Manifest gate claim disagrees with recount: {name}')
        part = name.removesuffix('_rows')
        if name != 'selected_accounts' and manifest['coverage'][part].get('nine_feature_eligible') != value:
            raise ValueError(f'Manifest coverage disagrees with recount: {part}')
        if value < METHOD['engineering_gates'][name]:
            raise ValueError(f'W33 engineering gate not met: {name}')
    return counts


def nine_rows(rows):
    """Common nine-feature-eligible rows in canonical order (UTC date, then account UTF-8 bytes)."""
    for row in rows:
        check_row(row)
    selected = [row for row in rows if row['nine_feature_eligible']]
    return sorted(selected, key=lambda row: (row['day'], row['account'].encode('utf-8')))


def matrix(rows, columns):
    import numpy as np
    if not rows:
        raise ValueError('Nonempty partition required')
    values = np.asarray([[row['features'][name] for name in features.FEATURES] for row in rows], dtype=np.float64)
    values[:, COUNT_COLUMNS] = np.log1p(values[:, COUNT_COLUMNS])
    return values[:, [features.FEATURES.index(name) for name in columns]]


class Scaler:
    """Fit-only population-SD standardisation; zero variance scales by 1 (as StandardScaler)."""

    def __init__(self, mean, scale):
        self.mean, self.scale = list(mean), list(scale)

    @classmethod
    def fit(cls, raw):
        import numpy as np
        mean, sd = raw.mean(axis=0), raw.std(axis=0, ddof=0)
        return cls(mean.tolist(), np.where(sd == 0, 1.0, sd).tolist())

    def transform(self, raw):
        import numpy as np
        return ((raw - np.asarray(self.mean)) / np.asarray(self.scale)).astype(np.float32)


def build_model(architecture):
    import torch.nn as nn
    layers = []
    for index, (left, right) in enumerate(zip(architecture, architecture[1:])):
        layers.append(nn.Linear(left, right))
        if index < len(architecture) - 2:
            layers.append(nn.LeakyReLU(0.1))
    return nn.Sequential(*layers)


class EarlyStop:
    """Keep the earliest best validation loss; ties never replace it."""

    def __init__(self, patience):
        self.patience, self.best, self.best_epoch, self.stalled = patience, math.inf, None, 0

    def update(self, epoch, loss):
        if not math.isfinite(loss):
            raise ValueError('Nonfinite validation loss')
        if loss < self.best:
            self.best, self.best_epoch, self.stalled = loss, epoch, 0
            return True
        self.stalled += 1
        return False

    @property
    def stop(self):
        return self.stalled >= self.patience


def seed_everything():
    import numpy as np
    import torch
    random.seed(42); np.random.seed(42); torch.manual_seed(42)
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)


def fit_one(train_x, val_x, architecture):
    import torch
    seed_everything()
    model = build_model(architecture)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001, betas=(0.9, 0.999), eps=1e-8,
                                 weight_decay=0, amsgrad=False)
    generator = torch.Generator().manual_seed(42)
    x, v = torch.from_numpy(train_x), torch.from_numpy(val_x)
    early, best_state, losses = EarlyStop(METHOD['patience']), None, []
    for epoch in range(METHOD['epochs_max']):
        model.train()
        for indexes in torch.randperm(len(x), generator=generator).split(METHOD['batch_size']):
            optimizer.zero_grad()
            loss = ((model(x[indexes]) - x[indexes]) ** 2).mean()
            loss.backward(); optimizer.step()
        model.eval()
        with torch.no_grad():
            value = float(((model(v) - v) ** 2).mean())
        losses.append(value)
        if early.update(epoch + 1, value):
            best_state = {key: tensor.detach().clone() for key, tensor in model.state_dict().items()}
        if early.stop:
            break
    if best_state is None:
        raise ValueError('No finite checkpoint')
    model.load_state_dict(best_state); model.eval()
    return model, {'trained_epochs': len(losses), 'best_epoch': early.best_epoch,
                   'best_validation_mse': early.best, 'validation_losses': losses}


def score_rows(model, inputs):
    """Canonical single-row CPU float32 reconstruction MSE."""
    import torch
    scores = []
    with torch.no_grad():
        for row in inputs:
            x = torch.from_numpy(row.reshape(1, -1))
            scores.append(float(((model(x) - x) ** 2).mean()))
    return scores


def c_norm_references(accounts, scores, cohort):
    """Per-account frozen denominator from that account's C fit-day errors; no fallback.

    Every selected account gets a record, including those with no eligible fit rows."""
    cohort = list(cohort)
    by_account, table = {account: [] for account in cohort}, {}
    for account, value in zip(accounts, scores):
        if account not in by_account:
            raise ValueError('Reference row outside the bound cohort')
        by_account[account].append(value)
    for account in sorted(by_account):
        values = by_account[account]
        if not values:
            table[account] = {'status': 'no_eligible_fit_rows', 'reference_days': 0}
        elif any(not math.isfinite(v) or v < 0 for v in values):
            table[account] = {'status': 'invalid_reference_error', 'reference_days': len(values)}
        elif len(values) < METHOD['c_norm']['min_reference_days']:
            table[account] = {'status': 'insufficient_reference_days', 'reference_days': len(values)}
        else:
            median = statistics.median(values)
            floor = METHOD['c_norm']['floor']
            table[account] = {'status': 'available', 'reference_days': len(values), 'raw_median': median,
                              'denominator': max(median, floor), 'floor_used': median < floor}
    return table


def threshold(scores):
    import numpy as np
    if len(scores) < METHOD['thresholds']['min_calibration_rows']:
        return {'status': 'insufficient_calibration_rows', 'rows': len(scores)}
    array = np.asarray(scores, dtype=np.float64)
    result = {'status': 'available', 'rows': len(scores)}
    for budget in METHOD['thresholds']['budgets']:
        value = float(np.quantile(array, 1 - budget, method='higher'))
        result[str(budget)] = {'threshold': value, 'ties_at_threshold': int((array == value).sum()),
                               'calibration_alerts': int((array > value).sum()),
                               'achieved_alert_fraction': float((array > value).mean())}
    return result


def preregister(export_dir, output):
    output = private_new(output)
    manifest, manifest_sha, cohort, rows, counts = load_export(export_dir)
    record = {'schema': PREREG_SCHEMA, 'profile': features.PROFILE,
              'created_at_utc': datetime.now(timezone.utc).isoformat(), 'method': METHOD,
              'export': {'path': str(Path(export_dir).resolve()), 'manifest_sha256': manifest_sha,
                         'cohort_file_sha256': manifest['cohort_file_sha256'],
                         'partition_rows_sha256': manifest['partition_rows_sha256'],
                         'recounted_gates': counts, 'producer_source_sha256': manifest['source_sha256'],
                         'producer_binding': manifest['binding']},
              'source_sha256': reader.source_hashes(TRAINING_SOURCES), 'environment': environment(),
              'reserved_access_authorised': False, 'live_activation': False,
              'status': 'training_preregistration_not_release'}
    record['receipt_sha256'] = sha_bytes(access.canonical(record))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as handle:
        handle.write(access.canonical(record) + b'\n')
        handle.flush(); os.fsync(handle.fileno())
    return record


def verify_preregistration(path):
    record = json.loads(Path(path).read_bytes())
    body = {key: value for key, value in record.items() if key != 'receipt_sha256'}
    if (record.get('receipt_sha256') != sha_bytes(access.canonical(body)) or record.get('schema') != PREREG_SCHEMA
            or record.get('method') != METHOD or record.get('reserved_access_authorised') is not False
            or record.get('source_sha256') != reader.source_hashes(TRAINING_SOURCES)
            or record.get('environment') != environment()):
        raise ValueError('Training preregistration mismatch')
    manifest, manifest_sha, cohort, rows, counts = load_export(record['export']['path'])
    if manifest_sha != record['export']['manifest_sha256'] or counts != record['export']['recounted_gates']:
        raise ValueError('Export changed since preregistration')
    return record, cohort, rows


def _save_detector(directory, model, scaler, columns):
    import torch
    directory.mkdir()
    torch.save(model.state_dict(), directory / 'model.pt')
    with (directory / 'scaler.json').open('xb') as handle:
        handle.write(access.canonical({'columns': columns, 'mean': scaler.mean, 'scale': scaler.scale}) + b'\n')


def _reload_detector(directory, architecture):
    import torch
    scaler_doc = json.loads((directory / 'scaler.json').read_bytes())
    model = build_model(architecture)
    model.load_state_dict(torch.load(directory / 'model.pt', weights_only=True, map_location='cpu'))
    model.eval()
    return model, Scaler(scaler_doc['mean'], scaler_doc['scale'])


def train(prereg_path, output):
    """The single W33 B/C fit: an experiment-level claim, then B and C, references, thresholds."""
    record, cohort, rows = verify_preregistration(prereg_path)
    output = private_new(output)
    claim = (ROOT / METHOD['experiment_claim']).resolve()
    claim.parent.mkdir(parents=True, exist_ok=True)
    with claim.open('xb') as handle:  # exclusive for the whole experiment, whichever receipt path is used
        handle.write(access.canonical({'experiment': 'W33', 'profile': features.PROFILE,
                                       'preregistration_path': str(Path(prereg_path).resolve()),
                                       'preregistration_sha256': record['receipt_sha256'], 'output': str(output),
                                       'started_at_utc': datetime.now(timezone.utc).isoformat()}) + b'\n')
    try:
        return _train_attempt(record, cohort, rows, output)
    except Exception as error:
        failure = Path(str(claim) + '.failed.json')
        with failure.open('xb') as handle:  # disclosed failed attempt; never an invisible rerun
            handle.write(access.canonical({'error_type': type(error).__name__,
                                           'failed_at_utc': datetime.now(timezone.utc).isoformat()}) + b'\n')
        raise


def _train_attempt(record, cohort, rows, output):
    import numpy as np
    fit, validation, calibration = (nine_rows(rows[part]) for part in ('fit', 'validation', 'calibration'))
    output.mkdir()
    results, order = {}, []
    for name in ('B', 'C'):
        spec = METHOD['detectors'][name]
        raw_fit, raw_val = matrix(fit, spec['columns']), matrix(validation, spec['columns'])
        scaler = Scaler.fit(raw_fit)
        model, history = fit_one(scaler.transform(raw_fit), scaler.transform(raw_val), spec['architecture'])
        _save_detector(output / name, model, scaler, spec['columns'])
        restored, restored_scaler = _reload_detector(output / name, spec['architecture'])
        probe = scaler.transform(raw_val)
        if score_rows(model, probe) != score_rows(restored, restored_scaler.transform(raw_val)):
            raise ValueError(f'{name} saved/reloaded score parity failed')
        results[name] = {**history, 'fit_rows': len(fit), 'validation_rows': len(validation),
                         'model_sha256': sha_bytes((output / name / 'model.pt').read_bytes()),
                         'scaler_sha256': sha_bytes((output / name / 'scaler.json').read_bytes())}
        order.append(f'fit_and_freeze_{name}')
    c_model, c_scaler = _reload_detector(output / 'C', METHOD['detectors']['C']['architecture'])
    fit_scores = score_rows(c_model, c_scaler.transform(matrix(fit, features.FEATURES)))
    references = c_norm_references([row['account'] for row in fit], fit_scores, cohort)
    with (output / 'c_norm_references.json').open('xb') as handle:
        handle.write(access.canonical(references) + b'\n')
    order.append('freeze_c_norm_references_before_calibration')
    b_model, b_scaler = _reload_detector(output / 'B', METHOD['detectors']['B']['architecture'])
    c_inputs = c_scaler.transform(matrix(calibration, features.FEATURES))
    scores = {'B': score_rows(b_model, b_scaler.transform(matrix(calibration, features.FEATURES[:5]))),
              'C': score_rows(c_model, c_inputs),
              'BL': [float(max(0.0, float(np.max(row)))) for row in c_inputs]}
    norm = [(value / references[row['account']]['denominator'])
            for row, value in zip(calibration, scores['C'])
            if references.get(row['account'], {}).get('status') == 'available']
    scores['C_norm'] = norm
    excluded = {}
    for row in calibration:
        status = references[row['account']]['status']
        if status != 'available':
            excluded[status] = excluded.get(status, 0) + 1
    thresholds = {name: threshold(values) for name, values in scores.items()}
    with (output / 'thresholds.json').open('xb') as handle:
        handle.write(access.canonical(thresholds) + b'\n')
    order.append('calibrate_thresholds')
    summary = {'schema': 'w33_training_release_candidate_v1', 'profile': features.PROFILE,
               'preregistration_sha256': record['receipt_sha256'], 'detectors': results,
               'c_norm': {'selected_accounts': len(cohort),
                          'available_accounts': sum(v['status'] == 'available' for v in references.values()),
                          'unavailable_accounts': sum(v['status'] != 'available' for v in references.values()),
                          'unavailable_by_reason': dict(sorted(
                              (status, sum(v['status'] == status for v in references.values()))
                              for status in {v['status'] for v in references.values()} - {'available'})),
                          'floor_used': sum(bool(v.get('floor_used')) for v in references.values()),
                          'calibration_rows': len(norm), 'calibration_rows_excluded': dict(sorted(excluded.items()))},
               'calibration_rows': len(calibration), 'operation_order': order,
               'references_sha256': sha_bytes((output / 'c_norm_references.json').read_bytes()),
               'thresholds_sha256': sha_bytes((output / 'thresholds.json').read_bytes()),
               'environment': environment(), 'reserved_access': False, 'activated': False,
               'status': 'trained_not_frozen_release'}
    with (output / 'manifest.json').open('xb') as handle:
        handle.write(access.canonical(summary) + b'\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    pre = sub.add_parser('preregister')
    pre.add_argument('--export', required=True)
    pre.add_argument('--out', required=True)
    run = sub.add_parser('train')
    run.add_argument('--prereg', required=True)
    run.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        if args.mode == 'preregister':
            result = preregister(args.export, args.out)
            print(json.dumps({'status': result['status'], 'receipt_sha256': result['receipt_sha256'],
                              'recounted_gates': result['export']['recounted_gates']}))
        else:
            result = train(args.prereg, args.out)
            print(json.dumps({key: result[key] for key in ('status', 'c_norm', 'calibration_rows', 'operation_order')}))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print('W33 training step failed closed; see the attempt record if one was created.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
