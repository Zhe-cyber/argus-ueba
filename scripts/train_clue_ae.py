"""Separate CLUE benchmark AE. No AWS/CERT installation or live inference."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.clue_features import FEATURES, PROFILE


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_dataset(path):
    if Path(path).stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Feature JSON exceeds 64 MiB')
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    if (data.get('schema_version') != 1 or data.get('profile') != PROFILE or data.get('features') != FEATURES
            or data.get('provenance', {}).get('feature_code_sha256') != sha(ROOT / 'scripts/clue_features.py')):
        raise ValueError('Feature contract/provenance differs')
    if data['provenance'].get('day_reversal_events', 0):
        raise ValueError('Resolve cross-day timestamp reversals first')
    seen = set()
    for row in data['rows']:
        if (not isinstance(row.get('user'), str) or not row['user']
                or date.fromisoformat(row['date']).isoformat() != row['date']
                or type(row.get('capture_boundary')) is not bool):
            raise ValueError('Invalid identity/day metadata')
        key = (row['user'], row['date'])
        if key in seen:
            raise ValueError('Duplicate identity-day')
        seen.add(key)
    return data, hashlib.sha256(raw).hexdigest()


def select(data, cutoffs):
    if len(cutoffs) != 5 or any(date.fromisoformat(d).isoformat() != d for d in cutoffs):
        raise ValueError('Require five exact UTC date cutoffs')
    if any(a >= b for a, b in zip(cutoffs, cutoffs[1:])):
        raise ValueError('Cutoffs must strictly increase')
    if cutoffs[-1] >= data['provenance']['last_capture_day']:
        raise ValueError('Evaluation must end before the last partial capture date')
    rows = [r for r in data['rows'] if not r['capture_boundary']]
    warmup, fitting = set(), {}
    for row in rows:
        if row['date'] <= cutoffs[0]: warmup.add(row['user'])
        elif row['date'] <= cutoffs[1]: fitting.setdefault(row['user'], set()).add(row['date'])
    population = sorted(u for u, days in fitting.items() if len(days) >= 5 and u in warmup)
    if len(population) < 6:
        raise ValueError('Require six fitting-eligible identities with prior warmup')
    selected = set(population)
    partitions = [[] for _ in range(5)]
    for row in rows:
        if row['user'] in selected and row['date'] <= cutoffs[-1]:
            i = next(i for i, end in enumerate(cutoffs) if row['date'] <= end)
            partitions[i].append(row)
    for part in partitions: part.sort(key=lambda r: (r['date'], r['user']))
    return population, partitions


def matrix(rows):
    import numpy as np
    for row in rows:
        if (row['coverage'].get('missing_required_paths', 0)
                or row['coverage'].get('unknown_action_events', 0)):
            raise ValueError('Unresolved feature coverage')
        if set(row['features']) != set(FEATURES):
            raise ValueError('Wrong vector fields')
        for value in row['features'].values():
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                raise ValueError('Features must be finite nonnegative counts')
        if row['features']['event_count'] <= 0:
            raise ValueError('No synthetic idle-day vectors')
    result = np.asarray([[r['features'][f] for f in FEATURES] for r in rows], dtype=np.float64)
    return np.log1p(result)


def build_model():
    import torch.nn as nn
    class ClueAE(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = nn.Sequential(nn.Linear(10, 32), nn.LeakyReLU(0.1), nn.Linear(32, 16),
                                         nn.LeakyReLU(0.1), nn.Linear(16, 8), nn.LeakyReLU(0.1))
            self.decoder = nn.Sequential(nn.Linear(8, 16), nn.LeakyReLU(0.1), nn.Linear(16, 32),
                                         nn.LeakyReLU(0.1), nn.Linear(32, 10))
        def forward(self, x): return self.decoder(self.encoder(x))
    return ClueAE()


def errors(model, tensor):
    import torch
    model.eval()
    with torch.no_grad():
        values = ((model(tensor) - tensor)**2).mean(dim=1).numpy()
    if not __import__('numpy').isfinite(values).all():
        raise ValueError('Nonfinite inference error')
    return values


def train(dataset, output, cutoffs, epochs=100, seed=42):
    if not 1 <= epochs <= 1000 or not 0 <= seed < 2**32:
        raise ValueError('Invalid epochs/seed')
    output = Path(output)
    if output.exists(): raise ValueError('Use a new candidate output directory')
    data, digest = load_dataset(dataset)
    population, parts = select(data, cutoffs)
    # Held-out feature values are not read here; only fitting/validation/calibration enter tensors.
    for part, minimum in zip(parts[1:4], (30, 6, 6)):
        if len(part) < minimum or len({r['user'] for r in part}) < 6:
            raise ValueError('Insufficient observed fitting/validation/calibration data')
    import joblib
    import numpy as np
    import torch
    from sklearn.preprocessing import StandardScaler
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    arrays = [matrix(p) for p in parts[1:4]]
    scaler = StandardScaler().fit(arrays[0])
    tensors = [torch.tensor(scaler.transform(a).astype(np.float32)) for a in arrays]
    model = build_model().cpu()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    best, weights = math.inf, None
    for _ in range(epochs):
        model.train()
        for batch in tensors[0][torch.randperm(len(tensors[0]))].split(64):
            optimizer.zero_grad()
            loss = ((model(batch)-batch)**2).mean()
            if not torch.isfinite(loss): raise ValueError('Nonfinite training loss')
            loss.backward(); optimizer.step()
        value = float(errors(model, tensors[1]).mean())
        if value < best:
            best, weights = value, {k:v.detach().clone() for k,v in model.state_dict().items()}
    if weights is None: raise ValueError('No finite model selected')
    model.load_state_dict(weights)
    calibration = errors(model, tensors[2])
    if float(np.ptp(calibration)) <= 1e-12: raise ValueError('Degenerate normal calibration')
    threshold = float(np.quantile(calibration, 0.99, method='linear'))
    output.mkdir(parents=True, exist_ok=False)
    model_path, scaler_path = output/'clue_ae_v1.pt', output/'clue_scaler_v1.pkl'
    torch.save({'profile': PROFILE, 'features': FEATURES, 'input_dim': 10, 'state_dict': weights}, model_path)
    joblib.dump(scaler, scaler_path)
    manifest = {'schema_version': 1, 'profile': PROFILE, 'features': FEATURES, 'input_dim': 10,
                'architecture': '10-32-16-8-16-32-10; LeakyReLU(0.1)',
                'transform': 'log1p_then_standard_scaler_v1', 'frozen': True,
                'model_path': model_path.name, 'scaler_path': scaler_path.name,
                'model_sha256': sha(model_path), 'scaler_sha256': sha(scaler_path),
                'dataset_sha256': digest, 'feature_code_sha256': sha(ROOT/'scripts/clue_features.py'),
                'training_code_sha256': sha(Path(__file__)), 'cutoffs_utc': cutoffs,
                'fitting_population': population,
                'partition_rows': {'fit':len(parts[1]), 'validation':len(parts[2]), 'normal_calibration':len(parts[3])},
                'fit_rows_sha256': hashlib.sha256(json.dumps(parts[1], sort_keys=True).encode()).hexdigest(),
                'threshold_raw_mse': threshold, 'calibration_quantile': 0.99,
                'threshold_rule': 'alert iff raw_mse > threshold; normal-calibration only',
                'best_validation_mse': best, 'seed':seed, 'epochs':epochs, 'device':'cpu',
                'python':platform.python_version(),
                'environment': {n:version(n) for n in ('torch','numpy','scikit-learn','joblib','scipy')},
                'evaluation_status':'not_evaluated', 'activated':False,
                'limitations':'Offline CLUE population AE, not a per-user conditional model or AWS/CERT checkpoint. '
                'Publisher-declared normal data; partial-prefix integrity/coverage limitations remain. '
                'MSE is not a compromise probability; 99% calibration quantile does not guarantee 1% future false alerts.'}
    (output/'clue_model_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False),encoding='utf8')
    return manifest


def evaluate(dataset, bundle, output):
    import joblib
    import numpy as np
    import torch
    bundle, output = Path(bundle), Path(output)
    if output.exists(): raise ValueError('Evaluation report already exists')
    manifest = json.loads((bundle/'clue_model_manifest.json').read_text())
    if (manifest.get('frozen') is not True or manifest.get('profile') != PROFILE
            or manifest.get('features') != FEATURES or manifest.get('transform') != 'log1p_then_standard_scaler_v1'):
        raise ValueError('Incompatible frozen bundle')
    for name in ('model','scaler'):
        path = (bundle/manifest[name+'_path']).resolve()
        if path.parent != bundle.resolve() or sha(path) != manifest[name+'_sha256']:
            raise ValueError('Artifact path/digest differs')
    data, digest = load_dataset(dataset)
    if digest != manifest['dataset_sha256']:
        raise ValueError('Evaluation dataset differs from the frozen split manifest')
    population, parts = select(data, manifest['cutoffs_utc'])
    if population != manifest['fitting_population']: raise ValueError('Fitting population differs')
    heldout = parts[4]
    if len(heldout) < 6 or len({r['user'] for r in heldout}) < 6:
        raise ValueError('Insufficient held-out normal coverage')
    # Load only this trusted locally generated, hash-checked bundle.
    model = build_model().cpu()
    checkpoint = torch.load(bundle/manifest['model_path'],map_location='cpu',weights_only=True)
    model.load_state_dict(checkpoint['state_dict'])
    scaler = joblib.load(bundle/manifest['scaler_path'])
    tensor = torch.tensor(scaler.transform(matrix(heldout)).astype(np.float32))
    raw = errors(model,tensor)
    alerts = int((raw > manifest['threshold_raw_mse']).sum())
    n, z = len(raw), 1.96
    rate = alerts/n
    centre = (rate+z*z/(2*n))/(1+z*z/n)
    radius = z*math.sqrt(rate*(1-rate)/n+z*z/(4*n*n))/(1+z*z/n)
    report = {'profile':PROFILE, 'dataset_sha256':digest,
              'model_sha256':manifest['model_sha256'], 'manifest_sha256':sha(bundle/'clue_model_manifest.json'),
              'heldout_active_identity_days':n, 'observed_identities':len({r['user'] for r in heldout}),
              'frozen_population':len(population), 'identities_without_heldout_activity':len(population)-len({r['user'] for r in heldout}),
              'normal_alerts':alerts, 'normal_alert_fraction':rate,
              'wilson95_interval_descriptive_only':[max(0.,centre-radius),min(1.,centre+radius)],
              'threshold_raw_mse':manifest['threshold_raw_mse'], 'evaluation_status':'normal_holdout_only',
              'attack_recall':None, 'activated':False,
              'limitations':'No attack evaluation. Days/users are correlated: binomial interval is descriptive, '
              'not a calibrated dependence-aware confidence guarantee. Missing activity is not a true negative.'}
    with output.open('x',encoding='utf8') as target: json.dump(report,target,indent=2,allow_nan=False)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    fit = sub.add_parser('train')
    fit.add_argument('--data',required=True); fit.add_argument('--out',required=True)
    fit.add_argument('--cutoffs',nargs=5,required=True)
    fit.add_argument('--epochs',type=int,default=100); fit.add_argument('--seed',type=int,default=42)
    check = sub.add_parser('evaluate')
    check.add_argument('--data',required=True); check.add_argument('--bundle',required=True); check.add_argument('--out',required=True)
    args = parser.parse_args()
    try:
        if args.command == 'train':
            result = train(args.data,args.out,args.cutoffs,args.epochs,args.seed)
            print(json.dumps({k:result[k] for k in ('profile','partition_rows','evaluation_status','activated')}))
        else:
            result = evaluate(args.data,args.bundle,args.out)
            print(json.dumps({k:result[k] for k in ('heldout_active_identity_days','normal_alerts','normal_alert_fraction','evaluation_status')}))
    except Exception:
        parser.exit(1,'CLUE workflow stopped. Check contract, coverage, disjoint dates, trusted artifact hashes and new output paths. No raw records displayed.\n')
