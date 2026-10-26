"""Readiness explains missing risk without running model inference or leaking paths."""
import json

import pytest

from backend import ae_scorer as module, config


@pytest.mark.parametrize(('files', 'tried', 'ready', 'expected'), [
    (False, False, False, 'missing_artifacts'),
    (True, False, False, 'not_loaded'),
    (True, True, False, 'load_failed'),
    (True, True, True, 'ready'),
    (False, True, True, 'ready'),  # Already loaded in memory, files later removed.
])
def test_readiness_does_not_load_or_expose_local_paths(monkeypatch, tmp_path, files, tried, ready, expected):
    model_path = tmp_path / 'private-model.pt'
    scaler_path = tmp_path / 'private-scaler.pkl'
    if files:
        model_path.touch()
        scaler_path.touch()
    monkeypatch.setattr(module, '_CLOUD_AE_PATH', model_path)
    monkeypatch.setattr(module, '_CLOUD_SCALER_PATH', scaler_path)
    scorer = module._CloudAEScorer()
    scorer._tried, scorer._ready = tried, ready

    def forbidden_load():
        raise AssertionError('A status request attempted inference/model loading')

    monkeypatch.setattr(scorer, '_load', forbidden_load)
    result = scorer.readiness()
    assert result['status'] == expected
    assert result['model_ready'] is ready
    assert str(tmp_path) not in json.dumps(result)
    assert 'private-model' not in json.dumps(result)


def test_prototype_origin_is_explicit_not_local_accuracy_claim(monkeypatch, tmp_path):
    model_path, scaler_path = tmp_path / 'model.pt', tmp_path / 'scaler.pkl'
    model_path.touch()
    scaler_path.touch()
    monkeypatch.setattr(module, '_CLOUD_AE_PATH', model_path)
    monkeypatch.setattr(module, '_CLOUD_SCALER_PATH', scaler_path)
    monkeypatch.setattr(config, 'CLOUD_MODEL_PROFILE', 'flaws-cloud-prototype')
    scorer = module._CloudAEScorer()
    scorer._ready = True
    status = scorer.readiness()
    assert status['model_origin'] == 'flaws.cloud AWS benchmark'
    assert status['provisional'] is True
    assert 'not been validated' in status['message']
