import json

import pytest

from backend.clue_replay import read_bundle
from scripts import train_clue_ae as training
from scripts import build_clue_replay as replay
from scripts.tests.test_clue_training import dataset


def test_two_step_export_keeps_high_and_derives_medium_from_calibration(dataset,tmp_path,monkeypatch):
    pytest.importorskip('torch')
    source,data,cuts=dataset
    bundle=tmp_path/'candidate';training.train(source,bundle,cuts,epochs=2)
    normal=training.evaluate(source,bundle,bundle/'normal_holdout_report.json')
    calls=[]; original=replay.residuals
    def checked(rows,*args):
        calls.append([r['date'] for r in rows])
        return original(rows,*args)
    monkeypatch.setattr(replay,'residuals',checked)
    policy_path=tmp_path/'policy.json'
    policy=replay.freeze_policy(source,bundle,policy_path)
    assert len(calls)==1 and all(cuts[2]<d<=cuts[3] for d in calls[0])
    assert policy['high_threshold']==normal['threshold_raw_mse']
    # Policy artifact must already exist before any held-out scoring/export.
    report=replay.export_replay(source,bundle,policy_path,tmp_path/'replay')
    actual,rows=read_bundle(tmp_path/'replay')
    assert actual==policy
    assert {r['split'] for r in rows}=={'heldout','calibration'}
    assert sum(r['review_priority']=='High' for r in rows if r['split']=='heldout')==normal['normal_alerts']
    assert report['live_activation'] is False
    assert all(r['account'].startswith('cohort-') and set(r['features'])==set(training.FEATURES) for r in rows)
    with pytest.raises(ValueError):replay.freeze_policy(source,bundle,policy_path)
    with pytest.raises(ValueError):replay.export_replay(source,bundle,policy_path,tmp_path/'replay')
    policy['medium_threshold']+=.001;policy_path.write_text(json.dumps(policy))
    with pytest.raises(ValueError,match='Medium threshold'):
        replay.export_replay(source,bundle,policy_path,tmp_path/'changed-medium')


def test_corrupted_model_rejected_before_deserialisation(dataset,tmp_path):
    pytest.importorskip('torch')
    source,_,cuts=dataset
    bundle=tmp_path/'candidate';training.train(source,bundle,cuts,epochs=1)
    manifest=json.loads((bundle/'clue_model_manifest.json').read_text())
    (bundle/manifest['model_path']).write_bytes(b'not a model')
    with pytest.raises(ValueError,match='Artifact binding'):
        replay.freeze_policy(source,bundle,tmp_path/'policy.json')
    assert not (tmp_path/'policy.json').exists()
