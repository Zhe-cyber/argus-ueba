"""Offline fixtures only; no benchmark or live-cloud accuracy is measured here."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from backend.cloud_feature_extractor import CLOUD_FEATURES
from scripts import audit_simulation as audit, export_cloud_baseline as exporter
from scripts import run_simulation as runner, train_verified_cloud as trainer
from scripts.tests.test_simulation import cloud, ACCOUNT, STACK


def test_colab_generator_pins_revision_and_has_valid_python_cells():
    import ast
    from scripts.build_verified_cloud_notebook import build
    notebook = build('a' * 40)
    for cell in notebook['cells']:
        if cell['cell_type'] == 'code': ast.parse(''.join(cell['source']))
    source = json.dumps(notebook)
    assert 'RUN_TRAINING = False' in source and '--check-only' in source
    assert 'a' * 40 in source
    with pytest.raises(ValueError): build('main')


@pytest.fixture
def dataset(tmp_path):
    rows = []
    for d in range(1, 9):
        for user in range(6):
            row = {'user': f'fixture-{user}', 'date': f'2020-01-{d:02d}', 'complete_day': True}
            row.update({f: float((user + i + d) % 7 + 1) for i, f in enumerate(CLOUD_FEATURES)})
            rows.append(row)
    document = {'schema_version': 1, 'dataset_kind': 'audited_aws_lab_normal', 'features': CLOUD_FEATURES,
                'rows': rows, 'provenance': {'feature_code_sha256': trainer.sha(trainer.ROOT / 'backend/cloud_feature_extractor.py'),
                                           'runs': [{'manifest_sha256': '0' * 64, 'matched_actions': 19}]}}
    path = tmp_path / 'fixture.json'
    path.write_text(json.dumps(document))
    return path, document


def prepare(path):
    return trainer.prepare(path, '2020-01-05', '2020-01-06', '2020-01-07')


def test_partitions_keep_whole_days_and_exclude_later_activity(dataset):
    path, _ = dataset
    _, parts = prepare(path)
    assert [len(p) for p in parts] == [30, 6, 6]
    assert max(r['date'] for r in parts[0]) < min(r['date'] for r in parts[1])
    assert max(r['date'] for r in parts[1]) < min(r['date'] for r in parts[2])


@pytest.mark.parametrize('fault', ['incomplete', 'nonfinite', 'negative', 'duplicate', 'contract', 'code', 'small', 'empty', 'identity'])
def test_training_refuses_bad_data_before_loading_torch(dataset, fault):
    path, document = dataset
    row = document['rows'][0]
    if fault == 'incomplete': row['complete_day'] = False
    elif fault == 'nonfinite': row[CLOUD_FEATURES[0]] = float('nan')
    elif fault == 'negative': row[CLOUD_FEATURES[0]] = -1
    elif fault == 'duplicate': document['rows'].append(deepcopy(row))
    elif fault == 'contract': document['features'] = list(reversed(CLOUD_FEATURES))
    elif fault == 'code': document['provenance']['feature_code_sha256'] = '0' * 64
    elif fault == 'small': document['rows'] = document['rows'][:6]
    elif fault == 'empty': row['event_count'] = 0
    elif fault == 'identity': row['user'] = ''
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError): prepare(path)


def test_cutoffs_must_increase(dataset):
    with pytest.raises(ValueError):
        trainer.prepare(dataset[0], '2020-01-05', '2020-01-05', '2020-01-07')


def test_normal_calibration_refuses_degenerate_bounds():
    pytest.importorskip('numpy')
    with pytest.raises(ValueError): trainer.calibrate([0, 0, 0])
    with pytest.raises(ValueError): trainer.calibrate([float('nan')])
    low, high = trainer.calibrate([1, 2, 3, 4])
    assert 0 < low < high


def test_train_only_scaling_and_saved_inference_match(dataset, tmp_path, monkeypatch):
    torch = pytest.importorskip('torch')
    import joblib
    import numpy as np
    path, document = dataset
    # Later normal calibration and held-out rows must not influence scaler fitting.
    for row in document['rows']:
        if row['date'] > '2020-01-05': row['event_count'] += 1000
    path.write_text(json.dumps(document))
    output = tmp_path / 'candidate'
    result = trainer.train(path, output, '2020-01-05', '2020-01-06', '2020-01-07', epochs=2)
    scaler = joblib.load(output / 'cloud_scaler_v1.pkl')
    _, parts = prepare(path)
    raw = np.array([[r[f] for f in CLOUD_FEATURES] for r in parts[0]])
    np.testing.assert_allclose(scaler.mean_, raw.mean(axis=0))
    checkpoint = torch.load(output / 'cloud_ae_v1.pt', map_location='cpu', weights_only=True)
    model = trainer._build_cloud_ae(12)
    model.load_state_dict(checkpoint['state_dict'])
    model.eval()
    calibration_raw = np.asarray([[r[f] for f in CLOUD_FEATURES] for r in parts[2]], dtype=np.float32)
    calibration = torch.tensor(scaler.transform(calibration_raw).astype('float32'))
    with torch.no_grad(): errors = ((model(calibration) - calibration) ** 2).mean(dim=1).numpy()
    assert trainer.calibrate(errors) == (checkpoint['ae_min'], checkpoint['ae_max'])
    assert result['evaluation_status'] == 'not_evaluated' and result['provisional'] is True
    # A second deterministic fit uses the same tensor values and bounds.
    for row in document['rows']:
        if row['date'] > '2020-01-07': row['event_count'] += 999999
    path.write_text(json.dumps(document))
    other = trainer.train(path, tmp_path / 'repeat', '2020-01-05', '2020-01-06', '2020-01-07', epochs=2)
    assert other['ae_min'] == result['ae_min'] and other['ae_max'] == result['ae_max']
    other_checkpoint = torch.load(tmp_path / 'repeat/cloud_ae_v1.pt', weights_only=True)
    for key, value in checkpoint['state_dict'].items(): assert torch.equal(value, other_checkpoint['state_dict'][key])
    # Operator installation of a reviewed bundle is a separate explicit step.
    installed = tmp_path / 'installed/ml/models'
    shutil.copytree(output, installed)
    monkeypatch.setattr(runner, 'ROOT', tmp_path / 'installed')
    runner.check_frozen_model(installed / 'frozen_model_manifest.json')
    (installed / 'cloud_ae_v1.pt').write_bytes(b'changed')
    with pytest.raises(ValueError): runner.check_frozen_model(installed / 'frozen_model_manifest.json')
    with pytest.raises(ValueError): trainer.train(path, output, '2020-01-05', '2020-01-06', '2020-01-07', epochs=2)


def test_export_selects_native_audited_actions_and_excludes_root(cloud, tmp_path, monkeypatch):
    result = runner.execute(runner.make_plan(ACCOUNT, STACK), 'fixture', 'argus-ueba-live-trail')
    folder = tmp_path / 'data/live/experiments/run'
    folder.mkdir(parents=True)
    manifest = folder / 'manifest.json'
    manifest.write_text(json.dumps(result))
    state = tmp_path / 'data/live/connected'
    state.mkdir()
    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    monkeypatch.setattr(exporter, 'ROOT', tmp_path)
    (tmp_path / 'backend').mkdir()
    shutil.copyfile(trainer.ROOT / 'backend/cloud_feature_extractor.py', tmp_path / 'backend/cloud_feature_extractor.py')
    with sqlite3.connect(state / 'events.db') as con:
        con.execute('CREATE TABLE events(event_id TEXT, source TEXT, source_account_id TEXT, user TEXT, action TEXT, resource TEXT, metadata TEXT, timestamp TEXT, ip_address TEXT)')
        for i, row in enumerate(result['results']):
            metadata = {'requestID': row['request_id'], 'userIdentity': {'principalId': result['principals'][row['persona']]}}
            con.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)', (f'native-{i}', 'aws_cloudtrail', ACCOUNT,
                        result['principals'][row['persona']], row['operation'], row['bucket'], json.dumps(metadata), '2020-01-01T12:00:00Z', '203.0.113.4'))
        con.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)', ('setup', 'aws_cloudtrail', ACCOUNT, 'root', 'CreateRole', 'private-setup', '{}', '2020-01-01T12:00:00Z', '203.0.113.5'))
    output = tmp_path / 'features.json'
    summary = exporter.export([manifest], state, output, now=datetime(2020, 1, 2, tzinfo=timezone.utc))
    assert summary['included_events'] == 19 and summary['excluded_events'] == 1
    assert summary['rows'] == 6 and summary['closed_day_rows'] == 6
    assert sum(r['event_count'] for r in json.loads(output.read_text())['rows']) == 19
    assert '203.0.113' not in output.read_text() and 'private-setup' not in output.read_text()
    assert result['principals']['persona-01'] not in output.read_text()
    with pytest.raises(ValueError): exporter.export([manifest, manifest], state, tmp_path / 'duplicate.json')
    with sqlite3.connect(state / 'events.db') as con: con.execute("DELETE FROM events WHERE event_id='native-0'")
    with pytest.raises(ValueError): exporter.export([manifest], state, tmp_path / 'missing.json')
