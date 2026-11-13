"""Release-gated CLUE evaluation. No live inference, cloud API or model fitting."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import train_shared_core_ae as training
from scripts import shared_core_features as features, shared_core_scenarios as scenarios
from scripts.shared_core_reader import MAX_COMPRESSED, MAX_EXPANDED, MAX_LINE, MAX_EVENTS

ARCHIVE_SHA = '0c9eadb104acf1da6de738ba9babe957c83cd8602a01fa6d846a6ea4a6611d96'
TEST_WINDOW = ('2017-08-11', '2017-08-24')
DEV_WINDOW = ('2017-08-05', '2017-08-09')
RELEASE_SOURCES = ['scripts/evaluate_shared_core_ae.py', 'scripts/tests/test_shared_core_evaluation.py',
                   'docs/SHARED_CORE_EVALUATOR_RELEASE.md', 'scripts/shared_core_features.py',
                   'scripts/shared_core_scenarios.py', 'scripts/shared_core_reader.py']


def archive_hash(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        while block := source.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def stream_archive(path, end):
    """Caller must verify its release before iteration; one boundary row closes end day."""
    if Path(path).stat().st_size > MAX_COMPRESSED:
        raise ValueError('Compressed archive bound')
    with ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != 'clue.json' or members[0].file_size > MAX_EXPANDED or members[0].flag_bits & 1:
            raise ValueError('Unexpected archive member')
        expanded = count = previous_id = 0
        previous_day = None
        with archive.open(members[0]) as source:
            while line := source.readline(MAX_LINE + 1):
                expanded += len(line); count += 1
                if len(line) > MAX_LINE or expanded > MAX_EXPANDED or count > MAX_EVENTS or not line.endswith(b'\n'):
                    raise ValueError('Native streaming bound/incomplete line')
                row = json.loads(line)
                if not isinstance(row, dict) or type(row.get('id')) is not int or row['id'] <= previous_id:
                    raise ValueError('Native ID order/conflict')
                day = features.instant(row['time']).date().isoformat()
                if previous_day is not None and day < previous_day:
                    raise ValueError('Cross-day reversal')
                previous_day, previous_id = day, row['id']
                yield row
                if day > end:
                    return


def candidate_scorer(candidate, data_path, prereg_path):
    import numpy as np
    import torch
    candidate = Path(candidate)
    manifest = json.loads((candidate / 'manifest.json').read_bytes())
    prereg = json.loads(Path(prereg_path).read_bytes())
    if manifest.get('profile') != features.PROFILE or manifest.get('method') != training.METHOD or prereg.get('method') != training.METHOD:
        raise ValueError('Candidate method differs')
    expected_sources = {name: training.sha(ROOT / name) for name in training.SOURCE_FILES}
    if manifest['source_hashes'] != expected_sources or prereg['source_hashes'] != expected_sources:
        raise ValueError('Training-frozen sources changed')
    if manifest['preregistration_sha256'] != training.sha(prereg_path) or manifest['data_sha256'] != training.sha(data_path) or prereg['data_sha256'] != training.sha(data_path):
        raise ValueError('Candidate data/preregistration differs')
    if manifest['model_sha256'] != training.sha(candidate / 'model.pt') or manifest['scaler_sha256'] != training.sha(candidate / 'scaler.json'):
        raise ValueError('Candidate artifact hash mismatch')
    data = training.load_data(data_path)
    scaler = json.loads((candidate / 'scaler.json').read_bytes())
    mean, scale = np.asarray(scaler['mean']), np.asarray(scaler['scale'])
    if scaler['features'] != features.FEATURES or mean.shape != (5,) or scale.shape != (5,) or not np.all(np.isfinite(mean)) or not np.all(np.isfinite(scale)) or not np.all(scale > 0):
        raise ValueError('Invalid saved scaler')
    torch.set_num_threads(1); torch.use_deterministic_algorithms(True)
    model = training.build_model()
    model.load_state_dict(torch.load(candidate / 'model.pt', weights_only=True, map_location='cpu')); model.eval()

    def score(vector):
        raw = training.matrix([{'features': vector}])
        x = torch.tensor((raw - mean) / scale, dtype=torch.float32)
        with torch.no_grad():
            error = float(((model(x) - x) ** 2).mean(dim=1)[0])
        baseline = float(np.maximum(0, x.numpy()).max())
        if not np.isfinite(error) or not np.isfinite(baseline):
            raise ValueError('Nonfinite score')
        return {'ae': error, 'max_deviation': baseline}

    # Verify frozen thresholds from original normal calibration, not test rows.
    calibration = training.partitions(data)[2]
    calibration_scores = [score(row['features']) for row in calibration]
    raw_calibration = training.matrix(calibration)
    calibration_x = torch.tensor((raw_calibration-mean)/scale, dtype=torch.float32)
    with torch.no_grad():
        batch_errors = ((model(calibration_x)-calibration_x)**2).mean(dim=1).numpy().astype(float)
    batch_baseline = np.maximum(0, calibration_x.numpy()).max(axis=1).astype(float)
    single_errors = np.asarray([row['ae'] for row in calibration_scores])
    max_difference = float(np.max(np.abs(single_errors-batch_errors)))
    if max_difference > 1e-5:
        raise ValueError('Inference/calibration batch numerical discrepancy exceeds pre-release engineering tolerance')
    manifest = dict(manifest)
    original_thresholds = manifest['thresholds']
    manifest['evaluation_numerics'] = {'inference': 'CPU float32 single-row, mean over feature dimension',
        'calibration_parity': 'original whole-calibration batch', 'max_absolute_single_batch_difference': max_difference,
        'engineering_tolerance_not_decision_margin': 1e-5,
        'calibration_policy': 'same normal rows and higher quantiles, canonical single-row inference before reserved release',
        'single_row_alerts_at_original_training_cutoffs': {str(b): {detector: sum(row[detector] > manifest['thresholds'][str(b)][detector]['threshold'] for row in calibration_scores)
                                                for detector in ['ae','max_deviation']} for b in training.METHOD['budgets']}}
    for budget in training.METHOD['budgets']:
        for detector in ['ae', 'max_deviation']:
            values = batch_errors if detector == 'ae' else batch_baseline
            threshold = float(np.quantile(values, 1-budget, method='higher'))
            if threshold != manifest['thresholds'][str(budget)][detector]['threshold']:
                raise ValueError('Frozen calibration threshold parity failed')
    # Keep the immutable training artifact. Freeze a transparent numerical-path
    # supplement before test access, never an epsilon margin or attack-based tuning.
    canonical_thresholds = {}
    for budget in training.METHOD['budgets']:
        canonical_thresholds[str(budget)] = {}
        for detector in ['ae', 'max_deviation']:
            values = np.asarray([row[detector] for row in calibration_scores])
            threshold = float(np.quantile(values, 1-budget, method='higher'))
            canonical_thresholds[str(budget)][detector] = {
                'threshold': threshold, 'calibration_alert_fraction': float(np.mean(values > threshold))}
    manifest['training_thresholds'] = original_thresholds
    manifest['thresholds'] = canonical_thresholds
    manifest['evaluation_numerics']['threshold_deltas_from_training'] = {
        str(b): {d: canonical_thresholds[str(b)][d]['threshold']-original_thresholds[str(b)][d]['threshold']
                 for d in ['ae','max_deviation']} for b in training.METHOD['budgets']}
    return score, manifest, data


def metrics(normal, cases, thresholds):
    import numpy as np
    from sklearn.metrics import roc_auc_score, average_precision_score
    result = {}
    for family in sorted(scenarios.FAMILIES):
        positive = [row for row in cases if row['family'] == family]
        detectors = {}
        for detector in ['ae', 'max_deviation']:
            negatives = [row['scores'][detector] for row in normal]
            positives = [row['scores'][detector] for row in positive]
            y = [0]*len(negatives) + [1]*len(positives)
            values = negatives + positives
            detectors[detector] = {'auroc': float(roc_auc_score(y, values)) if negatives and positives else None,
                'average_precision': float(average_precision_score(y, values)) if negatives and positives else None,
                'normal_days': len(negatives), 'injected_cases': len(positives),
                'injected_prevalence': len(positives)/len(values) if values else None, 'budgets': {}}
            for budget in training.METHOD['budgets']:
                threshold = thresholds[str(budget)][detector]['threshold']
                detectors[detector]['budgets'][str(budget)] = {
                    'threshold': threshold,
                    'normal_alerts': sum(value > threshold for value in negatives),
                    'normal_alert_fraction': float(np.mean(np.asarray(negatives) > threshold)) if negatives else None,
                    'case_alerts': sum(value > threshold for value in positives),
                    'case_recall': float(np.mean(np.asarray(positives) > threshold)) if positives else None}
        result[family] = detectors
    return result


def analyse(events, population, window, score, thresholds):
    """Engineering-testable composition of the already fixed native transformations."""
    population = set(population); targets = dict(scenarios.pairs(sorted(population)))
    donor_accounts = set(targets.values())
    unpaired_accounts = population-set(targets)-donor_accounts
    non_target_days = Counter()
    history, windows, native = features.History(), {}, defaultdict(list)
    current, complete = None, False
    past, normal, cases = [], [], []
    exclusions = {family: Counter() for family in scenarios.FAMILIES}
    observed, unscored, zero_change = set(), Counter(), Counter()

    def finish():
        snapshots = {account: history.snapshot(day) for account, day in windows.items()}
        in_window = current is not None and window[0] <= current <= window[1]
        for account, day in sorted(windows.items()):
            snapshot = snapshots[account]
            if current <= '2017-08-09':
                past.append({'account': account, 'day': current, **snapshot})
            if in_window:
                observed.add(account)
                if account in donor_accounts:
                    non_target_days['donor_only'] += 1
                elif account in unpaired_accounts:
                    non_target_days['unpaired'] += 1
                if snapshot['eligible']:
                    normal.append({'account': account, 'day': current, 'features': snapshot['features'], 'scores': score(snapshot['features'])})
                else:
                    unscored['cold_start' if snapshot['cold_start'] else 'input_quality'] += 1
                state = history.state.get(day.key[:3], (0, frozenset(), None))
                for family in sorted(scenarios.FAMILIES):
                    if family == 'account_switch' and account not in targets:
                        continue
                    if not snapshot['eligible']:
                        exclusions[family]['unscorable_original'] += 1; continue
                    donor = targets.get(account)
                    if family == 'account_switch' and (donor not in snapshots or not snapshots[donor]['eligible']):
                        exclusions[family]['donor_inactive_or_unscorable'] += 1; continue
                    if day.count > scenarios.MAX_DAY_EVENTS:
                        exclusions[family]['safety_cap'] += 1; continue
                    modified, reason = scenarios.generate(family, native[account], account, current, state[1],
                        donor=native.get(donor) if family == 'account_switch' else None)
                    if modified is None:
                        exclusions[family][reason] += 1; continue
                    variant = features.Day()
                    for event in modified:
                        variant.add(features.project_clue(event, synthetic=True))
                    if variant.key != day.key:
                        raise ValueError('Scenario changed target identity/source/day')
                    candidate = history.snapshot(variant)
                    if not candidate['eligible']:
                        exclusions[family]['unscorable_variant'] += 1; continue
                    same = candidate['features'] == snapshot['features']
                    zero_change[family] += same
                    cases.append({'account': account, 'day': current, 'family': family,
                                  'features': candidate['features'], 'zero_feature_change': same,
                                  'original_scores': normal[-1]['scores'], 'scores': score(candidate['features'])})
        for day in windows.values():
            history.commit_original(day)

    for row in events:
        day = features.instant(row['time']).date().isoformat()
        if current is not None and day < current:
            raise ValueError('Cross-day reversal')
        if current is not None and day != current:
            finish(); windows, native = {}, defaultdict(list)
        if day > window[1]:
            complete = True; break
        current = day
        if day < '2017-07-07' or row.get('uidType') != 'name':
            continue
        account = hashlib.sha256(('clue-7119953:' + row['uid']).encode()).hexdigest()
        if account not in population:
            continue
        event = features.project_clue(row)
        bucket = windows.setdefault(account, features.Day()); bucket.add(event)
        if window[0] <= day <= window[1] and len(native[account]) <= scenarios.MAX_DAY_EVENTS:
            native[account].append(row)
    if not complete:
        raise ValueError('No post-window boundary: final test day may be partial')
    return {'normal_rows': normal, 'case_rows': cases, 'past_rows': past,
            'summary': {'normal_scored_days': len(normal), 'normal_unscored': dict(unscored),
                'observed_identities': len(observed), 'population': len(population),
                'identities_without_test_activity': len(population-observed),
                'generated_cases': dict(Counter(row['family'] for row in cases)),
                'exclusions': {family: dict(counts) for family, counts in exclusions.items()},
                'switch_design': {'pairs': len(targets), 'target_accounts': len(targets),
                                  'donor_only_accounts': len(donor_accounts), 'unpaired_accounts': len(unpaired_accounts),
                                  'non_target_observed_days': dict(non_target_days)},
                'zero_feature_change': dict(zero_change)},
            'metrics': metrics(normal, cases, thresholds)}


def rehearsal(candidate, data_path, prereg, archive, output):
    score, manifest, data = candidate_scorer(candidate, data_path, prereg)
    if archive_hash(archive) != ARCHIVE_SHA:
        raise ValueError('Official archive SHA mismatch')
    result = analyse(stream_archive(archive, DEV_WINDOW[1]), data['population'], DEV_WINDOW, score, manifest['thresholds'])
    if result['past_rows'] != data['rows']:
        raise ValueError('Full ZIP/prefix feature and history parity failed')
    output = training.private_new(output)
    report = {'status': 'passed_engineering_only', 'window': list(DEV_WINDOW),
              'prefix_full_zip_feature_parity': True, 'summary': result['summary'],
              'reserved_access': False, 'data_sha256': training.sha(data_path),
              'manifest_sha256': training.sha(Path(candidate)/'manifest.json'),
              'evaluation_numerics': manifest['evaluation_numerics'],
              'evaluation_thresholds': manifest['thresholds'],
              'evaluator_sha256': training.sha(__file__), 'archive_sha256': ARCHIVE_SHA}
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def release(candidate, data_path, prereg, archive, rehearsal_path, output):
    _, manifest, _ = candidate_scorer(candidate, data_path, prereg)
    check = json.loads(Path(rehearsal_path).read_bytes())
    if check.get('status') != 'passed_engineering_only' or check.get('window') != list(DEV_WINDOW) or check.get('reserved_access') is not False or check.get('evaluator_sha256') != training.sha(__file__) or check.get('manifest_sha256') != training.sha(Path(candidate)/'manifest.json') or check.get('data_sha256') != training.sha(data_path) or check.get('evaluation_thresholds') != manifest['thresholds']:
        raise ValueError('Successful source-matched rehearsal required')
    if archive_hash(archive) != ARCHIVE_SHA:
        raise ValueError('Official archive hash mismatch')
    output = training.private_new(output)
    bound = {'archive': Path(archive), 'data': Path(data_path), 'preregistration': Path(prereg),
             'manifest': Path(candidate)/'manifest.json', 'model': Path(candidate)/'model.pt',
             'scaler': Path(candidate)/'scaler.json', 'rehearsal': Path(rehearsal_path)}
    record = {'kind': 'shared_core_reserved_release_v1', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'window': list(TEST_WINDOW), 'source_hashes': {name: training.sha(ROOT/name) for name in RELEASE_SOURCES},
              'artifacts': {name: {'path': str(path.resolve()), 'sha256': archive_hash(path) if name=='archive' else training.sha(path)} for name,path in bound.items()},
              'evaluation_thresholds': manifest['thresholds'], 'training_thresholds': manifest['training_thresholds'],
              'evaluation_numerics': manifest['evaluation_numerics'],
              'live_activation': False}
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(record, indent=2), encoding='utf-8')
    return {'release_sha256': training.sha(output), 'window': list(TEST_WINDOW)}


def evaluate(release_path, expected_sha, output):
    if training.sha(release_path) != expected_sha:
        raise ValueError('Release hash mismatch; no reserved access')
    record = json.loads(Path(release_path).read_bytes())
    if record.get('kind') != 'shared_core_reserved_release_v1' or record.get('window') != list(TEST_WINDOW) or record['source_hashes'] != {name: training.sha(ROOT/name) for name in RELEASE_SOURCES}:
        raise ValueError('Evaluator release mismatch; no reserved access')
    if set(record['artifacts']) != {'archive','data','preregistration','manifest','model','scaler','rehearsal'} or record['artifacts']['archive']['sha256'] != ARCHIVE_SHA or record.get('live_activation') is not False:
        raise ValueError('Unexpected release artifacts or official source; no reserved access')
    for name, item in record['artifacts'].items():
        actual = archive_hash(item['path']) if name=='archive' else training.sha(item['path'])
        if actual != item['sha256']:
            raise ValueError('Released artifact changed; no reserved access')
    paths = {name: Path(item['path']) for name,item in record['artifacts'].items()}
    if paths['manifest'].resolve() != (paths['model'].parent/'manifest.json').resolve() or paths['scaler'].resolve() != (paths['model'].parent/'scaler.json').resolve():
        raise ValueError('Candidate artifact paths disagree')
    score, manifest, data = candidate_scorer(paths['model'].parent, paths['data'], paths['preregistration'])
    if manifest['thresholds'] != record['evaluation_thresholds'] or manifest['evaluation_numerics'] != record['evaluation_numerics']:
        raise ValueError('Released inference calibration changed; no reserved access')
    output = training.private_new(output); output.mkdir(parents=True)
    receipt = {'release_sha256': expected_sha, 'access_started_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'started'}
    (output/'access-receipt.json').write_text(json.dumps(receipt, indent=2))
    try:
        result = analyse(stream_archive(paths['archive'], TEST_WINDOW[1]), data['population'], TEST_WINDOW, score, manifest['thresholds'])
        if result['past_rows'] != data['rows']:
            raise ValueError('Historical feature parity changed')
        result.pop('past_rows')
        result.update(profile=features.PROFILE, window=list(TEST_WINDOW), release_sha256=expected_sha,
                      evaluation_numerics=manifest['evaluation_numerics'],
                      training_thresholds=manifest['training_thresholds'], evaluation_thresholds=manifest['thresholds'],
                      status='reserved_normal_and_injected_scenarios', activated=False,
                      evidence='Semi-synthetic: publisher-described normal activity with fixed injected deviations',
                      limitations=['Not real attack accuracy or live transfer validation.',
                                   'Dependent account-days/counterfactuals; descriptive metrics, no independent-binomial guarantee.',
                                   'Per-scenario AP depends on reported injection prevalence; omitted cases are not negatives.',
                                   'One-day counterfactuals; original events alone update subsequent history.'])
        (output/'evaluation.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
        receipt['status'] = 'completed'
    except Exception as exc:
        receipt.update(status='failed_after_access_started', error_type=type(exc).__name__)
        raise
    finally:
        (output/'access-receipt.json').write_text(json.dumps(receipt, indent=2))
    return {'status': result['status'], 'summary': result['summary'], 'metrics': result['metrics'], 'activated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['rehearse', 'release', 'evaluate'])
    for name in ['candidate', 'data', 'prereg', 'archive', 'rehearsal', 'release', 'release-sha', 'out']:
        parser.add_argument('--'+name, required=name=='out')
    args = parser.parse_args()
    if args.mode == 'evaluate':
        if not args.release or not args.release_sha: parser.error('Release path and expected hash required')
        result = evaluate(args.release, args.release_sha, args.out)
    else:
        if not all([args.candidate,args.data,args.prereg,args.archive]): parser.error('Candidate/data/prereg/archive required')
        if args.mode == 'rehearse': result = rehearsal(args.candidate,args.data,args.prereg,args.archive,args.out)
        else:
            if not args.rehearsal: parser.error('Rehearsal report required')
            result = release(args.candidate,args.data,args.prereg,args.archive,args.rehearsal,args.out)
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
