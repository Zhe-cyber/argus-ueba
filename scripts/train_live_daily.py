"""Versioned offline training for audited MY-day lab exports; never activates."""
from datetime import datetime, timezone
from importlib.metadata import version
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.aws_lab_daily_features import CONTRACT, FEATURES
from scripts import export_live_daily as exporter, live_history_readiness as readiness, live_daily_method as method

CONTRACT_SHA = '1612cd7401704efef92d0c462543f3eeebf5c7c0cbe39285998299b498688ebc'
SOURCES = ('scripts/train_live_daily.py', 'scripts/live_daily_method.py', 'docs/LIVE_METHOD_ANNEX_V1.md')


class Refusal(ValueError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    return {name: sha(ROOT / name) for name in SOURCES}


def positive_counts(counts, domain):
    return (isinstance(counts, dict) and bool(counts) and not set(counts) - set(domain)
            and all(type(v) is int and v > 0 for v in counts.values()))


def prepare(directory, now=None):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    raw = (directory / 'dataset.json').read_bytes()
    data = json.loads(raw)
    if (hashlib.sha256(raw).hexdigest() != manifest.get('dataset_sha256')
            or sha(directory / 'feature_contract.json') != CONTRACT_SHA
            or manifest.get('feature_contract_sha256') != CONTRACT_SHA
            or data.get('feature_contract_sha256') != CONTRACT_SHA
            or exporter.digest(CONTRACT) != CONTRACT_SHA
            or data.get('schema') != 'argus_live_daily_dataset_v1'
            or data.get('profile') != 'aws_lab_daily_v1'
            or data.get('provenance', {}).get('source_sha256') != exporter.hashes()
            or manifest.get('source_sha256') != exporter.hashes()
            or data.get('provenance', {}).get('profile_sha256') != readiness.PROFILE_SHA):
        raise Refusal('Dataset/contract/source binding differs')
    today = (now or datetime.now(timezone.utc)).astimezone(readiness.MALAYSIA).date().isoformat()
    coverage = {(r['day'], r['persona']): r for r in data['readiness']['days'] if r['status'] == 'usable'}
    parts = {name: [] for name in readiness.WINDOWS}
    excluded, seen = [], set()
    for row in data['rows']:
        key = row['date_local'], row['persona']
        if key in seen or row['persona'] not in method.ROLES or key not in coverage:
            raise Refusal('Duplicate, unknown or unaudited account-day')
        seen.add(key)
        part = row['partition']
        if (part not in parts or not readiness.WINDOWS[part][0] <= key[0] <= readiness.WINDOWS[part][1]
                or key[0] >= today or row.get('complete_day') is not True):
            raise Refusal('Wrong partition or open date')
        values, cv = row['features'], row['coverage']
        if set(values) != set(FEATURES) or any(type(v) is not int or not 0 <= v <= 5 for v in values.values()):
            raise Refusal('Invalid count vector')
        n = values['event_count']
        if (set(cv) != {'planned', 'verified', 'missing', 'missed', 'unresolved', 'verified_fraction_of_planned'}
                or any(type(cv[k]) is not int or not 0 <= cv[k] <= 5 for k in ('planned', 'verified', 'missing', 'missed', 'unresolved'))
                or n <= 0 or cv['verified'] != n or cv['unresolved'] != 0 or not 1 <= cv['planned'] <= 5
                or n * 10 < cv['planned'] * 9 or cv['verified'] + cv['missing'] + cv['missed'] != cv['planned']
                or not math.isclose(cv['verified_fraction_of_planned'], n / cv['planned'], rel_tol=0, abs_tol=1e-15)
                or any(cv[k] != coverage[key][k] for k in cv)):
            raise Refusal('Inconsistent coverage')
        ac, rc, hc = row['action_counts'], row['resource_counts'], row['local_hour_counts']
        if (not positive_counts(ac, CONTRACT['allowed_operations']) or not positive_counts(rc, method.DOMAIN)
                or not positive_counts(hc, [f'{h:02d}' for h in range(24)])
                or any(sum(c.values()) != n for c in (ac, rc, hc))
                or [values[f] for f in FEATURES[1:4]] != [ac.get(a, 0) for a in CONTRACT['allowed_operations']]
                or values['unique_resources'] != len(rc) or values['confidential_bucket_reads'] != rc.get('confidential', 0)):
            raise Refusal('Inconsistent categorical context')
        weekday = datetime.fromisoformat(key[0]).weekday()
        off = sum(count for hour, count in hc.items() if weekday >= 5 or not 8 <= int(hour) < 20)
        ip = row['ip_observability']
        if (off != values['off_hours_events'] or set(ip) != {'valid_events', 'missing_events', 'invalid_events'}
                or any(type(v) is not int or v < 0 for v in ip.values()) or sum(ip.values()) != n
                or values['unique_valid_ips'] > ip['valid_events']
                or (ip['valid_events'] > 0 and values['unique_valid_ips'] == 0)):
            raise Refusal('Inconsistent time/IP observability')
        if ip['missing_events'] or ip['invalid_events']:
            excluded.append({'persona': key[1], 'date_local': key[0], 'reason': 'incomplete_ip_observability'})
            continue
        parts[part].append(row)
    if seen != set(coverage):
        raise Refusal('Missing usable rows from export')
    usable = [{'persona': r['persona'], 'day': r['date_local'], 'partition': p, 'status': 'usable'}
              for p, rows in parts.items() for r in rows]
    # Include every role in the gate even if exclusions removed all its rows.
    usable += [{'persona': role, 'day': '2026-10-30', 'partition': 'fit', 'status': 'excluded'} for role in method.ROLES]
    gates = readiness.history_gates(usable)
    if (not gates['history_gates_pass'] or gates['eligible_roles'] != 6 or len(parts['fit']) < 30):
        raise Refusal('Insufficient eligible closed history after IP exclusions')
    for rows in parts.values():
        rows.sort(key=lambda r: (r['date_local'], r['persona']))
    data['_input_sha256'] = manifest['dataset_sha256']
    return data, parts, excluded, gates


def fit_ae(parts):
    import numpy as np
    import torch
    torch.manual_seed(method.METHOD['seed'])
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    arrays = {p: np.log1p(np.asarray([[r['features'][f] for f in FEATURES] for r in rows], dtype=np.float64)) for p, rows in parts.items()}
    mean, std = arrays['fit'].mean(axis=0), arrays['fit'].std(axis=0)
    constant = arrays['fit'].max(axis=0) == arrays['fit'].min(axis=0)
    # Summation rounding can give identical log-counts a tiny nonzero std.
    # Exact repeated inputs must retain the contract's constant-feature scale1.
    mean[constant] = arrays['fit'][0, constant]
    if sum(~constant) < 2:
        raise Refusal('Insufficient varying fitting features')
    scale = np.where(constant, 1., std)
    tensors = {p: torch.tensor(((a - mean) / scale).astype(np.float32)) for p, a in arrays.items()}
    if any(not torch.isfinite(t).all() for t in tensors.values()):
        raise Refusal('Nonfinite standardized features')
    model = method.build_ae().cpu()
    opt = torch.optim.Adam(model.parameters(), lr=method.METHOD['learning_rate'], weight_decay=method.METHOD['weight_decay'])
    best, state, selected = math.inf, None, 0
    for epoch in range(method.METHOD['epochs']):
        model.train()
        opt.zero_grad()
        loss = ((model(tensors['fit']) - tensors['fit']) ** 2).mean()
        if not torch.isfinite(loss): raise Refusal('Nonfinite fitting loss')
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), method.METHOD['gradient_clip'], error_if_nonfinite=True)
        opt.step()
        model.eval()
        with torch.inference_mode(): val = float(((model(tensors['validation']) - tensors['validation']) ** 2).mean())
        if not math.isfinite(val): raise Refusal('Nonfinite validation loss')
        if val < best:
            best, selected = val, epoch + 1
            state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(state, strict=True)
    model.eval()
    return model, {'mean': mean.tolist(), 'scale': scale.tolist(), 'transform': 'log1p_then_standardize',
                   'constant_features': [FEATURES[i] for i in range(8) if constant[i]]}, best, selected


def score_rows(model, scaler, references, rows):
    """Internal inference on already prepared closed rows, not a live API entry point."""
    import numpy as np
    import torch
    raw = np.asarray([[r['features'][f] for f in FEATURES] for r in rows], dtype=float)
    tensor = torch.tensor(((np.log1p(raw) - scaler['mean']) / scaler['scale']).astype(np.float32))
    if not torch.isfinite(tensor).all(): raise Refusal('Nonfinite scoring input')
    with torch.inference_mode(): errors = ((model(tensor) - tensor) ** 2).mean(dim=1).tolist()
    if any(not math.isfinite(e) for e in errors): raise Refusal('Nonfinite reconstruction error')
    return [{'persona': r['persona'], 'date_local': r['date_local'], **method.context_scores(references, r), 'ae': e}
            for r, e in zip(rows, errors)]


def load_bundle(directory, *, expected_scope_sha256, allow_synthetic=False, _verify_in_progress=False):
    import torch
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('run_kind') != 'controlled_aws_lab' and not (allow_synthetic and manifest.get('run_kind') == 'synthetic_contract_test'):
        raise Refusal('Synthetic/unknown bundle cannot be loaded as real-study artifacts')
    if manifest.get('reloaded_score_parity') is not True and not _verify_in_progress:
        raise Refusal('Bundle reload verification incomplete')
    if manifest.get('scope_sha256') != expected_scope_sha256 or not isinstance(expected_scope_sha256, str) or len(expected_scope_sha256) != 64:
        raise Refusal('Bundle account/stack scope differs')
    if (manifest.get('profile') != method.METHOD['profile'] or manifest.get('method') != method.METHOD
            or manifest.get('source_sha256') != source_hashes() or manifest.get('feature_contract_sha256') != CONTRACT_SHA
            or manifest.get('data_source_sha256') != exporter.hashes()):
        raise Refusal('Bundle method/source contract differs')
    for name in ('weights.pt', 'scaler.json', 'references.json', 'normal_report.json'):
        if sha(directory / name) != manifest['artifact_sha256'].get(name):
            raise Refusal('Bundle artifact changed')
    checkpoint = torch.load(directory / 'weights.pt', map_location='cpu', weights_only=True)
    if checkpoint.get('profile') != method.METHOD['profile'] or checkpoint.get('features') != FEATURES:
        raise Refusal('Checkpoint profile/order differs')
    model = method.build_ae()
    model.load_state_dict(checkpoint['state_dict'], strict=True)
    if any(not torch.isfinite(p).all() for p in model.parameters()): raise Refusal('Nonfinite model parameters')
    model.eval()
    scaler = json.loads((directory / 'scaler.json').read_text())
    if (scaler.get('transform') != 'log1p_then_standardize' or len(scaler['mean']) != 8 or len(scaler['scale']) != 8
            or any(not math.isfinite(v) for v in scaler['mean']) or any(not math.isfinite(v) or v <= 0 for v in scaler['scale'])):
        raise Refusal('Invalid scaler')
    references = json.loads((directory / 'references.json').read_text())
    probabilities = list(references.get('personal', {}).values()) + [references.get('population', {})]
    if (set(references.get('personal', {})) != set(method.ROLES)
            or any(set(prob) != set(method.DOMAIN) or any(not math.isfinite(p) or p <= 0 or p > 1 for p in prob.values())
                   or not math.isclose(sum(prob.values()), 1., abs_tol=1e-12) for prob in probabilities)
            or not math.isfinite(references['volume_center']) or not math.isfinite(references['volume_scale'])
            or references['volume_scale'] <= 0):
        raise Refusal('Invalid frozen references')
    return model, scaler, references, manifest


def train(directory, output, now=None, *, synthetic=False):
    output = Path(output).resolve()
    if output.exists() or output == (ROOT / 'ml/models').resolve() or (ROOT / 'ml/models').resolve() in output.parents:
        raise Refusal('Use a fresh private candidate bundle path')
    before = source_hashes()
    data, parts, excluded, gates = prepare(directory, now)
    references = method.fit_references(parts['fit'])
    model, scaler, best, epoch = fit_ae(parts)
    scored = {p: score_rows(model, scaler, references, rows) for p, rows in parts.items() if p != 'fit'}
    calibration = method.calibrate(scored['normal_calibration'], references)
    if source_hashes() != before or sha(Path(directory) / 'dataset.json') != data['_input_sha256']:
        raise Refusal('Training source or dataset changed during run')
    import torch
    output.mkdir(parents=True, exist_ok=False)
    torch.save({'profile': method.METHOD['profile'], 'features': FEATURES, 'state_dict': model.state_dict()}, output / 'weights.pt')
    report = {'validation': scored['validation'], 'normal_calibration': scored['normal_calibration'], 'calibration': calibration,
              'validation_summary': method.validation_summary(scored['validation'], calibration)}
    for name, value in [('scaler.json', scaler), ('references.json', references), ('normal_report.json', report)]:
        (output / name).write_bytes(exporter.canonical(value))
    manifest = {'profile': method.METHOD['profile'], 'method': method.METHOD, 'source_sha256': before,
                'feature_contract_sha256': CONTRACT_SHA, 'dataset_sha256': data['_input_sha256'],
                'data_source_sha256': data['provenance']['source_sha256'], 'scope_sha256': data['provenance']['scope_sha256'],
                'artifact_sha256': {name: sha(output / name) for name in ('weights.pt', 'scaler.json', 'references.json', 'normal_report.json')},
                'partition_rows': {p: len(rows) for p, rows in parts.items()}, 'excluded_rows': excluded,
                'history_gates': gates, 'best_validation_mse': best, 'selected_epoch': epoch,
                'ae_parameters': sum(p.numel() for p in model.parameters()),
                'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'environment': {name: version(name) for name in ('torch', 'numpy')},
                'run_kind': 'synthetic_contract_test' if synthetic else 'controlled_aws_lab',
                'evaluation_status': 'normal_calibration_only', 'activated': False, 'reloaded_score_parity': False}
    (output / 'manifest.json').write_bytes(exporter.canonical(manifest))
    reloaded, saved_scaler, saved_refs, _ = load_bundle(output, expected_scope_sha256=manifest['scope_sha256'],
                    allow_synthetic=synthetic, _verify_in_progress=True)
    again = score_rows(reloaded, saved_scaler, saved_refs, parts['normal_calibration'])
    if again != scored['normal_calibration']:
        raise Refusal('Reload score parity failed; bundle is not qualified')
    manifest['reloaded_score_parity'] = True
    (output / 'manifest.json').write_bytes(exporter.canonical(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True, type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    try:
        if args.check_only:
            _, parts, excluded, _ = prepare(args.data)
            result = {'ready': True, 'partition_rows': {p: len(r) for p, r in parts.items()}, 'excluded_rows': len(excluded), 'trained': False}
        else:
            if args.out is None: parser.error('--out required for training')
            result = train(args.data, args.out)
        print(json.dumps(result))
        return 0
    except Refusal as error:
        print('Training refused: ' + str(error), file=sys.stderr)
        return 1
    except Exception:
        print('Training stopped; check local audited contracts and fresh output. No raw events displayed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
