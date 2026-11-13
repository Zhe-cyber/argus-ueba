"""Pinned CLUE familiarity development comparison; no live I/O or model activation."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import account_familiarity as familiarity
from scripts.personal_baseline import alert, either, document_digest, quantile_linear
from scripts.clue_familiarity_projection import project
from scripts.clue_native_projection import project_rows
from scripts.export_clue_dataset import Prefix
from scripts.evaluate_personal_baseline import verify_inputs, next_day, write_new
from scripts.train_clue_ae import select, sha
from scripts.build_clue_replay import candidate, residuals

METHODS = ('resource', 'joint', 'ae', 'ae_or_joint')


def index_projection(rows, frozen):
    index = {(r['user'], r['date']): r for r in rows}
    if len(index) != len(rows) or set(index) != {(r['user'], r['date']) for r in frozen}:
        raise ValueError('Familiarity/native account-days differ')
    for old in frozen:
        new = index[old['user'], old['date']]
        if (new['event_count'] != old['features']['event_count']
                or len(new['resources']) != old['features']['unique_paths']
                or len(new['actions']) != old['features']['unique_actions']
                or new['path_event_count'] != old['coverage']['path_events']
                or new['coverage']['missing_required_paths'] != old['coverage']['missing_required_paths']
                or new['coverage']['unknown_action_events'] != old['coverage']['unknown_action_events']
                or new['capture_boundary'] != old['capture_boundary']):
            raise ValueError('Familiarity projection differs from native counts')
    return index


def take(index, rows):
    return [index[r['user'], r['date']] for r in rows]


def summary(records):
    if len({(r['account'], r['date']) for r in records}) != len(records):
        raise ValueError('Duplicate report account-days')
    common = [r for r in records if all(r['alerts'][m] is not None for m in METHODS)]
    return {'rows': len(records), 'accounts': len({r['account'] for r in records}),
            'common_scorable_rows': len(common), 'common_accounts': len({r['account'] for r in common}),
            'methods': {m: {'scored_rows': sum(r['alerts'][m] is not None for r in records),
                            'unavailable_rows': sum(r['alerts'][m] is None for r in records),
                            'alerts': sum(r['alerts'][m] is True for r in records),
                            'common_alerts': sum(r['alerts'][m] is True for r in common),
                            'common_alert_fraction': sum(r['alerts'][m] is True for r in common) / len(common) if common else None}
                        for m in METHODS},
            'availability_status_counts': {m: dict(sorted(Counter(r['statuses'][m] for r in records).items()))
                                           for m in ('resource', 'joint')}}


def score_rows(native_rows, resource_rows, reference, calibration, model, scaler, aliases, ae_threshold):
    if [(r['user'], r['date']) for r in native_rows] != [(r['user'], r['date']) for r in resource_rows]:
        raise ValueError('Inference rows misaligned')
    ae_values = residuals(native_rows, model, scaler).mean(axis=1).tolist() if native_rows else []
    result = []
    for native, row, ae_value in zip(native_rows, resource_rows, ae_values):
        value = familiarity.score(reference, row)
        decisions = {m: alert(value['scores'][m], calibration[m]['threshold']) for m in ('resource', 'joint')}
        decisions['ae'] = alert(ae_value, ae_threshold)
        decisions['ae_or_joint'] = either(decisions['ae'], decisions['joint'])
        result.append({'account': aliases[row['user']], 'date': row['date'],
                       'scores': {**value['scores'], 'ae_raw_mse': ae_value},
                       'alerts': decisions, 'statuses': value['statuses'], 'dimensions': value['dimensions']})
    return result


def run(dataset, bundle, prefix_path, plan_path, output):
    output = Path(output).resolve()
    if output.exists() or not output.is_relative_to((ROOT / 'data/processed').resolve()):
        raise ValueError('Use a new private data/processed directory')
    manifest, plan, data, population, parts, bindings = verify_inputs(dataset, bundle, prefix_path, plan_path)
    # Pin/native checks precede trusted model deserialization.
    _, _, _, _, model, scaler = candidate(dataset, bundle)
    cuts = manifest['cutoffs_utc']
    index = index_projection(project(Prefix(prefix_path).events()), data['rows'])
    fitting = take(index, parts[1])
    normal_cal = take(index, parts[3])
    reference = familiarity.fit(fitting, next_day(cuts[0]), cuts[1])
    calibration = familiarity.calibrate(reference, normal_cal, next_day(cuts[2]), cuts[3])
    reference_digest = document_digest(reference.document())
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / 'reference.json', reference.document())
    write_new(output / 'normal_calibration.json', calibration)
    restored = familiarity.load_reference(json.loads((output / 'reference.json').read_text()))
    if document_digest(restored.document()) != reference_digest or any(
            familiarity.score(reference, r) != familiarity.score(restored, r) for r in normal_cal):
        raise ValueError('Persisted reference inference differs')
    reference = restored
    aliases = {u: f'cohort-{i + 1}' for i, u in enumerate(population)}
    infer = lambda native, resource: score_rows(native, resource, reference, calibration, model, scaler,
                                              aliases, manifest['threshold_raw_mse'])
    validation = infer(parts[2], take(index, parts[2]))
    calibrated = infer(parts[3], normal_cal)
    normal = infer(parts[4], take(index, parts[4]))
    if sum(r['alerts']['ae'] for r in normal) != 2 or not math_close(
            quantile_linear([r['scores']['ae_raw_mse'] for r in calibrated]), manifest['threshold_raw_mse']):
        raise ValueError('Frozen AE normal/calibration result differs')
    cases, switched = [], []
    earlier_keys = {(r['user'], r['date']) for p in parts[:4] for r in p}
    for case in plan['cases']:
        mapping = {case['left']: case['right'], case['right']: case['left']}
        native = project_rows(Prefix(prefix_path).events(), mapping, plan['switch_day_utc'])
        selected, changed = select({'rows': native, 'provenance': data['provenance']}, cuts)
        if selected != population or changed[:4] != parts[:4]:
            raise ValueError('Switch changed earlier native partitions')
        changed_index = index_projection(project(Prefix(prefix_path).events(), mapping, plan['switch_day_utc']), native)
        if any(changed_index[key] != index[key] for key in earlier_keys):
            raise ValueError('Switch changed fitting/calibration familiarity history')
        target = [r for r in changed[4] if r['user'] in mapping]
        records = infer(target, take(changed_index, target))
        for record, row in zip(records, target):
            record['operated_by'] = aliases[mapping[row['user']]]
        switched.extend(records)
        cases.append({'case_id': case['case_id'], 'summary': summary(records), 'days': records,
                      'owner_active_dates_without_actor_activity': {
                          aliases[u]: sorted({r['date'] for r in parts[4] if r['user'] == u}
                                             - {r['date'] for r in target if r['user'] == u}) for u in mapping},
                      'normal_controls': summary([r for r in normal if r['account'] not in {aliases[u] for u in mapping}])})
    if len(switched) != 25 or any(r['alerts']['ae'] for r in switched):
        raise ValueError('Frozen AE 25-day zero-alert switch result differs')
    if (any(sha(path) != digest for path, digest in bindings.values())
            or reference_digest != document_digest(reference.document())):
        raise ValueError('Frozen inputs or reference changed')
    report = {'schema_version': 1, 'method': familiarity.METHOD, 'status': 'development_only', 'activated': False,
              'computed_at_utc': datetime.now(timezone.utc).isoformat(),
              'method_spec': 'specs/W6-account-familiarity-development.md; fixed in eb03e80 before candidate scoring',
              'bindings': {name + '_sha256': digest for name, (_, digest) in bindings.items()},
              'code_canonical_lf_sha256': {name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                         for name in ('account_familiarity.py', 'clue_familiarity_projection.py',
                                                      'resource_observability.py', 'evaluate_account_familiarity.py')},
              'reference_sha256': sha(output / 'reference.json'), 'calibration_sha256': sha(output / 'normal_calibration.json'),
              'cutoffs_utc': cuts, 'frozen_population': len(population),
              'fitting_eligible_accounts': {dim: sum(n >= familiarity.MIN_DATES for n in d.days.values())
                                            for dim, d in reference.dimensions.items()},
              'thresholds': {'ae': manifest['threshold_raw_mse'], **{m: c['threshold'] for m, c in calibration.items()}},
              'validation_normal_retrospective': summary(validation), 'calibration_normal': summary(calibrated),
              'development_normal': summary(normal), 'development_normal_days': normal,
              'development_switches': summary(switched), 'cases': cases,
              'cases_with_any_alert': {m: sum(any(r['alerts'][m] is True for r in case['days']) for case in cases) for m in METHODS},
              'checks': {'native_counts_match': True, 'earlier_partitions_unchanged': True, 'frozen_ae_reproduced': True,
                         'reference_saved_before_case_scoring': True, 'json_reload_scores_identical': True,
                         'frozen_inputs_and_reference_unchanged': True},
              'environment': {name: version(name) for name in ('torch', 'numpy', 'scikit-learn', 'joblib')},
              'limitations': ['Previously inspected August 5-9 and three cases are development only, not a clean test.',
                             'Literal path equality does not prove physical-object identity, ownership or recipient permissions.',
                             'Entirely unseen resources and insufficient history are unavailable, not normal; report reduced denominators.',
                             'Globally unseen tokens are excluded from the contrast and separately reported, not detected by this rule.',
                             'Normal controls overlap across cases; correlated days are not independent evidence.',
                             'Validation alert counts apply later calibration thresholds retrospectively, not prospective validation.',
                             'Incidence contrast is a heuristic, not SHAP, probability, intent or proven compromise.',
                             'Single-service CLUE results do not validate AWS/Cloudflare/GitHub or authorize live scoring.']}
    write_new(output / 'development_report.json', report)
    return report


def math_close(a, b):
    import math
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-8)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('data', 'bundle', 'prefix', 'plan', 'out'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        result = run(args.data, args.bundle, args.prefix, args.plan, args.out)
        print(json.dumps({k: result[k] for k in ('status', 'thresholds', 'fitting_eligible_accounts',
                                                'development_normal', 'development_switches', 'cases_with_any_alert', 'checks')}))
    except Exception as error:
        print(f'Familiarity comparison stopped: {type(error).__name__}; inspect private outputs, no native records displayed.', file=sys.stderr)
        sys.exit(1)
