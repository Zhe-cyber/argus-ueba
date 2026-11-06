"""One preregistered inspected-data check; no training, fresh data or live I/O."""
import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import context_score_calibration as scoring
from scripts.export_clue_dataset import Prefix
from scripts.project_context_period import project
from scripts.evaluate_personal_baseline import PLAN_SHA256, MANIFEST_SHA256

PLAN = ROOT / 'specs/W29-action-mix-development-decision.md'
PLAN_SHA = '77b7feec5c5483b3620a3e78cad20993b9444e43a1a0dc0640f05f9147713f7c'
W8_SHA = '3b5806c902c8c51802c352e4426426c84b5f451cda47785890b969c2cb3714ca'
W10_SHA = '19eb77cb68deb4f702e25823a7d8ef323f506a265282dcae859629f411882aa9'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def switched_rows(rows, cases):
    """Whole donor-day relabelling is equivalent to the original native swap."""
    result = []
    used = [u for case in cases for u in (case['left'], case['right'])]
    if len(cases) != 3 or len(set(used)) != 6:
        raise ValueError('Require the original three disjoint pairs')
    for case in cases:
        mapping = {case['left']: case['right'], case['right']: case['left']}
        for row in rows:
            if row['user'] in mapping:
                item = copy.deepcopy(row)
                item['user'] = mapping[row['user']]
                result.append((case['case_id'], row['user'], item))
    return result


def decision(normal, cases):
    n = [r for r in normal if r['score'] is not None]
    c = [r for r in cases if r['score'] is not None]
    common_n = [r for r in n if r['ae'] is not None]
    common_c = [r for r in c if r['ae'] is not None]
    metrics = {}
    if common_n and common_c:
        from sklearn.metrics import roc_auc_score, average_precision_score
        labels = [0] * len(common_n) + [1] * len(common_c)
        for name in ('score', 'ae'):
            values = [r[name] for r in common_n + common_c]
            metrics[name] = {'auroc': float(roc_auc_score(labels, values)),
                             'average_precision': float(average_precision_score(labels, values))}
    gates = {
        'normal_coverage_at_least_90_percent': len(n) >= .9 * 191,
        'switch_coverage_at_least_90_percent': len(c) >= .9 * 25,
        'normal_alert_fraction_at_most_5_percent': bool(n) and sum(r['alert'] for r in n) / len(n) <= .05,
        'at_least_5_of_25_switch_alerts': sum(r['alert'] for r in c) >= 5,
        'at_least_two_pairs_with_alerts': len({r['case_id'] for r in c if r['alert']}) >= 2,
        'common_auroc_at_least_065': bool(metrics) and metrics['score']['auroc'] >= .65,
    }
    return {'decision': 'go_to_fresh_protocol_design_only' if all(gates.values()) else 'no_go',
            'gates': gates, 'normal_total': len(normal), 'normal_scored': len(n),
            'normal_alerts': sum(r['alert'] for r in n),
            'normal_statuses': dict(Counter(r['status'] for r in normal)),
            'switch_total': len(cases), 'switch_scored': len(c),
            'switch_alerts': sum(r['alert'] for r in c),
            'switch_statuses': dict(Counter(r['status'] for r in cases)),
            'per_pair': {key: {'rows': sum(r['case_id'] == key for r in cases),
                              'scored': sum(r['case_id'] == key for r in c),
                              'alerts': sum(r['case_id'] == key and r['alert'] for r in c)}
                         for key in sorted({r['case_id'] for r in cases})},
            'common_normal': len(common_n), 'common_switches': len(common_c),
            'common_positive_prevalence': len(common_c) / (len(common_n) + len(common_c)) if common_c else None,
            'common_metrics': metrics}


def run(prefix, manifest, switch_plan, dataset, output):
    output = Path(output).resolve()
    if output.exists() or not output.is_relative_to((ROOT / 'data/processed').resolve()):
        raise ValueError('Use a new private output directory')
    w8 = ROOT / 'data/processed/clue-context-feature-diagnostic-v1'
    w10 = ROOT / 'data/processed/clue-context-score-calibration-v1'
    old = ROOT / 'data/processed/clue-account-affinity-development-v1/development_report.json'
    bindings = {PLAN: PLAN_SHA, Path(manifest): MANIFEST_SHA256, Path(switch_plan): PLAN_SHA256,
                w8 / 'diagnostic_report.json': W8_SHA, w10 / 'calibration_gate_report.json': W10_SHA}
    if any(sha(p) != value for p, value in bindings.items()):
        raise ValueError('Preregistered plan or historical input differs')
    original, cal_report, cached = read(w8 / 'diagnostic_report.json'), read(w10 / 'calibration_gate_report.json'), read(old)
    bindings.update({Path(prefix): original['prefix_sha256'], Path(dataset): cached['bindings']['dataset_sha256'],
                     w8 / 'reference.json': original['reference_sha256'],
                     w10 / 'normal_calibration.json': cal_report['calibration_sha256'], old: sha(old)})
    for record, key in [(original, 'source_canonical_lf_sha256'), (cal_report, 'source_canonical_lf_sha256')]:
        for name, expected in record[key].items():
            if Path(name).name != name or hashlib.sha256((ROOT / 'scripts' / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() != expected:
                raise ValueError('Historical source differs')
    if any(sha(p) != value for p, value in bindings.items()):
        raise ValueError('Historical reference/calibration/prefix differs')
    calibration = read(w10 / 'normal_calibration.json')['action_mix']
    if calibration['gate'] != 'ready_for_development_comparison' or calibration['threshold'] != 0.8723298381957394:
        raise ValueError('Action calibration differs')
    ref = scoring.load_reference(read(w8 / 'reference.json'))
    before = ref.document()
    population = read(manifest)['fitting_population']
    plan = read(switch_plan)
    if plan['switch_day_utc'] != '2017-08-05' or plan['end_day_utc'] != '2017-08-09':
        raise ValueError('Historical switch window differs')
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'status': 'started', 'started_at_utc': datetime.now(timezone.utc).isoformat(),
               'plan_sha256': PLAN_SHA, 'source_sha256': sha(__file__), 'native_source': 'inspected_prefix_only'}
    (output / 'attempt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    # Only the previously inspected, bounded prefix can be read here.
    rows = project(Prefix(prefix).events(), set(population), '2017-08-05', '2017-08-09')
    if len(rows) != 191:
        raise ValueError('Original normal-day population differs')
    expected = {(r['user'], r['date']): r for r in read(dataset)['rows']
                if r['user'] in population and '2017-08-05' <= r['date'] <= '2017-08-09'}
    if set(expected) != {(r['user'], r['date']) for r in rows}:
        raise ValueError('Frozen day keys differ')
    for row in rows:
        old_row = expected[row['user'], row['date']]
        if (row['event_count'] != old_row['features']['event_count']
                or row['distinct_paths'] != old_row['features']['unique_paths']
                or len(row['views']['action_mix']) != old_row['features']['unique_actions']
                or row['coverage']['missing_required_paths'] != old_row['coverage']['missing_required_paths']
                or row['coverage']['unknown_action_events'] != old_row['coverage']['unknown_action_events']):
            raise ValueError('Frozen native count/coverage differs')
    aliases = {u: f'cohort-{i+1}' for i, u in enumerate(population)}
    normal_cache = {(r['account'], r['date']): r for r in cached['development_normal_days']}
    case_cache = {(case['case_id'], r['account'], r['date']): r for case in cached['cases'] for r in case['days']}
    def one(row, historical):
        result = scoring.score(ref, row)
        value = result['scores']['action_mix']
        return {'account': aliases[row['user']], 'date': row['date'], 'score': value,
                'status': result['statuses']['action_mix'],
                'alert': value > calibration['threshold'] if value is not None else None,
                'ae': historical['scores']['ae_raw_mse'], 'ae_alert': historical['alerts']['ae'],
                'unseen_category_mass': result['globally_unseen_category_mass']['action_mix']}
    normal = [one(r, normal_cache[aliases[r['user']], r['date']]) for r in rows]
    cases = []
    for case_id, actor, row in switched_rows(rows, plan['cases']):
        historical = case_cache[case_id, aliases[row['user']], row['date']]
        if historical['operated_by'] != aliases[actor]:
            raise ValueError('Donor/recipient alignment differs')
        cases.append({**one(row, historical), 'case_id': case_id})
    if len(cases) != 25 or len(case_cache) != 25 or len(normal_cache) != 191:
        raise ValueError('Historical denominators differ')
    if ref.document() != before or any(sha(p) != v for p, v in bindings.items()):
        raise ValueError('Frozen state/input changed')
    result = {'method': 'w29_existing_action_mix_control', 'status': 'development_only', 'activated': False,
              'computed_at_utc': datetime.now(timezone.utc).isoformat(),
              'threshold': calibration['threshold'], 'summary': decision(normal, cases),
              'normal_rows': normal, 'case_rows': cases,
              'bindings': {str(p): v for p, v in bindings.items()},
              'source_sha256': {name: sha(ROOT / 'scripts' / name) for name in
                                ['check_action_mix_development.py', 'context_score_calibration.py',
                                 'context_feature_diagnostic.py', 'project_context_period.py', 'export_clue_dataset.py']},
              'fresh_archive_opened': False, 'live_scores_written': False,
              'limitations': ['Previously inspected cases; selection influenced by prior experiments.',
                             'Cached comparator is the original ten-feature AE, not the five-feature candidate.',
                             'Correlated counterfactuals; no independent-test accuracy or transfer claim.',
                             'Action composition is insensitive to pure timing/volume changes.']}
    (output / 'development-decision.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    receipt.update(status='completed', result_sha256=sha(output / 'development-decision.json'))
    (output / 'attempt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('prefix', 'manifest', 'switch-plan', 'dataset', 'out'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    result = run(args.prefix, args.manifest, args.switch_plan, args.dataset, args.out)
    print(json.dumps({'threshold': result['threshold'], **result['summary']}))
