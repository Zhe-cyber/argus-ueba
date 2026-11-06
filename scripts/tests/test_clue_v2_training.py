"""W33 training tests on a synthetic export only; never the real export or archive."""
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from scripts import (clue_v2_access as access, clue_v2_features as features, clue_v2_reader as reader,
                     export_clue_v2 as exporter, train_clue_v2 as train)

ACCOUNTS = [f'acct-{i}' for i in range(8)]
SMALL_GATES = {'selected_accounts': 5, 'fit_rows': 100, 'validation_rows': 50, 'calibration_rows': 100}


def synthetic_rows(part, first, days, rng, accounts, resource_free_every=0):
    rows = []
    for offset in range(days):
        day = (date.fromisoformat(first) + timedelta(offset)).isoformat()
        for index, account in enumerate(accounts):
            count = int(rng.integers(1, 60)); actions = int(rng.integers(1, min(count, 6) + 1))
            resource_free = bool(resource_free_every) and (offset + index) % resource_free_every == 0
            values = {'event_count': count, 'unique_actions': actions,
                      'unique_resources': 0 if resource_free else int(rng.integers(1, count + 1)),
                      'off_hours_fraction': float(rng.random()), 'new_action_count': int(rng.integers(0, actions + 1)),
                      'volume_log_ratio': float(rng.normal()), 'new_resource_share': None if resource_free else float(rng.random()),
                      'action_mix_js_distance': float(rng.random()), 'hour_profile_js_distance': float(rng.random())}
            rows.append({'partition': part, 'account': account, 'day': day, 'status': 'eligible',
                         'prior_usable_days': 10, 'issues': {}, 'features': values,
                         'unavailable': {'new_resource_share': 'no_resource_today'} if resource_free else {},
                         'five_feature_eligible': True, 'nine_feature_eligible': not resource_free})
    return rows


def write_export(root, name='export', gates_pass=True, extra_cohort=(), mutate=None):
    """Synthetic export with manifest gate/coverage/provenance claims matching its own files."""
    rng = np.random.default_rng(7)
    parts = {'fit': synthetic_rows('fit', '2017-09-04', 30, rng, ACCOUNTS, resource_free_every=9),
             'validation': synthetic_rows('validation', '2017-11-27', 7, rng, ACCOUNTS),
             'calibration': synthetic_rows('calibration', '2017-12-04', 14, rng, ACCOUNTS)}
    directory = root / 'data' / name
    directory.mkdir(parents=True)
    hashes, nine = {}, {}
    for part, rows in parts.items():
        data = b''.join(access.canonical(row) + b'\n' for row in rows)
        (directory / f'rows-{part}.jsonl').write_bytes(data)
        hashes[part] = hashlib.sha256(data).hexdigest()
        nine[part] = sum(row['nine_feature_eligible'] for row in rows)
    selected = ACCOUNTS + list(extra_cohort)
    cohort = access.canonical({'profile': features.PROFILE, 'selected': selected}) + b'\n'
    (directory / 'cohort.json').write_bytes(cohort)
    receipt = root / 'data' / f'{name}-reader-receipt.json'
    receipt.write_text(json.dumps({'receipt_sha256': 'r' * 64, 'foundation': {'receipt_sha256': 'f' * 64}}))
    observed = {'selected_accounts': len(selected), 'fit_nine_feature_rows': nine['fit'],
                'validation_nine_feature_rows': nine['validation'], 'calibration_nine_feature_rows': nine['calibration']}
    manifest = {'schema': 'w33_pretest_export_v1', 'profile': features.PROFILE, 'features': features.FEATURES,
                'reserved_access': False, 'feature_contract_sha256': features.contract_sha256(),
                'engineering_gates_pass': gates_pass, 'policy': access.POLICY,
                'cohort_file_sha256': hashlib.sha256(cohort).hexdigest(), 'partition_rows_sha256': hashes,
                'engineering_gates': {key: {'observed': value} for key, value in observed.items()},
                'coverage': {part: {'nine_feature_eligible': nine[part]} for part in parts},
                'source_sha256': reader.source_hashes(exporter.EXPORT_SOURCES),
                'binding': {'reader_receipt_path': str(receipt), 'reader_receipt_sha256': 'r' * 64,
                            'foundation_receipt_sha256': 'f' * 64, 'archive_sha256': access.ARCHIVE_SHA,
                            'availability_file_sha256': 'a' * 64}}
    if mutate:
        mutate(manifest)
    (directory / 'manifest.json').write_bytes(access.canonical(manifest) + b'\n')
    return directory


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(train, 'ROOT', tmp_path)
    monkeypatch.setitem(train.METHOD, 'epochs_max', 4)  # speed only; bound in and checked by the preregistration
    monkeypatch.setitem(train.METHOD, 'engineering_gates', SMALL_GATES)  # explicit fixture minima, also bound
    return tmp_path, write_export(tmp_path)


def test_transform_logs_only_the_four_count_columns():
    row = {'features': dict(zip(features.FEATURES, [9, 3, 2, 0.25, 1, -0.5, 0.5, 0.2, 0.7]))}
    values = train.matrix([row], features.FEATURES)[0]
    assert values.tolist() == [math.log1p(9), math.log1p(3), math.log1p(2), 0.25, math.log1p(1), -0.5, 0.5, 0.2, 0.7]
    assert train.matrix([row], features.FEATURES[:5]).shape == (1, 5)


def test_scaler_uses_population_sd_and_unit_scale_for_constant_columns():
    raw = np.array([[1.0, 5.0], [3.0, 5.0]])
    scaler = train.Scaler.fit(raw)
    assert scaler.mean == [2.0, 5.0] and scaler.scale == [1.0, 1.0]
    assert train.Scaler.fit(np.array([[0.0], [4.0]])).scale == [2.0]  # ddof=0
    assert train.Scaler.fit(raw).transform(raw).dtype == np.float32


def eligible_row(account, day, **changes):
    values = dict(zip(features.FEATURES, [3, 2, 1, 0.5, 0, 0.1, 0.5, 0.2, 0.3]))
    values.update(changes)
    return {'account': account, 'day': day, 'status': 'eligible', 'prior_usable_days': 5, 'features': values,
            'five_feature_eligible': True, 'nine_feature_eligible': values['new_resource_share'] is not None}


def test_nine_feature_rows_are_filtered_and_canonically_ordered():
    rows = [eligible_row('b', '2017-09-05'), eligible_row('a', '2017-09-05'),
            eligible_row('c', '2017-09-04', new_resource_share=None, unique_resources=0)]
    assert [(r['day'], r['account']) for r in train.nine_rows(rows)] == [('2017-09-05', 'a'), ('2017-09-05', 'b')]


@pytest.mark.parametrize('row', [
    eligible_row('a', '2017-09-04', volume_log_ratio=float('inf')),
    eligible_row('a', '2017-09-04', hour_profile_js_distance=1.5),
    eligible_row('a', '2017-09-04', unique_actions=0),
    eligible_row('a', '2017-09-04', new_action_count=3),
    eligible_row('a', '2017-09-04', event_count=2.0),
    {**eligible_row('a', '2017-09-04'), 'nine_feature_eligible': False},
    {**eligible_row('a', '2017-09-04'), 'prior_usable_days': 4},
    {**eligible_row('a', '2017-09-04'), 'status': 'cold_start'},
])
def test_row_invariants_fail_closed(row):
    with pytest.raises(ValueError):
        train.check_row(row)


def test_early_stopping_keeps_earliest_best_and_ignores_ties():
    stop = train.EarlyStop(2)
    assert stop.update(1, 0.5) and not stop.update(2, 0.5) and not stop.update(3, 0.6)
    assert stop.stop and stop.best_epoch == 1
    with pytest.raises(ValueError):
        train.EarlyStop(2).update(1, float('nan'))


def test_c_norm_references_cover_every_cohort_account():
    accounts = ['a'] * 6 + ['b'] * 4 + ['c'] * 5 + ['d'] * 5
    scores = [1, 2, 3, 4, 5, 6] + [1] * 4 + [0.0] * 5 + [1, 1, 1, 1, float('nan')]
    table = train.c_norm_references(accounts, scores, ['a', 'b', 'c', 'd', 'zero'])
    assert table['a']['denominator'] == 3.5 and table['a']['floor_used'] is False
    assert table['b']['status'] == 'insufficient_reference_days'
    assert table['c']['denominator'] == 1e-8 and table['c']['floor_used'] is True
    assert table['d']['status'] == 'invalid_reference_error'
    assert table['zero'] == {'status': 'no_eligible_fit_rows', 'reference_days': 0}
    assert len(table) == 5
    with pytest.raises(ValueError, match='cohort'):
        train.c_norm_references(['outsider'], [1.0], ['a'])


def test_threshold_higher_quantile_strict_alerts_and_minimum_rows():
    assert train.threshold(list(range(99)))['status'] == 'insufficient_calibration_rows'
    result = train.threshold([float(v) for v in range(100)])
    assert result['0.01']['threshold'] == 99.0 and result['0.01']['calibration_alerts'] == 0
    assert result['0.05']['threshold'] == 95.0 and result['0.05']['calibration_alerts'] == 4
    tied = train.threshold([1.0] * 100)
    assert tied['0.01']['ties_at_threshold'] == 100 and tied['0.01']['calibration_alerts'] == 0


def test_preregistration_binds_export_and_refuses_changes(workspace):
    root, export_dir = workspace
    record = train.preregister(export_dir, root / 'data/prereg.json')
    assert record['export']['recounted_gates'] == {'selected_accounts': 8, 'fit_rows': 214,
                                                   'validation_rows': 56, 'calibration_rows': 112}
    assert record['export']['producer_source_sha256'] == reader.source_hashes(exporter.EXPORT_SOURCES)
    assert record['method']['engineering_gates'] == SMALL_GATES
    assert train.verify_preregistration(root / 'data/prereg.json')[0] == record
    with pytest.raises(ValueError):
        train.preregister(export_dir, root / 'data/prereg.json')
    with pytest.raises(ValueError):
        train.preregister(export_dir, root / 'outside.json')
    (export_dir / 'rows-fit.jsonl').write_bytes((export_dir / 'rows-fit.jsonl').read_bytes() + b'\n')
    with pytest.raises(ValueError, match='fit rows'):
        train.verify_preregistration(root / 'data/prereg.json')


def test_production_gates_are_recounted_and_refuse_small_exports(tmp_path, monkeypatch):
    monkeypatch.setattr(train, 'ROOT', tmp_path)
    assert train.METHOD['engineering_gates'] == {'selected_accounts': 10, 'fit_rows': 1000,
                                                 'validation_rows': 100, 'calibration_rows': 100}
    with pytest.raises(ValueError, match='gate not met'):  # manifest says pass; the recount decides
        train.load_export(write_export(tmp_path, 'small'))


@pytest.mark.parametrize('mutate,message', [
    (lambda m: m['engineering_gates']['fit_nine_feature_rows'].update(observed=9999), 'claim disagrees'),
    (lambda m: m['coverage']['validation'].update(nine_feature_eligible=1), 'coverage disagrees'),
    (lambda m: m.update(engineering_gates_pass=False), 'gate-passing'),
])
def test_manifest_gate_claims_must_match_recount(workspace, mutate, message):
    root, _ = workspace
    with pytest.raises(ValueError, match=message):
        train.load_export(write_export(root, 'claims', mutate=mutate))


@pytest.mark.parametrize('mutate', [
    lambda m: m['source_sha256'].update({'scripts/clue_v2_features.py': '0' * 64}),   # stale producer
    lambda m: m['source_sha256'].pop('scripts/export_clue_v2.py'),                    # missing producer
    lambda m: m['binding'].update(reader_receipt_sha256='x' * 64),                     # wrong reader receipt
    lambda m: m.pop('binding'),
])
def test_stale_or_missing_producer_binding_stops_before_fitting(workspace, monkeypatch, mutate):
    root, _ = workspace
    monkeypatch.setattr(train, 'fit_one', lambda *args: pytest.fail('Fitting reached with bad provenance'))
    export_dir = write_export(root, 'provenance', mutate=mutate)  # row files and their checksums stay valid
    with pytest.raises(ValueError):
        train.preregister(export_dir, root / 'data/prereg-provenance.json')


def test_training_order_parity_outputs_and_cohort_coverage(workspace):
    root, _ = workspace
    export_dir = write_export(root, 'with-zero', extra_cohort=['acct-no-fit-rows'])
    train.preregister(export_dir, root / 'data/prereg.json')
    summary = train.train(root / 'data/prereg.json', root / 'data/run')
    assert summary['operation_order'] == ['fit_and_freeze_B', 'fit_and_freeze_C',
                                          'freeze_c_norm_references_before_calibration', 'calibrate_thresholds']
    # 30 days x 8 accounts = 240 fit rows, minus 26 resource-free days excluded from both B and C.
    assert summary['detectors']['B']['fit_rows'] == summary['detectors']['C']['fit_rows'] == 214
    c_norm = summary['c_norm']
    assert c_norm['selected_accounts'] == 9 == c_norm['available_accounts'] + c_norm['unavailable_accounts']
    assert c_norm['unavailable_by_reason'] == {'no_eligible_fit_rows': 1}
    references = json.loads((root / 'data/run/c_norm_references.json').read_bytes())
    assert references['acct-no-fit-rows'] == {'status': 'no_eligible_fit_rows', 'reference_days': 0}
    assert summary['activated'] is False and summary['reserved_access'] is False
    thresholds = json.loads((root / 'data/run/thresholds.json').read_bytes())
    assert set(thresholds) == {'B', 'C', 'C_norm', 'BL'} and all(t['status'] == 'available' for t in thresholds.values())
    assert json.loads((root / 'data/run/B/scaler.json').read_bytes())['columns'] == features.FEATURES[:5]


def test_one_real_fit_per_experiment_whatever_the_receipt_path(workspace, monkeypatch):
    root, export_dir = workspace
    train.preregister(export_dir, root / 'data/prereg-one.json')
    train.preregister(export_dir, root / 'data/prereg-two.json')
    train.train(root / 'data/prereg-one.json', root / 'data/run-one')
    monkeypatch.setattr(train, 'fit_one', lambda *args: pytest.fail('Second experiment fit started'))
    with pytest.raises(FileExistsError):
        train.train(root / 'data/prereg-two.json', root / 'data/run-two')
    assert not (root / 'data/run-two').exists()


def test_training_is_deterministic_across_isolated_workspaces(tmp_path, monkeypatch):
    import torch
    monkeypatch.setitem(train.METHOD, 'epochs_max', 4)
    monkeypatch.setitem(train.METHOD, 'engineering_gates', SMALL_GATES)
    outputs = []
    for name in ('one', 'two'):
        root = tmp_path / name
        monkeypatch.setattr(train, 'ROOT', root)
        export_dir = write_export(root)
        train.preregister(export_dir, root / 'data/prereg.json')
        train.train(root / 'data/prereg.json', root / 'data/run')
        outputs.append(root / 'data/run')
    for detector in ('B', 'C'):
        first, second = (torch.load(o / detector / 'model.pt', weights_only=True) for o in outputs)
        assert all(torch.equal(first[key], second[key]) for key in first)
    assert (outputs[0] / 'thresholds.json').read_bytes() == (outputs[1] / 'thresholds.json').read_bytes()


def test_failed_attempt_stays_claimed_and_disclosed(workspace, monkeypatch):
    root, export_dir = workspace
    train.preregister(export_dir, root / 'data/prereg.json')
    train.preregister(export_dir, root / 'data/prereg-retry.json')
    monkeypatch.setattr(train, 'fit_one', lambda *args: (_ for _ in ()).throw(RuntimeError('engineering failure')))
    with pytest.raises(RuntimeError):
        train.train(root / 'data/prereg.json', root / 'data/run')
    claim = root / train.METHOD['experiment_claim']
    assert claim.exists() and Path(str(claim) + '.failed.json').exists()
    with pytest.raises(FileExistsError):  # a fresh receipt does not reopen the experiment
        train.train(root / 'data/prereg-retry.json', root / 'data/run-2')


def test_preregister_cli_reports_current_summary_after_saving(workspace, monkeypatch, capsys):
    import sys
    root, export_dir = workspace
    receipt = root / 'data/cli-prereg.json'
    monkeypatch.setattr(sys, 'argv', ['train_clue_v2.py', 'preregister', '--export', str(export_dir), '--out', str(receipt)])
    assert train.main() == 0
    printed = json.loads(capsys.readouterr().out)
    saved = json.loads(receipt.read_bytes())
    assert printed['recounted_gates'] == saved['export']['recounted_gates']
    assert printed['receipt_sha256'] == saved['receipt_sha256']
    assert not (root / train.METHOD['experiment_claim']).exists()

