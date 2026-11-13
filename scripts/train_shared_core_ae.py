"""One isolated five-feature AE candidate; no reserved access or live activation."""
import argparse
from importlib.metadata import version
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.shared_core_features import PROFILE, FEATURES, digest

METHOD = {'profile': PROFILE, 'architecture': [5, 16, 8, 3, 8, 16, 5],
          'activation': 'LeakyReLU(0.1)', 'output': 'linear', 'seed': 42,
          'epochs_max': 100, 'patience': 10, 'batch_size': 64, 'learning_rate': 0.001,
          'transform': 'log1p_counts_then_fit_only_StandardScaler',
          'baseline': 'max(0, five_fit_standardised_features)',
          'threshold': 'higher_normal_calibration_quantile_strict_greater',
          'budgets': [0.01, 0.05], 'reserved_utc': ['2017-08-11', '2017-08-24']}
SOURCE_FILES = ['scripts/shared_core_features.py', 'scripts/shared_core_scenarios.py',
                'scripts/shared_core_reader.py', 'scripts/export_shared_core_development.py',
                'scripts/train_shared_core_ae.py', 'scripts/clue_features.py',
                'scripts/export_clue_dataset.py', 'specs/W23-shared-core-contract.md',
                'docs/SHARED_CORE_TEST_PROTOCOL.md', 'docs/SHARED_CORE_RESOURCE_RULES.md']


def sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def private_new(path):
    path = Path(path).resolve()
    if path.exists() or not path.is_relative_to(ROOT / 'data'):
        raise ValueError('New private output below checkout data required')
    return path


def load_data(path):
    from datetime import date
    if Path(path).stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Oversized feature export')
    data = json.loads(Path(path).read_bytes())
    if data.get('profile') != PROFILE or data.get('features') != FEATURES or data.get('reserved_access') is not False or data.get('k') != 5:
        raise ValueError('Wrong feature contract')
    seen = set()
    population = data.get('population', [])
    if len(population) != 55 or len(set(population)) != 55:
        raise ValueError('Require the 55 fitting-selected identities')
    for row in data['rows']:
        if date.fromisoformat(row['day']).isoformat() != row['day'] or row['account'] not in population:
            raise ValueError('Invalid identity/day')
        if row['day'] > '2017-08-09':
            raise ValueError('Training process must not receive reserved/future data')
        if type(row.get('eligible')) is not bool or (row['eligible'] and (row.get('prior_active_days', 0) < 5 or row.get('issues') or row.get('features') is None)):
            raise ValueError('Eligibility contract mismatch')
        if not row['eligible'] and row.get('features') is not None:
            raise ValueError('Unscorable rows must not supply invented vectors')
        key = row['account'], row['day']
        if key in seen:
            raise ValueError('Duplicate account-day')
        seen.add(key)
    for name, value in data['bindings']['sources'].items():
        if sha(ROOT / 'scripts' / name) != value:
            raise ValueError('Feature producing source changed; re-export')
    return data


def partitions(data):
    return [[row for row in data['rows'] if row['eligible'] and start <= row['day'] <= end]
            for start, end in [('2017-07-13', '2017-07-26'), ('2017-07-27', '2017-07-31'), ('2017-08-01', '2017-08-04')]]


def matrix(rows):
    import numpy as np
    vectors = []
    for row in rows:
        value = row['features']
        if not isinstance(value, dict) or set(value) != set(FEATURES):
            raise ValueError('Complete ordered feature vector required')
        for key in [FEATURES[0], FEATURES[1], FEATURES[2], FEATURES[4]]:
            if type(value[key]) is not int or value[key] < 0:
                raise ValueError('Nonnegative integer counts required')
        fraction = value['off_hours_fraction']
        if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not np.isfinite(fraction) or not 0 <= fraction <= 1:
            raise ValueError('Valid off-hours fraction required')
        if not 1 <= value['unique_actions'] <= value['event_count'] or value['new_action_count'] > value['unique_actions'] or value['unique_resources'] > value['event_count']:
            raise ValueError('Feature count invariant failed')
        vectors.append([value[key] for key in FEATURES])
    result = np.asarray(vectors, dtype=np.float64)
    if not len(vectors):
        raise ValueError('Nonempty partition required')
    result[:, [0, 1, 2, 4]] = np.log1p(result[:, [0, 1, 2, 4]])
    return result


def build_model():
    import torch.nn as nn
    layers = []
    for index, (left, right) in enumerate(zip(METHOD['architecture'], METHOD['architecture'][1:])):
        layers.append(nn.Linear(left, right))
        if index < 5:
            layers.append(nn.LeakyReLU(0.1))
    return nn.Sequential(*layers)


def preregister(data_path, output):
    load_data(data_path)
    output = private_new(output)
    record = {'kind': 'shared_core_training_preregistration_v1', 'method': METHOD,
              'data_sha256': sha(data_path), 'source_hashes': {name: sha(ROOT / name) for name in SOURCE_FILES},
              'reserved_access_authorised': False, 'live_activation': False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(record, handle, indent=2)
    return {'preregistration_sha256': sha(output), 'reserved_access_authorised': False}


def train(data_path, prereg_path, output):
    import numpy as np
    import torch
    from sklearn.preprocessing import StandardScaler
    record = json.loads(Path(prereg_path).read_bytes())
    if record.get('kind') != 'shared_core_training_preregistration_v1' or record.get('method') != METHOD or record.get('data_sha256') != sha(data_path) or record.get('reserved_access_authorised') is not False:
        raise ValueError('Training preregistration mismatch')
    if record['source_hashes'] != {name: sha(ROOT / name) for name in SOURCE_FILES}:
        raise ValueError('Preregistered sources changed')
    data = load_data(data_path)
    fit, validation, calibration = partitions(data)
    if len(calibration) < 100:
        raise ValueError('Insufficient normal calibration days')
    output = private_new(output)
    raw_fit, raw_val, raw_cal = map(matrix, (fit, validation, calibration))
    scaler = StandardScaler().fit(raw_fit)
    x = torch.tensor(scaler.transform(raw_fit), dtype=torch.float32)
    v = torch.tensor(scaler.transform(raw_val), dtype=torch.float32)
    c = torch.tensor(scaler.transform(raw_cal), dtype=torch.float32)
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True); torch.manual_seed(42)
    generator = torch.Generator().manual_seed(42)
    model = build_model()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    best, best_state, stalled, trained_epochs = float('inf'), None, 0, 0
    for epoch in range(100):
        model.train()
        order = torch.randperm(len(x), generator=generator)
        for indexes in order.split(64):
            optimizer.zero_grad(); loss = ((model(x[indexes]) - x[indexes]) ** 2).mean()
            loss.backward(); optimizer.step()
        model.eval()
        with torch.no_grad():
            value = float(((model(v) - v) ** 2).mean())
        trained_epochs = epoch + 1
        if value < best:
            best, stalled = value, 0
            best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
        else:
            stalled += 1
        if stalled >= 10:
            break
    if best_state is None or not np.isfinite(best):
        raise ValueError('Training did not produce a finite checkpoint')
    model.load_state_dict(best_state); model.eval()
    with torch.no_grad():
        errors = ((model(c) - c) ** 2).mean(dim=1).numpy().astype(float)
    baseline = np.maximum(0, c.numpy()).max(axis=1).astype(float)
    thresholds = {}
    for budget in METHOD['budgets']:
        thresholds[str(budget)] = {name: {'threshold': float(np.quantile(scores, 1-budget, method='higher')),
            'calibration_alert_fraction': float(np.mean(scores > np.quantile(scores, 1-budget, method='higher')))}
            for name, scores in [('ae', errors), ('max_deviation', baseline)]}
    output.mkdir(parents=True)
    torch.save(best_state, output / 'model.pt')
    scaler_data = {'features': FEATURES, 'mean': scaler.mean_.tolist(), 'scale': scaler.scale_.tolist(),
                   'variance': scaler.var_.tolist(), 'fit_samples': len(fit), 'transform': METHOD['transform']}
    (output / 'scaler.json').write_text(json.dumps(scaler_data, indent=2), encoding='utf-8')
    # Reconstruct transforms and weights from disk before declaring a usable candidate.
    restored_scaler = json.loads((output / 'scaler.json').read_bytes())
    restored_x = torch.tensor((raw_cal - np.asarray(restored_scaler['mean'])) / np.asarray(restored_scaler['scale']), dtype=torch.float32)
    restored = build_model(); restored.load_state_dict(torch.load(output / 'model.pt', weights_only=True, map_location='cpu')); restored.eval()
    with torch.no_grad():
        restored_errors = ((restored(restored_x) - restored_x) ** 2).mean(dim=1).numpy().astype(float)
    if not np.array_equal(restored_errors, errors):
        raise ValueError('Saved/reloaded score parity failed')
    report = {'profile': PROFILE, 'features': FEATURES, 'method': METHOD,
              'partition_rows': {'fit': len(fit), 'validation': len(validation), 'normal_calibration': len(calibration)},
              'fit_identities': len({row['account'] for row in fit}), 'frozen_population': len(data['population']),
              'trained_epochs': trained_epochs, 'best_validation_mse': best, 'thresholds': thresholds,
              'saved_score_parity': 'exact', 'evaluation_status': 'not_evaluated', 'activated': False,
              'preregistration_sha256': sha(prereg_path), 'data_sha256': sha(data_path),
              'model_sha256': sha(output / 'model.pt'), 'scaler_sha256': sha(output / 'scaler.json'),
              'source_hashes': record['source_hashes'],
              'environment': {name: version(name) for name in ['torch', 'numpy', 'scikit-learn', 'scipy', 'tzdata']},
              'limitations': 'Calibration diagnostics only. No reserved test, attack metrics, live transfer validation or activation.'}
    (output / 'manifest.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['preregister', 'train']); parser.add_argument('--data', required=True)
    parser.add_argument('--prereg'); parser.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.mode == 'preregister':
        result = preregister(args.data, args.out)
    else:
        if not args.prereg:
            parser.error('--prereg required')
        report = train(args.data, args.prereg, args.out)
        result = {name: report[name] for name in ['profile', 'partition_rows', 'fit_identities', 'trained_epochs', 'thresholds', 'saved_score_parity', 'evaluation_status', 'activated']}
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
