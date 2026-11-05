"""W33 reserved evaluator: one release-gated January test of A, B, C, C-norm and BL.

Offline only. Detector A is the frozen shared_behavior_core_v1 model scored by its
own frozen loader on W23 features and W23 history; B/C/C-norm/BL use the W33
training artifacts on W33 features and history. Injections reuse the frozen W23
scenario generator unchanged, with the W33 fitting-selected cohort as input.
Nothing here fits a model, changes a threshold or activates live scoring.

Gates: `rehearse` (pre-test parity, no test rows), `release` (exclusive receipt,
before the 15 Nov 23:59 MYT freeze), `evaluate` (only on 16-17 Nov MYT, once per
experiment via an exclusive access claim).
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import clue_v2_access as access, clue_v2_features as v2, clue_v2_reader as reader
from scripts import export_clue_v2 as exporter, train_clue_v2 as trainer, report_clue_v2_validation as validation_report
from scripts import shared_core_features as w23, shared_core_scenarios as scenarios
from scripts import evaluate_shared_core_ae as v1_evaluator, train_shared_core_ae as v1_training

TEST = tuple(access.POLICY['reserved'])
START = access.POLICY['warmup'][0]
DETECTORS = ['A', 'B', 'C', 'C_norm', 'BL']
BUDGETS = ['0.01', '0.05']
FAMILIES = sorted(scenarios.FAMILIES)
MYT = ZoneInfo('Asia/Kuala_Lumpur')
RELEASE_DEADLINE = datetime.fromisoformat(access.POLICY['freeze_deadline_myt'])
EXECUTION_DATES = tuple(access.POLICY['test_execution_dates_myt'])
ACCESS_CLAIM = 'data/processed/clue-ae-v2/w33-reserved-access-claim.json'
RELEASE_KIND = 'w33_reserved_release_v1'
REHEARSAL_STATUS = 'passed_pretest_parity_no_test_rows'
EVALUATOR_SOURCES = ['specs/W33-clue-ae-v2.md', 'scripts/evaluate_clue_v2.py', 'scripts/tests/test_clue_v2_evaluation.py',
                     'scripts/shared_core_scenarios.py', 'scripts/evaluate_shared_core_ae.py',
                     'scripts/train_shared_core_ae.py', 'scripts/report_clue_v2_validation.py',
                     'scripts/tests/test_clue_v2_validation_report.py'] + trainer.TRAINING_SOURCES
COMPARISONS = [('B', 'A'), ('C', 'B'), ('C_norm', 'C'), ('BL', 'C')]


def sha(path):
    return access.sha(path)


def canonical_write(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as handle:
        handle.write(access.canonical(document) + b'\n')
        handle.flush(); os.fsync(handle.fileno())


def stream_window(archive, end):
    """Native rows dated START..end. The first later row only closes `end` (date decoded, never yielded).

    Callers must verify a release before calling with a reserved `end`."""
    previous_day, previous_id = None, 0
    lines = reader._lines(archive)
    try:
        for line in lines:
            day = reader._timestamp_day(line)
            if previous_day is not None and day < previous_day:
                raise ValueError('Cross-day reversal; unsupported archive shape')
            previous_day = day
            if day > end:
                return
            row = json.loads(line)
            if type(row.get('id')) is not int or row['id'] <= previous_id:
                raise ValueError('Native ID order/conflict')
            previous_id = row['id']
            if day >= START:
                yield row
    finally:
        lines.close()
    raise ValueError('No post-window boundary row: the final day may be partial')


# --- Scorers ---------------------------------------------------------------------------------

def v1_artifacts(release_path):
    """Verify the frozen v1 release file, its artifacts and its sources; return (record, candidate paths)."""
    record = json.loads(Path(release_path).read_bytes())
    if record.get('kind') != 'shared_core_reserved_release_v1':
        raise ValueError('Not the frozen v1 release')
    if record['source_hashes'] != {name: v1_training.sha(v1_evaluator.ROOT / name) for name in v1_evaluator.RELEASE_SOURCES}:
        raise ValueError('Frozen v1 sources changed')
    for name, item in record['artifacts'].items():
        if name != 'archive' and v1_training.sha(item['path']) != item['sha256']:
            raise ValueError('Frozen v1 artifact changed')
    paths = {name: Path(item['path']) for name, item in record['artifacts'].items()}
    return record, paths


def load_scorers(prereg_path, training_dir, v1_release):
    """Load and verify every detector; returns a dict with scoring functions, thresholds and the cohort."""
    record, cohort, _ = trainer.verify_preregistration(prereg_path)
    training_dir = Path(training_dir)
    manifest = json.loads((training_dir / 'manifest.json').read_bytes())
    if (manifest.get('preregistration_sha256') != record['receipt_sha256'] or manifest.get('activated') is not False
            or manifest.get('status') != 'trained_not_frozen_release'
            or manifest['references_sha256'] != sha(training_dir / 'c_norm_references.json')
            or manifest['thresholds_sha256'] != sha(training_dir / 'thresholds.json')
            or any(manifest['detectors'][d]['model_sha256'] != sha(training_dir / d / 'model.pt')
                   or manifest['detectors'][d]['scaler_sha256'] != sha(training_dir / d / 'scaler.json') for d in ('B', 'C'))):
        raise ValueError('W33 training artifacts differ from their manifest')
    b_model, b_scaler = trainer._reload_detector(training_dir / 'B', trainer.METHOD['detectors']['B']['architecture'])
    c_model, c_scaler = trainer._reload_detector(training_dir / 'C', trainer.METHOD['detectors']['C']['architecture'])
    references = json.loads((training_dir / 'c_norm_references.json').read_bytes())
    if set(references) != set(cohort):
        raise ValueError('C-norm references do not cover exactly the cohort')
    stored = json.loads((training_dir / 'thresholds.json').read_bytes())
    v1_record, paths = v1_artifacts(v1_release)
    a_score, a_manifest, _ = v1_evaluator.candidate_scorer(paths['model'].parent, paths['data'], paths['preregistration'])
    if a_manifest['thresholds'] != v1_record['evaluation_thresholds']:
        raise ValueError('Detector A canonical thresholds differ from the frozen v1 release')
    thresholds = {'A': {b: a_manifest['thresholds'][b]['ae']['threshold'] for b in BUDGETS}}
    for name in ('B', 'C', 'C_norm', 'BL'):
        item = stored[name]
        thresholds[name] = {b: item[b]['threshold'] for b in BUDGETS} if item['status'] == 'available' else None

    def score_v2(snapshot, account):
        result = dict.fromkeys(['B', 'C', 'C_norm', 'BL'])
        if not snapshot['five_feature_eligible']:
            return result
        features = snapshot['features']
        # B uses only the five W23-meaning columns; feature 7 is not an input, so a placeholder cannot matter.
        five = dict(features, new_resource_share=0.0 if features['new_resource_share'] is None else features['new_resource_share'])
        result['B'] = trainer.score_rows(b_model, b_scaler.transform(trainer.matrix([{'features': five}], v2.FEATURES[:5])))[0]
        if snapshot['nine_feature_eligible']:
            x = c_scaler.transform(trainer.matrix([{'features': features}], v2.FEATURES))
            result['C'] = trainer.score_rows(c_model, x)[0]
            result['BL'] = float(max(0.0, float(x[0].max())))
            reference = references[account]
            if reference['status'] == 'available':
                result['C_norm'] = result['C'] / reference['denominator']
        return result

    def score_a(snapshot):
        return a_score(snapshot['features'])['ae'] if snapshot['eligible'] else None

    return {'cohort': cohort, 'score_v2': score_v2, 'score_a': score_a, 'thresholds': thresholds,
            'training_manifest_sha256': sha(training_dir / 'manifest.json'), 'v1_release_sha256': sha(v1_release),
            'preregistration_sha256': record['receipt_sha256'], 'export_path': record['export']['path']}


def verify_validation_report(report_path, export_dir):
    """The supplied report must equal the report regenerated from the bound validation export, byte for byte.

    Regenerated in memory only; nothing is written or overwritten."""
    export_dir = Path(export_dir)
    manifest_bytes = (export_dir / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    rows_bytes = (export_dir / 'rows-validation.jsonl').read_bytes()
    if (hashlib.sha256(rows_bytes).hexdigest() != manifest['partition_rows_sha256']['validation']
            or manifest.get('feature_contract_sha256') != v2.contract_sha256()):
        raise ValueError('Validation export binding differs')
    rows = [json.loads(line) for line in rows_bytes.splitlines() if line]
    if any(row.get('partition') != 'validation' for row in rows):
        raise ValueError('Validation row file contains another partition')
    hashes = {'export_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
              'validation_rows_sha256': hashlib.sha256(rows_bytes).hexdigest(),
              'feature_contract_sha256': v2.contract_sha256(),
              'source_sha256': reader.source_hashes(validation_report.REPORT_SOURCES)}
    expected = validation_report.markdown(validation_report.describe(rows), hashes).encode('utf-8')
    if Path(report_path).read_bytes() != expected:
        raise ValueError('Validation report is not the one produced from the bound export and report sources')
    return hashlib.sha256(expected).hexdigest()


# --- Chronological analysis --------------------------------------------------------------------

def analyse(events, cohort, window, score_v2, score_a, collect_rows=False):
    """Replay history from warm-up; score each window day once, with variants from one start-of-day state."""
    cohort = sorted(cohort)
    members = set(cohort)
    targets = dict(scenarios.pairs(cohort))  # frozen W23 pairing algorithm, W33 cohort as declared input
    v2_history, w23_history = v2.History(), w23.History()
    windows, native, current = {}, defaultdict(list), None
    normal, cases, past = [], [], []
    exclusions = {family: Counter() for family in FAMILIES}  # pre-generation reasons only
    generation = {family: {'generated': 0, 'retained_scored_by_any': 0, 'unscorable_by_all': 0,
                           'scored_by_detector': dict.fromkeys(DETECTORS, 0),
                           'unscored_by_detector': dict.fromkeys(DETECTORS, 0)} for family in FAMILIES}
    unscored = Counter()

    def unchanged(variant_vector, original_vector):
        """True/False only for two comparable vectors; None means unavailable, never 'identical'."""
        if variant_vector is None or original_vector is None:
            return None
        return variant_vector == original_vector

    def scores(v2_snapshot, w23_snapshot, account):
        result = score_v2(v2_snapshot, account)
        result['A'] = score_a(w23_snapshot)
        return result

    def finish():
        v2_snaps = {account: v2_history.snapshot(day) for account, day in windows.items()}
        w23_snaps = {account: w23_history.snapshot(day.core) for account, day in windows.items()}
        if collect_rows and current <= access.POLICY['gap_history_only'][1]:
            part = exporter.partition(current)
            if part in exporter.ROW_PARTITIONS:
                past.extend({'partition': part, 'account': account, 'day': current, **v2_snaps[account]}
                            for account in sorted(windows))
        if window is not None and window[0] <= current <= window[1]:
            for account, day in sorted(windows.items()):
                original = scores(v2_snaps[account], w23_snaps[account], account)
                if all(value is None for value in original.values()):
                    unscored['invalid_input' if v2_snaps[account]['status'] == 'invalid_input' else 'cold_start'] += 1
                normal.append({'account': account, 'day': current, 'scores': original,
                               'v2_status': v2_snaps[account]['status'], 'a_eligible': w23_snaps[account]['eligible']})
                state = v2_history.state.get(day.key[:3])
                prior_actions = state.actions if state else frozenset()
                for family in FAMILIES:
                    if family == 'account_switch' and account not in targets:
                        continue
                    if v2_snaps[account]['status'] == 'invalid_input':
                        exclusions[family]['invalid_original'] += 1; continue
                    if all(value is None for value in original.values()):
                        exclusions[family]['unscorable_original'] += 1; continue
                    donor = targets.get(account)
                    if family == 'account_switch' and (donor not in v2_snaps or v2_snaps[donor]['status'] != 'eligible'):
                        exclusions[family]['donor_inactive_or_unscorable'] += 1; continue
                    if day.core.count > scenarios.MAX_DAY_EVENTS:
                        exclusions[family]['safety_cap'] += 1; continue
                    modified, reason = scenarios.generate(family, native[account], account, current, prior_actions,
                                                          donor=native.get(donor) if family == 'account_switch' else None)
                    if modified is None:
                        exclusions[family][reason] += 1; continue
                    variant = v2.V2Day()
                    for event in modified:
                        variant.add(w23.project_clue(event, synthetic=True))
                    if variant.key != day.key:
                        raise ValueError('Scenario changed target identity, source or day')
                    stats = generation[family]
                    stats['generated'] += 1  # counted on successful generation, before any scoring
                    v_v2, v_w23 = v2_history.snapshot(variant), w23_history.snapshot(variant.core)
                    variant_scores = scores(v_v2, v_w23, account)
                    for detector, value in variant_scores.items():
                        stats['scored_by_detector' if value is not None else 'unscored_by_detector'][detector] += 1
                    if all(value is None for value in variant_scores.values()):
                        stats['unscorable_by_all'] += 1; continue
                    stats['retained_scored_by_any'] += 1
                    cases.append({'account': account, 'day': current, 'family': family, 'scores': variant_scores,
                                  'original_scores': original,
                                  'feature_unchanged': {'v2': unchanged(v_v2['features'], v2_snaps[account]['features']),
                                                        'w23': unchanged(v_w23['features'], w23_snaps[account]['features'])}})
        for day in windows.values():  # originals only, once, after every variant of the day
            v2_history.commit_original(day)
            w23_history.commit_original(day.core)

    for row in events:
        day = w23.instant(row['time']).date().isoformat()
        if current is not None and day < current:
            raise ValueError('Cross-day reversal')
        if current is not None and day != current:
            finish(); windows, native = {}, defaultdict(list)
        current = day
        if row.get('uidType') != 'name':
            continue
        event = w23.project_clue(row)
        if event.account not in members:
            continue
        windows.setdefault(event.account, v2.V2Day()).add(event)
        if window is not None and window[0] <= day <= window[1] and len(native[event.account]) <= scenarios.MAX_DAY_EVENTS:
            native[event.account].append(row)
    if current is not None:
        finish()
    for family, stats in generation.items():
        retained = sum(row['family'] == family for row in cases)
        if (stats['generated'] != stats['retained_scored_by_any'] + stats['unscorable_by_all']
                or stats['retained_scored_by_any'] != retained
                or any(stats['scored_by_detector'][d] + stats['unscored_by_detector'][d] != stats['generated']
                       for d in DETECTORS)):
            raise ValueError(f'Generation accounting does not reconcile for {family}')
    return {'normal': normal, 'cases': cases, 'past_rows': past, 'unscored_normal': dict(unscored),
            'generation': generation,
            'exclusions': {family: dict(sorted(counts.items())) for family, counts in exclusions.items()},
            'switch_design': {'pairs': len(targets), 'unpaired_accounts': len(cohort) - 2 * len(targets)}}


# --- Metrics -----------------------------------------------------------------------------------

def _common(row):
    return all(row['scores'][d] is not None for d in DETECTORS)


def metrics(normal, cases, thresholds, common=False):
    from sklearn.metrics import roc_auc_score, average_precision_score
    normal = [row for row in normal if not common or _common(row)]
    cases = [row for row in cases if not common or _common(row)]
    result = {}
    for family in FAMILIES:
        result[family] = {}
        for detector in DETECTORS:
            negatives = [row['scores'][detector] for row in normal if row['scores'][detector] is not None]
            positives = [row['scores'][detector] for row in cases if row['family'] == family and row['scores'][detector] is not None]
            both = bool(negatives) and bool(positives)
            y, values = [0] * len(negatives) + [1] * len(positives), negatives + positives
            entry = {'normal_days': len(negatives), 'injected_cases': len(positives),
                     'injected_prevalence': len(positives) / len(values) if values else None,
                     'auroc': float(roc_auc_score(y, values)) if both else None,
                     'average_precision': float(average_precision_score(y, values)) if both else None, 'budgets': {}}
            changes = [row['scores'][detector] - row['original_scores'][detector] for row in cases
                       if row['family'] == family and row['scores'][detector] is not None
                       and row['original_scores'][detector] is not None]
            entry['paired_change'] = ({'cases': len(changes), 'median': statistics.median(changes),
                                       'positive_fraction': sum(c > 0 for c in changes) / len(changes)} if changes else None)
            for budget in BUDGETS:
                cut = thresholds[detector][budget] if thresholds.get(detector) else None
                entry['budgets'][budget] = None if cut is None else {
                    'threshold': cut, 'normal_alerts': sum(v > cut for v in negatives),
                    'normal_alert_fraction': sum(v > cut for v in negatives) / len(negatives) if negatives else None,
                    'case_alerts': sum(v > cut for v in positives),
                    'case_recall': sum(v > cut for v in positives) / len(positives) if positives else None}
            result[family][detector] = entry
    return result


def dominance(table, coverage):
    """W33 section 7 descriptive convention on the common evaluation; never a winner or activation rule."""
    out = {}
    for left, right in COMPARISONS:
        out[f'{left}_vs_{right}'] = {}
        for budget in BUDGETS:
            cells = [(table[f][left]['budgets'][budget], table[f][right]['budgets'][budget]) for f in FAMILIES]
            if any(a is None or b is None or a['case_recall'] is None or b['case_recall'] is None for a, b in cells):
                out[f'{left}_vs_{right}'][budget] = 'not_comparable'
                continue
            recalls_ok = all(a['case_recall'] >= b['case_recall'] for a, b in cells)
            any_higher = any(a['case_recall'] > b['case_recall'] for a, b in cells)
            alert_ok = cells[0][0]['normal_alert_fraction'] <= cells[0][1]['normal_alert_fraction']
            dominant = recalls_ok and any_higher and alert_ok and coverage[left] >= coverage[right]
            out[f'{left}_vs_{right}'][budget] = 'descriptively_dominant' if dominant else 'trade_off_or_no_gain'
    return out


def summarise(result, thresholds):
    coverage = {d: sum(row['scores'][d] is not None for row in result['normal']) for d in DETECTORS}
    common_table = metrics(result['normal'], result['cases'], thresholds, common=True)
    return {'normal_days_observed': len(result['normal']), 'normal_scored_by_detector': coverage,
            'normal_common_days': sum(_common(row) for row in result['normal']),
            'generation': result['generation'],
            'cases_common': dict(Counter(row['family'] for row in result['cases'] if _common(row))),
            'feature_unchanged': {family: {view: dict(Counter(
                {True: 'unchanged', False: 'changed', None: 'unavailable'}[row['feature_unchanged'][view]]
                for row in result['cases'] if row['family'] == family)) for view in ('v2', 'w23')} for family in FAMILIES},
            'unscored_normal': result['unscored_normal'], 'exclusions': result['exclusions'],
            'switch_design': result['switch_design'],
            'metrics_all_supported': metrics(result['normal'], result['cases'], thresholds),
            'metrics_common': common_table, 'dominance_common': dominance(common_table, coverage)}


# --- Gates -------------------------------------------------------------------------------------

def _now(now):
    return (now or datetime.now(timezone.utc)).astimezone(MYT)


def rehearse(reader_receipt, prereg_path, training_dir, v1_release, output):
    """Pre-test parity: replay to 14 Jan, require exported-row and threshold parity. No test rows, no scenarios."""
    output = trainer.private_new(output)
    loaded = load_scorers(prereg_path, training_dir, v1_release)
    record, cohort, rows = trainer.verify_preregistration(prereg_path)
    _, archive = reader.verify_reader(reader_receipt)
    result = analyse(reader.pretest_events(archive), cohort, None, loaded['score_v2'], loaded['score_a'], collect_rows=True)
    exported = sorted((row for part in exporter.ROW_PARTITIONS for row in rows[part]), key=lambda r: (r['day'], r['account']))
    replayed = sorted(result['past_rows'], key=lambda r: (r['day'], r['account']))
    if replayed != exported:
        raise ValueError('Evaluator feature/history replay differs from the bound export')
    calibration = trainer.nine_rows(rows['calibration'])
    recomputed = {name: [] for name in ('B', 'C', 'BL', 'C_norm')}
    for row in calibration:
        values = loaded['score_v2'](row, row['account'])
        for name in recomputed:
            if values[name] is not None:
                recomputed[name].append(values[name])
    stored = json.loads((Path(training_dir) / 'thresholds.json').read_bytes())
    if any(trainer.threshold(recomputed[name]) != stored[name] for name in recomputed):
        raise ValueError('Calibration thresholds do not reproduce through the evaluator path')
    report = {'status': REHEARSAL_STATUS, 'rows_compared': len(exported), 'thresholds_reproduced': True,
              'detector_a_thresholds': loaded['thresholds']['A'], 'test_rows_accessed': False,
              'evaluator_source_sha256': reader.source_hashes(EVALUATOR_SOURCES),
              'training_manifest_sha256': loaded['training_manifest_sha256'],
              'preregistration_sha256': loaded['preregistration_sha256'], 'v1_release_sha256': loaded['v1_release_sha256']}
    canonical_write(output, report)
    return report


def _utc_clock():
    return datetime.now(timezone.utc)


def _before_freeze(clock):
    moment = clock()
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError('Aware clock required')
    if moment.astimezone(MYT) > RELEASE_DEADLINE:
        raise ValueError('W33 freeze gate passed; no release (no-go)')
    return moment.astimezone(timezone.utc)


def release(reader_receipt, prereg_path, training_dir, v1_release, validation_report_path, rehearsal_path, output,
            clock=_utc_clock):
    _before_freeze(clock)
    output = trainer.private_new(output)
    loaded = load_scorers(prereg_path, training_dir, v1_release)
    check = json.loads(Path(rehearsal_path).read_bytes())
    sources = reader.source_hashes(EVALUATOR_SOURCES)
    if (check.get('status') != REHEARSAL_STATUS or check.get('test_rows_accessed') is not False
            or check.get('thresholds_reproduced') is not True
            or type(check.get('rows_compared')) is not int or check['rows_compared'] <= 0
            or check.get('evaluator_source_sha256') != sources
            or check.get('training_manifest_sha256') != loaded['training_manifest_sha256']
            or check.get('preregistration_sha256') != loaded['preregistration_sha256']
            or check.get('v1_release_sha256') != loaded['v1_release_sha256']
            or check.get('detector_a_thresholds') != loaded['thresholds']['A']):
        raise ValueError('A passing, source- and artifact-matched pre-test rehearsal is required')
    verify_validation_report(validation_report_path, loaded['export_path'])
    reader_doc, archive = reader.verify_reader(reader_receipt)
    training_dir = Path(training_dir)
    bound = {'archive': Path(archive), 'reader_receipt': Path(reader_receipt), 'preregistration': Path(prereg_path),
             'training_manifest': training_dir / 'manifest.json', 'B_model': training_dir / 'B/model.pt',
             'B_scaler': training_dir / 'B/scaler.json', 'C_model': training_dir / 'C/model.pt',
             'C_scaler': training_dir / 'C/scaler.json', 'c_norm_references': training_dir / 'c_norm_references.json',
             'thresholds': training_dir / 'thresholds.json', 'v1_release': Path(v1_release),
             'validation_report': Path(validation_report_path), 'rehearsal': Path(rehearsal_path)}
    artifacts = {name: {'path': str(path.resolve()), 'sha256': sha(path)} for name, path in bound.items()}
    completed = _before_freeze(clock)  # re-checked after all artifact work, immediately before finalising
    record = {'kind': RELEASE_KIND, 'profile': v2.PROFILE, 'created_at_utc': completed.isoformat(),
              'window': list(TEST), 'execution_dates_myt': list(EXECUTION_DATES), 'source_sha256': sources,
              'artifacts': artifacts, 'thresholds': loaded['thresholds'],
              'cohort_sha256': v2.digest(sorted(loaded['cohort'])),
              'reserved_access_performed': False, 'live_activation': False}
    record['release_sha256_body'] = hashlib.sha256(access.canonical(record)).hexdigest()
    canonical_write(output, record)
    return record


def _created_before_freeze(value):
    if not isinstance(value, str):
        raise ValueError('Release creation time missing')
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None or moment.utcoffset() != timezone.utc.utcoffset(None) or moment.isoformat() != value:
        raise ValueError('Release creation time must be canonical aware UTC')
    if moment.astimezone(MYT) > RELEASE_DEADLINE:
        raise ValueError('Release created after the W33 freeze gate')


def verify_release(release_path, expected_sha):
    if sha(release_path) != expected_sha:
        raise ValueError('Release hash mismatch; no reserved access')
    record = json.loads(Path(release_path).read_bytes())
    body = {key: value for key, value in record.items() if key != 'release_sha256_body'}
    if (record.get('kind') != RELEASE_KIND or record.get('window') != list(TEST)
            or record.get('release_sha256_body') != hashlib.sha256(access.canonical(body)).hexdigest()
            or record.get('source_sha256') != reader.source_hashes(EVALUATOR_SOURCES)
            or record.get('live_activation') is not False or record['artifacts']['archive']['sha256'] != access.ARCHIVE_SHA):
        raise ValueError('Evaluator release mismatch; no reserved access')
    _created_before_freeze(record.get('created_at_utc'))
    for name, item in record['artifacts'].items():
        if sha(item['path']) != item['sha256']:
            raise ValueError(f'Released artifact changed: {name}; no reserved access')
    return record


def evaluate(release_path, expected_sha, output, now=None):
    """The single W33 reserved access. Exclusive experiment claim; failures stay claimed and disclosed."""
    record = verify_release(release_path, expected_sha)
    if _now(now).date().isoformat() not in EXECUTION_DATES:
        raise ValueError('Outside the declared 16-17 Nov MYT execution window; no reserved access')
    output = trainer.private_new(output)
    paths = {name: item['path'] for name, item in record['artifacts'].items()}
    training_dir = Path(paths['training_manifest']).parent
    loaded = load_scorers(paths['preregistration'], training_dir, paths['v1_release'])
    if loaded['thresholds'] != record['thresholds'] or v2.digest(sorted(loaded['cohort'])) != record['cohort_sha256']:
        raise ValueError('Released scorers changed; no reserved access')
    claim = (ROOT / ACCESS_CLAIM).resolve()
    claim.parent.mkdir(parents=True, exist_ok=True)
    canonical_write(claim, {'experiment': 'W33', 'release_sha256': expected_sha, 'output': str(output),
                            'access_started_at_utc': datetime.now(timezone.utc).isoformat()})
    try:
        result = analyse(stream_window(paths['archive'], TEST[1]), loaded['cohort'], TEST,
                         loaded['score_v2'], loaded['score_a'])
        summary = summarise(result, loaded['thresholds'])
        output.mkdir()
        document = {'profile': v2.PROFILE, 'window': list(TEST), 'release_sha256': expected_sha,
                    'thresholds': loaded['thresholds'], 'summary': summary,
                    'evidence': 'Semi-synthetic: publisher-described normal activity with fixed injected deviations',
                    'activated': False, 'status': 'reserved_evaluation_completed',
                    'limitations': ['Not real attack accuracy or live transfer validation.',
                                    'Dependent account-days and paired variants; descriptive metrics only.',
                                    'Average precision depends on the reported injection prevalence; exclusions are not negatives.',
                                    'A uses its original frozen thresholds; its budget is not the December budget.']}
        canonical_write(output / 'evaluation.json', document)
        rows = {'normal': result['normal'], 'cases': result['cases']}
        canonical_write(output / 'scored-rows-private.json', rows)
    except Exception as error:
        canonical_write(Path(str(claim) + '.failed.json'), {'error_type': type(error).__name__,
                                                            'failed_at_utc': datetime.now(timezone.utc).isoformat()})
        raise
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    for mode in ('rehearse', 'release'):
        command = sub.add_parser(mode)
        for name in ('reader-receipt', 'prereg', 'training', 'v1-release', 'out'):
            command.add_argument('--' + name, required=True)
        if mode == 'release':
            command.add_argument('--validation-report', required=True)
            command.add_argument('--rehearsal', required=True)
    run = sub.add_parser('evaluate')
    run.add_argument('--release', required=True)
    run.add_argument('--release-sha', required=True)
    run.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        if args.mode == 'rehearse':
            result = rehearse(args.reader_receipt, args.prereg, args.training, args.v1_release, args.out)
            print(json.dumps({key: result[key] for key in ('status', 'rows_compared', 'thresholds_reproduced')}))
        elif args.mode == 'release':
            result = release(args.reader_receipt, args.prereg, args.training, args.v1_release,
                             args.validation_report, args.rehearsal, args.out)  # real clock
            print(json.dumps({'kind': result['kind'], 'release_file_sha256': sha(args.out), 'window': result['window']}))
        else:
            result = evaluate(args.release, args.release_sha, args.out)
            print(json.dumps({'status': result['status'], 'activated': False}))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print('W33 evaluator step failed closed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
