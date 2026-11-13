"""Offline training from audited normal lab features; never activates the live model."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.cloud_feature_extractor import CLOUD_FEATURES, CLOUD_INPUT_DIM
from scripts.train_cloud_ae import _build_cloud_ae


class TrainingRefusal(ValueError):
    """Safe workflow rejection suitable for display without dataset contents."""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def day(value):
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise TrainingRefusal('Use exact YYYY-MM-DD UTC cutoffs')
    return value


def prepare(path, train_end, validation_end, calibration_end):
    cutoffs = [day(d) for d in (train_end, validation_end, calibration_end)]
    if not cutoffs[0] < cutoffs[1] < cutoffs[2]:
        raise TrainingRefusal('Require train_end < validation_end < calibration_end')
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    data['_input_sha256'] = hashlib.sha256(raw).hexdigest()
    if (data.get('schema_version') != 1 or data.get('dataset_kind') != 'audited_aws_lab_normal'
            or data.get('features') != CLOUD_FEATURES
            or data.get('provenance', {}).get('feature_code_sha256') != sha(ROOT / 'backend/cloud_feature_extractor.py')
            or not data.get('provenance', {}).get('runs')):
        raise TrainingRefusal('Unsupported dataset contract or feature code digest')
    partitions = [[], [], []]
    seen = set()
    for row in data['rows']:
        current = day(row['date'])
        identity = row.get('user')
        if not isinstance(identity, str) or not identity:
            raise TrainingRefusal('Identity is missing')
        if (identity, current) in seen:
            raise TrainingRefusal('Duplicate identity-day')
        seen.add((identity, current))
        if current > calibration_end:
            continue  # Later rows never enter model selection/calibration.
        if row.get('complete_day') is not True or current >= datetime.now(timezone.utc).date().isoformat():
            raise TrainingRefusal('Only closed UTC days may enter training/calibration')
        values = [row[f] for f in CLOUD_FEATURES]
        if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0 for v in values):
            raise TrainingRefusal('Features must be finite nonnegative numbers')
        if row['event_count'] <= 0:
            raise TrainingRefusal('Empty feature window')
        partitions[0 if current <= train_end else 1 if current <= validation_end else 2].append(row)
    # Operational minimums, not a claim of statistical sufficiency or accuracy.
    for rows, minimum in zip(partitions, (30, 6, 6)):
        if len(rows) < minimum or len({r['user'] for r in rows}) < 6:
            raise TrainingRefusal('Insufficient rows/identities: require train>=30, validation>=6, calibration>=6 and six identities each')
    if len({r['date'] for r in partitions[0]}) < 5:
        raise TrainingRefusal('Training requires at least five distinct closed UTC days')
    for rows in partitions:
        rows.sort(key=lambda r: (r['date'], r['user']))
    return data, partitions


def calibrate(errors):
    import numpy as np
    values = np.asarray(errors, dtype=float)
    if not len(values) or not np.isfinite(values).all() or (values < 0).any():
        raise TrainingRefusal('Invalid normal calibration errors')
    low, high = float(np.percentile(values, 5)), float(2 * np.percentile(values, 95))
    if high - low <= 1e-12:
        raise TrainingRefusal('Degenerate calibration; collect more varied normal activity')
    return low, high


def train(path, output, train_end, validation_end, calibration_end, epochs=100, seed=42):
    if not 1 <= epochs <= 1000 or not 0 <= seed < 2**32:
        raise TrainingRefusal('Invalid epochs/seed')
    output = Path(output).resolve()
    if output.exists() or output == (ROOT / 'ml/models').resolve():
        raise TrainingRefusal('Use a new versioned output directory, never the active model directory')
    data, partitions = prepare(path, train_end, validation_end, calibration_end)
    import joblib
    import numpy as np
    import torch
    from sklearn.preprocessing import StandardScaler
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    arrays = [np.asarray([[r[f] for f in CLOUD_FEATURES] for r in rows], dtype=np.float32) for rows in partitions]
    scaler = StandardScaler().fit(arrays[0])
    tensors = [torch.tensor(scaler.transform(a).astype(np.float32)) for a in arrays]
    if any(not torch.isfinite(t).all() for t in tensors):
        raise TrainingRefusal('Scaled features overflowed')
    model = _build_cloud_ae(CLOUD_INPUT_DIM).cpu()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    best, state = math.inf, None
    for _ in range(epochs):
        model.train()
        for batch in tensors[0][torch.randperm(len(tensors[0]))].split(64):
            optimizer.zero_grad()
            loss = ((model(batch) - batch) ** 2).mean()
            if not torch.isfinite(loss):
                raise TrainingRefusal('Nonfinite training loss')
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            validation_loss = float(((model(tensors[1]) - tensors[1]) ** 2).mean())
        if validation_loss < best:
            best = validation_loss
            state = {key: value.detach().clone() for key, value in model.state_dict().items()}
    if state is None:
        raise TrainingRefusal('No finite model selected')
    model.load_state_dict(state)
    with torch.no_grad():
        errors = ((model(tensors[2]) - tensors[2]) ** 2).mean(dim=1).numpy()
    low, high = calibrate(errors)
    output.mkdir(parents=True, exist_ok=False)
    model_path, scaler_path = output / 'cloud_ae_v1.pt', output / 'cloud_scaler_v1.pkl'
    # Same architecture, feature order and score equation as current serving.
    torch.save({'state_dict': state, 'input_dim': CLOUD_INPUT_DIM, 'features': CLOUD_FEATURES,
                'ae_min': low, 'ae_max': high, 'epochs': epochs, 'seed': seed}, model_path)
    joblib.dump(scaler, scaler_path)
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    summary = {'schema_version': 1, 'frozen': True, 'normal_calibration_only': True,
               'input_dim': CLOUD_INPUT_DIM, 'features': CLOUD_FEATURES,
               'model_path': model_path.name, 'scaler_path': scaler_path.name,
               'model_sha256': sha(model_path), 'scaler_sha256': sha(scaler_path),
               'training_data_sha256': data['_input_sha256'], 'training_code_sha256': sha(Path(__file__)),
               'architecture_code_sha256': sha(ROOT / 'scripts/train_cloud_ae.py'),
               'feature_code_sha256': data['provenance']['feature_code_sha256'],
               'git_revision': revision.stdout.strip() if revision.returncode == 0 else None,
               'environment': {name: version(name) for name in ('torch', 'numpy', 'scikit-learn', 'joblib', 'scipy', 'threadpoolctl')},
               'python': platform.python_version(), 'device': 'cpu', 'seed': seed, 'epochs': epochs,
               'created_at': datetime.now(timezone.utc).isoformat(),
               'cutoffs_utc': {'train_end': train_end, 'validation_end': validation_end, 'calibration_end': calibration_end},
               'partitions': [{ 'rows': len(rows), 'identities': len({r['user'] for r in rows}),
                                'first_day': min(r['date'] for r in rows), 'last_day': max(r['date'] for r in rows)} for rows in partitions],
               'ae_min': low, 'ae_max': high, 'best_validation_mse': best,
               'normal_calibration_raw_p95': float(np.percentile(errors, 95)),
               'evaluation_status': 'not_evaluated', 'provisional': True,
               'limitations': 'Controlled AWS machine routines only. No held-out accuracy claim; '
               'calibration bounds preserve the existing score equation, not a calibrated probability. '
               'Daily snapshots do not validate partial-day live scores. Never automatically activate.'}
    (output / 'frozen_model_manifest.json').write_text(json.dumps(summary, indent=2, allow_nan=False), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--train-end', required=True)
    parser.add_argument('--validation-end', required=True)
    parser.add_argument('--calibration-end', required=True)
    parser.add_argument('--epochs', type=int, default=100)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--check-only', action='store_true', help='Validate provenance and data readiness without fitting')
    args = parser.parse_args()
    try:
        if args.check_only:
            _, partitions = prepare(args.data, args.train_end, args.validation_end, args.calibration_end)
            print(json.dumps({'ready': True, 'partition_rows': [len(rows) for rows in partitions], 'trained': False}))
        else:
            result = train(args.data, args.out, args.train_end, args.validation_end, args.calibration_end, args.epochs, args.seed)
            print(json.dumps({'frozen': result['frozen'], 'evaluation_status': result['evaluation_status'], 'activated': False}))
        return 0
    except TrainingRefusal as error:
        print(f'Training refused: {error}', file=sys.stderr)
        return 1
    except Exception:
        print('Training refused/stopped. Check provenance, closed-day partitions, sample coverage and a new output directory. No raw data displayed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
