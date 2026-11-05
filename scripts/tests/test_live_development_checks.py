from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from types import SimpleNamespace

import pytest

from scripts import live_development_checks as development, rehearse_live_study as rehearsal
from scripts import export_live_daily as exporter, reserved_study as reserved
from scripts.tests.test_live_daily_export import export_study
from scripts.tests.test_live_history_readiness import study, ACCOUNT, STACK

PRECAL = datetime(2026, 11, 8, 1, tzinfo=reserved.MALAYSIA)


@pytest.fixture
def normal_data(export_study, tmp_path):
    path = tmp_path / 'normal-data'
    exporter.export(*export_study, ACCOUNT, STACK, path, PRECAL)
    return path


def edit(path, mutate):
    data = json.loads((path / 'dataset.json').read_text())
    mutate(data)
    (path / 'dataset.json').write_bytes(exporter.canonical(data) + b'\n')
    manifest = json.loads((path / 'manifest.json').read_text())
    manifest['dataset_sha256'] = development.trainer.sha(path / 'dataset.json')
    (path / 'manifest.json').write_bytes(exporter.canonical(manifest))


def test_exact_delta_and_no_calibration_claim(normal_data):
    before = [(normal_data / name).read_bytes() for name in ('dataset.json', 'manifest.json')]
    report = development.sensitivity(normal_data, PRECAL)
    assert report['status'] == 'development_prediction_computed'
    assert report['future_calibration_threshold'] == 'unknown'
    assert report['validation_account_days'] == 0
    assert report['fitting_events_per_role']['persona-01'] == 16
    assert report['fitting_events_per_role']['persona-02'] == 30
    assert len(report['reserved_slot_predictions']) == 4
    for slot in report['reserved_slot_predictions']:
        assert slot['basis'] == 'frozen_schedule_only_not_native_outcomes'
        if slot.get('status') == 'unavailable_no_planned_target_read':
            assert slot['predicted_delta'] is None
            continue
        assert slot['reference_basis'] == 'fitting_rows_only'
        assert math.isfinite(slot['predicted_delta'])
        assert 1 <= slot['planned_event_count'] <= 5
    samples = [s for s in report['samples'] if s['status'] == 'development_counterfactual']
    assert samples
    for sample in samples:
        assert math.isclose(sample['hypothetical_score'] - sample['normal_score'], sample['exact_delta'], abs_tol=1e-12)
        assert sample['ae_unique_resource_delta'] in (0, 1)
    assert before == [(normal_data / name).read_bytes() for name in ('dataset.json', 'manifest.json')]


def test_calibration_rows_and_late_diagnostics_refused(normal_data):
    with pytest.raises(ValueError, match='closes'):
        development.sensitivity(normal_data, development.DEADLINE)
    edit(normal_data, lambda d: d['rows'][0].update({'partition': 'normal_calibration'}))
    with pytest.raises(ValueError, match='forbidden'):
        development.sensitivity(normal_data, PRECAL)


def test_insufficient_fit_remains_pending_and_does_not_fit_model(normal_data, monkeypatch):
    edit(normal_data, lambda d: d.update({'rows': []}))
    monkeypatch.setattr(development.method, 'fit_references', lambda *_: pytest.fail('References fitted without history'))
    pending = development.sensitivity(normal_data, PRECAL)
    assert pending['status'] == 'pending_fitting_history'
    assert len(pending['reserved_slot_predictions']) == 4
    assert all(r['predicted_delta'] is None for r in pending['reserved_slot_predictions'])
    with pytest.raises(ValueError, match='insufficient'):
        rehearsal.rehearse(normal_data, normal_data.parent / 'not-created', PRECAL)
    assert not (normal_data.parent / 'not-created').exists()


def test_rehearsal_derivation_explicitly_reuses_fit_only(normal_data, tmp_path):
    data, _, rows, _ = development.read_development(normal_data, PRECAL)
    path = tmp_path / 'derived'
    rehearsal.derive_dataset(data, rows, path)
    derived = json.loads((path / 'dataset.json').read_text())
    assert derived['dataset_kind'] == 'synthetic_rehearsal_from_fitting'
    assert derived['provenance']['scope_sha256'] == reserved.digest([rehearsal.DUMMY_ACCOUNT, STACK])
    for row in derived['rows']:
        if row['partition'] != 'fit':
            assert row['synthetic_relabelled_copy'] is True
            assert row['rehearsal_origin_date'] <= '2026-11-07'
    _, parts, _, gates = development.trainer.prepare(path, rehearsal.SIMULATED_FREEZE)
    assert gates['eligible_roles'] == 6
    assert [len(parts[k]) for k in exporter.readiness.WINDOWS] == [42, 12, 18]


def test_full_rehearsal_is_synthetic_and_production_loader_still_refuses(normal_data, tmp_path, monkeypatch):
    pytest.importorskip('torch')
    # Only this test supplies a pretend clean source tree. The real harness uses actual Git checks.
    def git(args, **kwargs):
        assert args[0] == 'git'
        if 'status' in args: result = ''
        elif 'rev-parse' in args: result = 'a' * 40
        elif 'log' in args: result = str(int(datetime(2026, 10, 29, tzinfo=timezone.utc).timestamp()))
        else: pytest.fail('Unexpected subprocess')
        return SimpleNamespace(stdout=result, returncode=0)
    monkeypatch.setattr(reserved.subprocess, 'run', git)
    output = tmp_path / 'rehearsal'
    report = rehearsal.rehearse(normal_data, output, PRECAL)
    assert report['status'] == 'engineering_replay_completed'
    assert report['rehearsal_only'] and report['activated'] is False
    assert report['default_production_loader_rejected_bundle'] is True
    case = json.loads((output / 'SYNTHETIC-case-report.json').read_text())
    assert case['run_kind'] == 'synthetic_contract_test'
    assert len(case['rows']) == 12 and not case['live_release_approved']
    with pytest.raises(development.trainer.Refusal, match='Synthetic'):
        development.trainer.load_bundle(output / 'synthetic-bundle',
            expected_scope_sha256=reserved.digest([rehearsal.DUMMY_ACCOUNT, STACK]))


def test_normal_no_go_is_reported_without_forcing_release(normal_data, tmp_path, monkeypatch):
    pytest.importorskip('torch')
    original = development.method.calibrate
    def no_go(*args):
        result = original(*args)
        result['primary_gate'] = 'no_go_constant_or_blind_role'
        return result
    monkeypatch.setattr(development.method, 'calibrate', no_go)
    output = tmp_path / 'no-go-rehearsal'
    result = rehearsal.rehearse(normal_data, output, PRECAL)
    assert result['status'] == 'rehearsal_normal_gate_no_go'
    assert result['default_production_loader_rejected_bundle'] is True
    assert not (output / 'SIMULATED-release.json').exists()


def test_engineering_failure_is_not_hidden_as_normal_no_go(normal_data, tmp_path, monkeypatch):
    pytest.importorskip('torch')
    def mismatch(*args):
        raise ValueError('simulated artifact mismatch')
    monkeypatch.setattr(reserved, 'check_calibration', mismatch)
    with pytest.raises(ValueError, match='artifact mismatch'):
        rehearsal.rehearse(normal_data, tmp_path / 'bad-rehearsal', PRECAL)
