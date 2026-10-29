"""Synthetic protocol-window fixtures; no real pilot model is fitted here."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from scripts import live_daily_method as method, train_live_daily as trainer, export_live_daily as exporter
from scripts.tests.test_live_daily_export import export_study
from scripts.tests.test_live_history_readiness import study, ACCOUNT, STACK, NOW


@pytest.fixture
def dataset(export_study, tmp_path):
    path = tmp_path / 'export'
    exporter.export(*export_study, ACCOUNT, STACK, path, NOW)
    return path


def edit_data(path, edit):
    data = json.loads((path / 'dataset.json').read_text())
    edit(data)
    raw = exporter.canonical(data) + b'\n'
    (path / 'dataset.json').write_bytes(raw)
    manifest = json.loads((path / 'manifest.json').read_text())
    import hashlib
    manifest['dataset_sha256'] = hashlib.sha256(raw).hexdigest()
    (path / 'manifest.json').write_bytes(exporter.canonical(manifest))


def simple_fit():
    return [{'persona': role, 'features': {'event_count': 3}, 'resource_counts': {f'p{i:02d}': 3}}
            for i, role in enumerate(method.ROLES, 1) for _ in range(7)]


def test_personal_peer_resource_context_distinguishes_accounts_not_intent():
    ref = method.fit_references(simple_fit())
    normal = simple_fit()[0]
    switched = {**normal, 'resource_counts': {'p06': 3}}
    assert method.context_scores(ref, switched)['personal'] > method.context_scores(ref, normal)['personal']
    assert method.context_scores(ref, switched) == method.context_scores(ref, {**switched, 'approved': True})
    assert method.context_scores(ref, switched)['volume'] == method.context_scores(ref, normal)['volume']
    assert ref['personal']['persona-01']['p01'] > ref['personal']['persona-02']['p01']
    assert all(p > 0 for p in ref['personal']['persona-01'].values())
    with pytest.raises(ValueError): method.excess(ref['population'], {'outside-domain': 1})


def test_sparse_threshold_uses_strict_max_and_ties_never_randomised():
    result = method.empirical_threshold([float(i) for i in range(18)])
    assert result['threshold'] == 17 and result['normal_alerts'] == 0
    assert result['tail_resolution'] == 1 / 18
    ties = method.empirical_threshold([1.] * 18)
    assert ties['gate'] == 'no_go_constant_calibration' and ties['normal_alerts'] == 0
    assert method.empirical_threshold(list(range(20)))['normal_alerts'] == 1


def test_union_budget_reported_not_retuned():
    rows = [{'persona': method.ROLES[i % 6], 'personal': float(i), 'population': float(i),
             'volume': float(i), 'ae': float(20 - i)} for i in range(20)]
    report = method.calibrate(rows, method.fit_references(simple_fit()))
    assert report['components']['personal']['normal_alerts'] == 1
    assert report['components']['ae']['normal_alerts'] == 1
    assert report['combined_normal_alerts'] == 2 and not report['combined_budget_pass']
    assert report['components']['personal']['threshold'] == 18


def test_prepare_checks_all_six_roles_and_ip_exclusions(dataset):
    _, parts, excluded, gates = trainer.prepare(dataset, NOW)
    assert [len(parts[p]) for p in trainer.readiness.WINDOWS] == [42, 12, 18]
    assert not excluded and gates['eligible_roles'] == 6
    def remove_ip(data):
        for row in data['rows']:
            if row['persona'] == 'persona-01' and row['partition'] == 'validation':
                n = row['features']['event_count']
                row['ip_observability'] = {'valid_events': 0, 'missing_events': n, 'invalid_events': 0}
                row['features']['unique_valid_ips'] = 0
    edit_data(dataset, remove_ip)
    with pytest.raises(trainer.Refusal, match='after IP exclusions'):
        trainer.prepare(dataset, NOW)


@pytest.mark.parametrize('fault', ['hash', 'context', 'partition', 'open', 'coverage', 'duplicate'])
def test_bad_input_refused_before_torch(dataset, fault, monkeypatch):
    monkeypatch.setattr(trainer, 'fit_ae', lambda _: pytest.fail('Fitting called before validation'))
    if fault == 'hash':
        (dataset / 'dataset.json').write_bytes(b'{}')
    else:
        def edit(data):
            row = data['rows'][0]
            if fault == 'context': row['resource_counts'] = {'p01': 999}
            elif fault == 'partition': row['partition'] = 'normal_calibration'
            elif fault == 'open': row['complete_day'] = False
            elif fault == 'coverage': row['coverage']['verified_fraction_of_planned'] = .3
            else: data['rows'].append(deepcopy(row))
        edit_data(dataset, edit)
    with pytest.raises(trainer.Refusal): trainer.prepare(dataset, NOW)


def test_fit_only_scaler_refs_and_checkpoint_calibration_independence(dataset):
    torch = pytest.importorskip('torch')
    import numpy as np
    _, parts, _, _ = trainer.prepare(dataset, NOW)
    model, scaler, val, epoch = trainer.fit_ae(parts)
    expected = np.log1p([[r['features'][f] for f in trainer.FEATURES] for r in parts['fit']])
    np.testing.assert_allclose(scaler['mean'], expected.mean(axis=0))
    modified = deepcopy(parts)
    for row in modified['normal_calibration']:
        row['features']['event_count'] += 10000
        row['resource_counts'] = {'confidential': 3}
    second, scale2, val2, epoch2 = trainer.fit_ae(modified)
    assert scaler == scale2 and val == val2 and epoch == epoch2
    assert all(torch.equal(v, second.state_dict()[k]) for k, v in model.state_dict().items())
    assert method.fit_references(parts['fit']) == method.fit_references(modified['fit'])
    assert sum(p.numel() for p in model.parameters()) == 98


def test_synthetic_training_reload_tag_and_tamper_refusal(dataset, tmp_path):
    pytest.importorskip('torch')
    output = tmp_path / 'synthetic-bundle'
    manifest = trainer.train(dataset, output, NOW, synthetic=True)
    assert manifest['run_kind'] == 'synthetic_contract_test'
    assert manifest['reloaded_score_parity'] and manifest['activated'] is False
    assert manifest['evaluation_status'] == 'normal_calibration_only'
    scope = manifest['scope_sha256']
    with pytest.raises(trainer.Refusal, match='Synthetic'):
        trainer.load_bundle(output, expected_scope_sha256=scope)
    with pytest.raises(trainer.Refusal, match='scope differs'):
        trainer.load_bundle(output, expected_scope_sha256='0' * 64, allow_synthetic=True)
    model, scaler, refs, _ = trainer.load_bundle(output, expected_scope_sha256=scope, allow_synthetic=True)
    _, parts, _, _ = trainer.prepare(dataset, NOW)
    scores = trainer.score_rows(model, scaler, refs, parts['normal_calibration'])
    assert scores == json.loads((output / 'normal_report.json').read_text())['normal_calibration']
    (output / 'scaler.json').write_bytes(b'{}')
    with pytest.raises(trainer.Refusal, match='artifact changed'):
        trainer.load_bundle(output, expected_scope_sha256=scope, allow_synthetic=True)
    with pytest.raises(trainer.Refusal, match='fresh'):
        trainer.train(dataset, output, NOW, synthetic=True)


def test_empty_real_period_refuses_without_output(dataset, tmp_path):
    edit_data(dataset, lambda data: data.update(rows=[]))
    with pytest.raises(trainer.Refusal): trainer.prepare(dataset, datetime(2026, 10, 29, tzinfo=timezone.utc))
    assert not (tmp_path / 'untrained').exists()
