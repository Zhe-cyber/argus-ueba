"""W33 result packaging on synthetic evaluator output only; never the real archive, release or reserved rows."""
import csv
import hashlib
import json
import random

import pytest

from scripts import evaluate_clue_v2 as ev, package_clue_v2_results as pack, train_clue_v2 as trainer

SHA = 'f' * 64
KEY = 'acct_' + 'c' * 64


def synthetic(empty_family='account_switch'):
    """Evaluator-shaped output: C_norm unavailable at threshold level and on some rows; one family has no cases."""
    rng = random.Random(7)
    scores = lambda shift: {d: rng.random() + shift for d in ev.DETECTORS}
    normal = [{'account': KEY, 'day': '2018-01-15', 'scores': scores(0.0), 'v2_status': 'eligible', 'a_eligible': True}
              for _ in range(40)]
    for row in normal[:5]:
        row['scores']['C_norm'] = None
    cases = []
    for family in ev.FAMILIES:
        if family == empty_family:
            continue
        for i in range(12):
            original = scores(0.0)
            cases.append({'account': KEY, 'day': '2018-01-16', 'family': family, 'scores': scores(0.4),
                          'original_scores': original,
                          'feature_unchanged': {'v2': [False, True, None][i % 3], 'w23': False}})
    generation = {f: {'generated': sum(c['family'] == f for c in cases) + 1,
                      'retained_scored_by_any': sum(c['family'] == f for c in cases), 'unscorable_by_all': 1,
                      'scored_by_detector': {}, 'unscored_by_detector': {}} for f in ev.FAMILIES}
    thresholds = {d: {'0.01': 1.2, '0.05': 0.9} for d in ev.DETECTORS}
    thresholds['C_norm'] = None
    result = {'normal': normal, 'cases': cases, 'generation': generation, 'unscored_normal': {'cold_start': 3},
              'exclusions': {f: {'safety_cap': 1} if f == 'mass_access' else {} for f in ev.FAMILIES},
              'switch_design': {'pairs': 0, 'unpaired_accounts': 1}}
    document = {'profile': 'clue_ae_v2', 'window': ['2018-01-15', '2018-01-28'], 'release_sha256': SHA,
                'thresholds': thresholds, 'summary': json.loads(json.dumps(ev.summarise(result, thresholds))),
                'evidence': 'SYNTHETIC FIXTURE: not a W33 result', 'activated': False,
                'status': 'reserved_evaluation_completed', 'limitations': ['Fixture limitation.']}
    return document, {'normal': normal, 'cases': cases}


def write(tmp_path, document, rows):
    folder = tmp_path / 'evaluation'
    folder.mkdir()
    (folder / 'evaluation.json').write_text(json.dumps(document))
    (folder / 'scored-rows-private.json').write_text(json.dumps(rows))
    return folder


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(trainer, 'ROOT', tmp_path)
    return tmp_path


def test_package_writes_reconciled_aggregate_outputs(root):
    document, rows = synthetic()
    manifest = pack.package(write(root, document, rows), SHA, root / 'data/package')
    out = root / 'data/package'
    assert manifest['reconciled'] is True and manifest['contains_account_keys'] is False
    assert all(hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
               for name, digest in manifest['outputs'].items())
    assert {f'roc-pr-{f}.png' for f in ev.FAMILIES if f != 'account_switch'} <= set(manifest['outputs'])
    assert 'roc-pr-account_switch.png' not in manifest['outputs']  # no cases: no figure, not an empty curve
    text = (out / 'report.md').read_text(encoding='utf-8')
    assert 'SYNTHETIC FIXTURE' in text and 'safety_cap=1' in text and 'not negatives' in text
    for name in ('report.md', 'metrics.csv', 'manifest.json'):
        assert KEY not in (out / name).read_text(encoding='utf-8')


def test_csv_values_reconcile_exactly_and_unavailable_is_explicit(root):
    document, rows = synthetic()
    pack.package(write(root, document, rows), SHA, root / 'data/package')
    with (root / 'data/package/metrics.csv').open(encoding='utf-8', newline='') as handle:
        lines = list(csv.DictReader(handle))
    assert len(lines) == 2 * len(ev.FAMILIES) * len(ev.DETECTORS)
    cell = lambda view, f, d: next(l for l in lines if (l['view'], l['family'], l['detector']) == (view, f, d))
    summary = document['summary']
    assert float(cell('common', 'mass_access', 'C')['auroc']) == summary['metrics_common']['mass_access']['C']['auroc']
    assert cell('common', 'mass_access', 'C_norm')['threshold_0.01'] == 'unavailable'
    assert cell('common', 'account_switch', 'A')['auroc'] == 'unavailable'
    assert int(cell('all_supported', 'mass_access', 'C_norm')['normal_days']) == 35
    assert int(cell('common', 'mass_access', 'A')['normal_days']) == 35


@pytest.mark.parametrize('tamper', ['metric', 'generation', 'rows'])
def test_unreconciled_evaluation_is_refused_before_writing(root, tamper):
    document, rows = synthetic()
    if tamper == 'metric':
        document['summary']['metrics_common']['mass_access']['B']['auroc'] = 0.99
    elif tamper == 'generation':
        document['summary']['generation']['off_hours']['retained_scored_by_any'] += 1
    else:
        rows['cases'].pop()
    with pytest.raises(ValueError, match='reconcile'):
        pack.package(write(root, document, rows), SHA, root / 'data/package')
    assert not (root / 'data/package').exists()


@pytest.mark.parametrize('change', [{'release_sha256': 'e' * 64}, {'activated': True}, {'status': 'failed'}])
def test_only_a_completed_unactivated_evaluation_of_this_release_is_packaged(root, change):
    document, rows = synthetic()
    document.update(change)
    with pytest.raises(ValueError, match='release'):
        pack.package(write(root, document, rows), SHA, root / 'data/package')


def test_output_must_be_new_and_private(root):
    document, rows = synthetic()
    folder = write(root, document, rows)
    with pytest.raises(ValueError):
        pack.package(folder, SHA, root / 'outside')
    pack.package(folder, SHA, root / 'data/package')
    with pytest.raises(ValueError):
        pack.package(folder, SHA, root / 'data/package')
