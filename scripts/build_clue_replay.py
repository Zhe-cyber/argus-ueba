"""Two-step private CLUE replay export. No training, database access or live activation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.clue_replay_contract import PROFILE, priority, validate_policy
from scripts.train_clue_ae import FEATURES, build_model, load_dataset, matrix, select, sha


def code_digest():
    return hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def candidate(dataset, bundle):
    bundle = Path(bundle).resolve()
    manifest_path = bundle / 'clue_model_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get('profile') != PROFILE or manifest.get('features') != FEATURES
            or manifest.get('input_dim') != 10 or manifest.get('frozen') is not True
            or manifest.get('transform') != 'log1p_then_standard_scaler_v1'
            or manifest.get('calibration_quantile') != .99):
        raise ValueError('Use the frozen ten-feature CLUE candidate')
    for kind in ('model', 'scaler'):
        artifact = (bundle / manifest[kind + '_path']).resolve()
        if artifact.parent != bundle or sha(artifact) != manifest[kind + '_sha256']:
            raise ValueError('Artifact binding differs; no deserialisation performed')
    training_code = (ROOT / 'scripts/train_clue_ae.py').read_bytes().replace(b'\r\n', b'\n')
    if hashlib.sha256(training_code).hexdigest() != manifest['training_code_sha256']:
        raise ValueError('Use the pinned training implementation')
    data, digest = load_dataset(dataset)
    if digest != manifest['dataset_sha256']:
        raise ValueError('Dataset binding differs')
    population, partitions = select(data, manifest['cutoffs_utc'])
    if population != manifest['fitting_population']:
        raise ValueError('Fitting population differs')
    # Only caller-supplied, locally verified trusted artifacts are deserialised.
    import joblib
    import torch
    model = build_model().cpu()
    model.load_state_dict(torch.load(bundle / manifest['model_path'], map_location='cpu', weights_only=True)['state_dict'])
    model.eval()
    scaler = joblib.load(bundle / manifest['scaler_path'])
    return bundle, manifest, population, partitions, model, scaler


def residuals(rows, model, scaler):
    import numpy as np
    import torch
    if not rows:
        raise ValueError('Partition is empty')
    x = torch.tensor(scaler.transform(matrix(rows)).astype(np.float32))
    with torch.no_grad():
        values = ((model(x) - x) ** 2).numpy()
    if not np.isfinite(values).all():
        raise ValueError('Nonfinite model output')
    return values


def freeze_policy(dataset, bundle, output):
    output = Path(output)
    if output.exists():
        raise ValueError('Policy already exists; never overwrite it')
    bundle, manifest, _, parts, model, scaler = candidate(dataset, bundle)
    import numpy as np
    # No fitting, validation or held-out feature matrix is scored here.
    errors = residuals(parts[3], model, scaler).mean(axis=1)
    high = float(manifest['threshold_raw_mse'])
    if not np.isclose(np.quantile(errors, .99, method='linear'), high, rtol=1e-6, atol=1e-8):
        raise ValueError('Frozen High threshold does not reproduce calibration')
    policy = {'schema_version': 1, 'profile': PROFILE, 'features': FEATURES,
              'medium_threshold': float(np.quantile(errors, .95, method='linear')),
              'high_threshold': high, 'medium_quantile': .95, 'high_quantile': .99,
              'quantile_method': 'linear', 'boundary_rule': 'strictly_greater',
              'units': 'raw_reconstruction_mse', 'calibration_rows': len(errors),
              'cutoffs_utc': manifest['cutoffs_utc'],
              'model_sha256': manifest['model_sha256'], 'scaler_sha256': manifest['scaler_sha256'],
              'dataset_sha256': manifest['dataset_sha256'],
              'candidate_manifest_sha256': sha(bundle / 'clue_model_manifest.json'),
              'export_code_canonical_lf_sha256': code_digest(),
              'meaning': 'Normal-data-calibrated review priority, not attack labels or compromise probability. High retains the original frozen alert rule; Medium is a new presentation policy.'}
    validate_policy(policy)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as target:
        json.dump(policy, target, indent=2, allow_nan=False)
    return policy


def export_replay(dataset, bundle, policy_path, output):
    output, policy_path = Path(output), Path(policy_path)
    if output.exists():
        raise ValueError('Use a new replay output directory')
    raw_policy = policy_path.read_bytes()
    policy = json.loads(raw_policy)
    validate_policy(policy)
    bundle, manifest, population, parts, model, scaler = candidate(dataset, bundle)
    expected = {'model_sha256': manifest['model_sha256'], 'scaler_sha256': manifest['scaler_sha256'],
                'dataset_sha256': manifest['dataset_sha256'], 'candidate_manifest_sha256': sha(bundle / 'clue_model_manifest.json'),
                'cutoffs_utc': manifest['cutoffs_utc'], 'high_threshold': manifest['threshold_raw_mse'],
                'export_code_canonical_lf_sha256': code_digest(), 'features': FEATURES}
    if any(policy.get(k) != v for k, v in expected.items()):
        raise ValueError('Policy binding differs')
    import numpy as np
    calibration_residuals = residuals(parts[3], model, scaler)
    expected_medium = float(np.quantile(calibration_residuals.mean(axis=1), .95, method='linear'))
    if policy['medium_threshold'] != expected_medium or policy['calibration_rows'] != len(parts[3]):
        raise ValueError('Medium threshold must come from the fixed calibration partition')
    heldout_residuals = residuals(parts[4], model, scaler)
    heldout_scores = heldout_residuals.mean(axis=1)
    published = json.loads((bundle / 'normal_holdout_report.json').read_text())
    bindings = {'manifest_sha256': sha(bundle / 'clue_model_manifest.json'),
                'model_sha256': manifest['model_sha256'], 'dataset_sha256': manifest['dataset_sha256'],
                'threshold_raw_mse': policy['high_threshold']}
    if (any(published.get(k) != v for k, v in bindings.items())
            or published['heldout_active_identity_days'] != len(heldout_scores)
            or published['normal_alerts'] != int((heldout_scores > policy['high_threshold']).sum())):
        raise ValueError('Frozen holdout report was not reproduced')
    aliases = {u: f'cohort-{i+1}' for i, u in enumerate(population)}
    rows = []
    for split, partition, values in [('calibration', parts[3], calibration_residuals), ('heldout', parts[4], heldout_residuals)]:
        for row, vector in zip(partition, values):
            score = float(vector.mean())
            rows.append({'account': aliases[row['user']], 'day': row['date'], 'split': split,
                         'raw_mse': score, 'review_priority': priority(score, policy['medium_threshold'], policy['high_threshold']),
                         'features': row['features'],
                         'residuals': {f: float(vector[i] / len(FEATURES)) for i, f in enumerate(FEATURES)}})
    output.mkdir(parents=True, exist_ok=False)
    (output / 'policy.json').write_bytes(raw_policy)
    (output / 'replay.json').write_text(json.dumps({'schema_version': 1, 'profile': PROFILE, 'rows': rows}, indent=2, allow_nan=False), encoding='utf-8')
    manifest_out = {'schema_version': 1, **{name + '_sha256': sha(output / name) for name in ('policy.json', 'replay.json')}}
    (output / 'manifest.json').write_text(json.dumps(manifest_out, indent=2), encoding='utf-8')
    return {'calibration_account_days': len(parts[3]), 'heldout_account_days': len(parts[4]),
            'heldout_high': int((heldout_scores > policy['high_threshold']).sum()), 'live_activation': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('freeze-policy', 'export'))
    for flag in ('--data', '--bundle', '--out'):
        parser.add_argument(flag, required=True)
    parser.add_argument('--policy')
    args = parser.parse_args()
    try:
        if args.operation == 'export' and not args.policy:
            raise ValueError('Export requires the previously frozen --policy')
        result = (freeze_policy(args.data, args.bundle, args.out) if args.operation == 'freeze-policy'
                  else export_replay(args.data, args.bundle, args.policy, args.out))
        print(json.dumps({k: v for k, v in result.items() if k in
                          ('medium_threshold', 'high_threshold', 'calibration_rows', 'calibration_account_days',
                           'heldout_account_days', 'heldout_high', 'live_activation')}))
    except Exception as error:
        parser.exit(1, f'Replay preparation stopped ({type(error).__name__}). Verify local bindings and a new output path.\n')
