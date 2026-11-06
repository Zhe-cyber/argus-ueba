"""Synthetic artifacts and temporary pointers; no real inference or scheduled tasks."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import refresh_live_diagnostics as worker
from backend.tests.test_diagnostic_receipts import fixture, write_bundle, NOW
from workspace_next import diagnostic_receipts as consumer


@pytest.fixture
def setup(tmp_path, monkeypatch):
    row, provenance = fixture()
    actual_root = worker.ROOT
    pins = {**provenance['source_sha256'], **{name: hashlib.sha256((actual_root / name).read_bytes()).hexdigest()
        for name in ('scripts/refresh_live_diagnostics.py', 'workspace_next/diagnostic_receipts.py')}}
    monkeypatch.setattr(worker, 'ROOT', tmp_path)
    config = {'schema': 'argus_diagnostic_refresh_job_v1', 'end_my': worker.END.isoformat(),
        'expected_provenance': provenance, 'source_sha256': pins,
        'output_root': str(tmp_path / 'data/processed/clue-ae-v2/daily-live-receipts'),
        'state_dir': str(tmp_path / 'data/live/diagnostic-refresh-v1'),
        'pointer': str(tmp_path / 'data/live/workspace-case-preview-20261030-v1/diagnostic-receipts-config.json')}
    for key in ('output_root', 'state_dir'):
        Path(config[key]).mkdir(parents=True)
    Path(config['pointer']).parent.mkdir(parents=True)
    for key in ('pilot_config', 'prereg', 'database', 'training'):
        value = tmp_path / key
        value.write_text('{}')
        config[key] = str(value)
    path = tmp_path / 'config.json'
    path.write_bytes(consumer.canonical(config))
    def generate(cfg, output, now):
        write_bundle(output, [deepcopy(row)], provenance)
    monkeypatch.setattr(worker, 'generate', generate)
    return path, config


def test_refresh_verifies_before_publish_and_same_day_does_not_repeat(setup, monkeypatch):
    path, config = setup
    assert worker.refresh(path, check=True, now=NOW)['status'] == 'configuration_verified'
    result = worker.refresh(path, now=NOW)
    assert result['status'] == 'refreshed' and result['provider_calls'] == 0
    pointer = json.loads(Path(config['pointer']).read_bytes())
    consumer.load_bundle(**pointer, now=NOW)
    monkeypatch.setattr(worker, 'generate', lambda *a: pytest.fail('Repeated a successful daily job'))
    assert worker.refresh(path, now=NOW)['status'] == 'already_refreshed_today'
    assert not (Path(config['state_dir']) / 'refresh.lock').exists()


def test_generation_failure_preserves_prior_pointer(setup, monkeypatch):
    path, config = setup
    pointer = Path(config['pointer'])
    pointer.write_bytes(b'{"old":"retained"}')
    def broken(*a):
        raise RuntimeError('synthetic generation failure')
    monkeypatch.setattr(worker, 'generate', broken)
    with pytest.raises(RuntimeError):
        worker.refresh(path, now=NOW)
    assert pointer.read_bytes() == b'{"old":"retained"}'
    attempt = json.loads((Path(config['state_dir']) / 'last_attempt.json').read_bytes())
    assert attempt['pointer_changed'] is False


def test_wrong_model_binding_is_not_published(setup, monkeypatch):
    path, config = setup
    original = worker.generate
    def corrupt(cfg, output, now):
        original(cfg, output, now)
        manifest = json.loads((output / 'manifest.json').read_bytes())
        manifest['provenance']['detectors']['B']['model_sha256'] = 'f' * 64
        (output / 'manifest.json').write_bytes(consumer.canonical(manifest))
    monkeypatch.setattr(worker, 'generate', corrupt)
    with pytest.raises(consumer.ReceiptError, match='provenance_mismatch'):
        worker.refresh(path, now=NOW)
    assert not Path(config['pointer']).exists()


def test_expiry_and_existing_lock_never_generate(setup, monkeypatch):
    path, config = setup
    monkeypatch.setattr(worker, 'generate', lambda *a: pytest.fail('Unexpected generation'))
    assert worker.refresh(path, now=worker.END)['status'] == 'refresh_period_expired'
    lock = Path(config['state_dir']) / 'refresh.lock'
    lock.write_text('requires operator review')
    assert worker.refresh(path, now=NOW)['status'] == 'refresh_locked_requires_review'
    assert lock.exists()


def test_source_drift_refuses_before_generation(setup):
    path, config = setup
    config['source_sha256']['scripts/refresh_live_diagnostics.py'] = '0' * 64
    path.write_bytes(consumer.canonical(config))
    with pytest.raises(consumer.ReceiptError, match='source_binding_mismatch'):
        worker.refresh(path, now=NOW)
