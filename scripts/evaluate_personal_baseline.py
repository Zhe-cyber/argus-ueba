"""Bounded local CLUE development comparison. No downloads, live I/O or activation."""
from datetime import date, timedelta, datetime, timezone
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import personal_baseline as personal
from scripts.clue_native_projection import project_rows
from scripts.export_clue_dataset import Prefix
from scripts.train_clue_ae import load_dataset, select, sha
from scripts.build_clue_replay import candidate, residuals

MANIFEST_SHA256 = '0d620d90b85746021113a86f4656ec56e572eac8d89df149ee5c39d1b2e5fa8d'
PLAN_SHA256 = 'dd6835887e05356971a5985d962fd1c7d44fd619a1e596b475759d32aabe1892'
METHODS = ('population', 'personal', 'ae', 'ae_or_personal')


def next_day(value):
    return (date.fromisoformat(value) + timedelta(days=1)).isoformat()


def verify_inputs(dataset, bundle, prefix_path, plan_path):
    bundle = Path(bundle).resolve()
    manifest_path = bundle / 'clue_model_manifest.json'
    if sha(manifest_path) != MANIFEST_SHA256 or sha(plan_path) != PLAN_SHA256:
        raise ValueError('Use the pinned development manifest and existing switch plan')
    manifest, plan = json.loads(manifest_path.read_text()), json.loads(Path(plan_path).read_text())
    data, digest = load_dataset(dataset)
    if (digest != manifest['dataset_sha256'] or plan['manifest_sha256'] != MANIFEST_SHA256
            or plan['dataset_sha256'] != digest or plan['model_sha256'] != manifest['model_sha256']
            or plan['threshold_raw_mse'] != manifest['threshold_raw_mse'] or plan.get('executed') is not False
            or plan.get('profile') != manifest['profile']):
        raise ValueError('Frozen dataset/plan bindings differ')
    bindings = {'manifest': (manifest_path, MANIFEST_SHA256), 'dataset': (Path(dataset), digest),
                'plan': (Path(plan_path), PLAN_SHA256)}
    for kind in ('model', 'scaler'):
        artifact = (bundle / manifest[kind + '_path']).resolve()
        if artifact.parent != bundle or sha(artifact) != manifest[kind + '_sha256']:
            raise ValueError('Artifact path/hash differs; no deserialisation performed')
        bindings[kind] = artifact, manifest[kind + '_sha256']
    prefix = Prefix(prefix_path)
    if prefix.sha256 != data['provenance']['prefix_sha256']:
        raise ValueError('Native prefix differs')
    bindings['prefix'] = Path(prefix_path), prefix.sha256
    if plan['switch_day_utc'] != next_day(manifest['cutoffs_utc'][3]) or plan['end_day_utc'] != manifest['cutoffs_utc'][4]:
        raise ValueError('Development switch dates differ')
    used = [u for case in plan['cases'] for u in (case['left'], case['right'])]
    if (len(plan['cases']) != 3 or len(set(used)) != 6
            or any(u not in manifest['fitting_population'] for u in used)):
        raise ValueError('Require the original three disjoint pairs')
    normal = project_rows(prefix.events())
    if normal != data['rows']:
        raise ValueError('Unswitched native projection differs from the frozen export')
    population, parts = select(data, manifest['cutoffs_utc'])
    if population != manifest['fitting_population'] or [len(p) for p in parts[1:]] != [605, 188, 169, 191]:
        raise ValueError('Frozen development partitions differ')
    return manifest, plan, data, population, parts, bindings


def summaries(records):
    if len({(r['account'], r['date']) for r in records}) != len(records):
        raise ValueError('Repeated account-days cannot inflate an aggregate')
    common = [r for r in records if all(r['alerts'][k] is not None for k in METHODS)]
    return {'rows': len(records), 'common_scorable_rows': len(common),
            'common_account_count': len({r['account'] for r in common}),
            'methods': {kind: {'scored_rows': sum(r['alerts'][kind] is not None for r in records),
                               'unavailable_rows': sum(r['alerts'][kind] is None for r in records),
                               'alerts': sum(r['alerts'][kind] is True for r in records),
                               'common_rows_alerts': sum(r['alerts'][kind] is True for r in common),
                               'common_rows_alert_fraction': sum(r['alerts'][kind] is True for r in common) / len(common) if common else None}
                        for kind in METHODS}}


def score_rows(rows, reference, calibration, model, scaler, aliases, ae_threshold):
    ae_values = residuals(rows, model, scaler).mean(axis=1).tolist() if rows else []
    records = []
    for row, ae_value in zip(rows, ae_values):
        values = {kind: personal.score(reference, row, personal=kind == 'personal') for kind in ('population', 'personal')}
        decisions = {kind: personal.alert(values[kind]['score'], calibration[kind]['threshold']) for kind in values}
        decisions['ae'] = personal.alert(ae_value, ae_threshold)
        decisions['ae_or_personal'] = personal.either(decisions['ae'], decisions['personal'])
        records.append({'account': aliases[row['user']], 'date': row['date'],
                        'scores': {**{kind: result['score'] for kind, result in values.items()}, 'ae_raw_mse': ae_value},
                        'alerts': decisions, 'personal_status': values['personal']['status'],
                        'top_personal_deviations': sorted(values['personal']['components'], key=lambda c: c['contribution'], reverse=True)[:3]})
    return records


def write_new(path, document):
    with Path(path).open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(document, handle, indent=2, allow_nan=False)


def run(dataset, bundle, prefix_path, plan_path, output):
    output = Path(output).resolve()
    if output.exists() or not output.is_relative_to((ROOT / 'data/processed').resolve()):
        raise ValueError('Use a new private data/processed output directory in this checkout')
    manifest, plan, data, population, parts, bindings = verify_inputs(dataset, bundle, prefix_path, plan_path)
    # All bindings and the native projection are checked before any pickle/model is loaded.
    _, _, _, _, model, scaler = candidate(dataset, bundle)
    cuts = manifest['cutoffs_utc']
    reference = personal.fit_reference(parts[1], next_day(cuts[0]), cuts[1])
    reference = personal.load_reference(reference.document())  # Verify persisted-inference contract too.
    if set(reference.centres) != set(population):
        raise ValueError('Personal fitting population differs')
    calibration = {kind: personal.calibrate(reference, parts[3], next_day(cuts[2]), cuts[3], personal=kind == 'personal')
                   for kind in ('population', 'personal')}
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / 'reference.json', reference.document())
    write_new(output / 'normal_calibration.json', calibration)
    # The saved reference and thresholds exist before new development-case scoring.
    aliases = {u: f'cohort-{i + 1}' for i, u in enumerate(population)}
    score = lambda rows: score_rows(rows, reference, calibration, model, scaler, aliases, manifest['threshold_raw_mse'])
    validation, normal_cal, normal_dev = score(parts[2]), score(parts[3]), score(parts[4])
    if sum(r['alerts']['ae'] for r in normal_dev) != 2:
        raise ValueError('Original frozen normal AE classifications differ')
    import numpy as np
    if not np.isclose(np.quantile([r['scores']['ae_raw_mse'] for r in normal_cal], .99, method='linear'),
                      manifest['threshold_raw_mse'], rtol=1e-6, atol=1e-8):
        raise ValueError('Original normal AE threshold does not reproduce calibration')
    cases, switched_records = [], []
    for case in plan['cases']:
        left, right = case['left'], case['right']
        mapping = {left: right, right: left}
        changed = project_rows(Prefix(prefix_path).events(), mapping, plan['switch_day_utc'])
        switched_population, projected = select({'rows': changed, 'provenance': data['provenance']}, cuts)
        if switched_population != population or projected[:4] != parts[:4]:
            raise ValueError('Switch altered earlier data/reference/calibration')
        target = [row for row in projected[4] if row['user'] in mapping]
        records = score(target)
        switched_records.extend(records)
        owner_days = {u: {r['date'] for r in parts[4] if r['user'] == u} for u in mapping}
        active = {u: {r['date'] for r in target if r['user'] == u} for u in mapping}
        for record, row in zip(records, target):
            record['operated_by'] = aliases[mapping[row['user']]]
        cases.append({'case_id': case['case_id'], 'summary': summaries(records), 'days': records,
                      'owner_active_dates_without_actor_activity': {aliases[u]: sorted(owner_days[u] - active[u]) for u in mapping},
                      'normal_controls': summaries([r for r in normal_dev if r['account'] not in (aliases[left], aliases[right])])})
    if len(switched_records) != 25 or any(r['alerts']['ae'] for r in switched_records):
        raise ValueError('Original 25-day/zero-detection AE development result differs')
    if any(sha(path) != expected for path, expected in bindings.values()):
        raise ValueError('Frozen source input changed during execution')
    report = {'schema_version': 1, 'method': personal.METHOD, 'status': 'development_only', 'activated': False,
              'computed_at_utc': datetime.now(timezone.utc).isoformat(),
              'method_spec': 'specs/W4-personal-baseline-development.md; fixed before candidate scoring, on inspected data',
              'bindings': {name + '_sha256': digest for name, (_, digest) in bindings.items()},
              'code_canonical_lf_sha256': {name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                         for name in ('personal_baseline.py', 'clue_native_projection.py', 'evaluate_personal_baseline.py')},
              'reference_sha256': sha(output / 'reference.json'), 'calibration_sha256': sha(output / 'normal_calibration.json'),
              'cutoffs_utc': cuts, 'fitting_accounts': len(population), 'fitting_rows': len(parts[1]),
              'reference_scale_floor': personal.SCALE_FLOOR,
              'scale_floor_features': [f for f, scale in zip(personal.FEATURES, reference.scales) if scale == personal.SCALE_FLOOR],
              'thresholds': {'ae': manifest['threshold_raw_mse'], **{kind: c['threshold'] for kind, c in calibration.items()}},
              'validation_normal': summaries(validation), 'calibration_normal': summaries(normal_cal),
              'development_normal': summaries(normal_dev), 'development_normal_days': normal_dev,
              'development_switches': summaries(switched_records), 'cases': cases,
              'cases_with_any_alert': {kind: sum(any(r['alerts'][kind] is True for r in case['days']) for case in cases) for kind in METHODS},
              'checks': {'native_rebuild_matches_export': True, 'earlier_partitions_unchanged': True,
                         'original_ae_results_reproduced': True, 'frozen_inputs_unchanged': True, 'thresholds_saved_before_case_scoring': True},
              'environment': {name: version(name) for name in ('torch', 'numpy', 'scikit-learn', 'joblib')},
              'limitations': ['All 5–9 August records and original pairs were previously inspected: development evidence only.',
                             'Three cases and correlated days do not establish general attack effectiveness or an independent alert-rate guarantee.',
                             'Donor paths/resources are preserved; a reciprocal projection is not a proven feasible credential-compromise trace.',
                             'CLUE is a single storage service; this method/threshold is not activated or validated on AWS/Cloudflare/GitHub.',
                             'The ten counts are correlated; absolute deviations and scale floors are a heuristic statistical baseline, not probabilities or SHAP.',
                             'Normal controls repeat across cases. The aggregate normal report counts each original normal account-day once.']}
    write_new(output / 'development_report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('data', 'bundle', 'prefix', 'plan', 'out'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        report = run(args.data, args.bundle, args.prefix, args.plan, args.out)
        print(json.dumps({k: report[k] for k in ('status', 'activated', 'thresholds', 'development_normal', 'development_switches', 'checks')}))
        return 0
    except Exception as error:
        print(f'Development comparison stopped: {type(error).__name__}. Check bindings and private partial outputs; no raw records displayed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
