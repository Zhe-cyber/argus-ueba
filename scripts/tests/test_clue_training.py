"""Synthetic fixture fits only: no dataset or live-cloud performance measurements."""
import ast
from copy import deepcopy
import json

import pytest

from scripts import train_clue_ae as clue
from scripts.build_clue_training_notebook import build


@pytest.fixture
def dataset(tmp_path):
    rows=[]
    for day in range(1,13):
        for user in range(6):
            rows.append({'user':f'fixture-{user}','date':f'2020-01-{day:02d}',
                         'capture_boundary':day in (1,12),
                         'features':{f:float((day+user+i)%9+1) for i,f in enumerate(clue.FEATURES)},
                         'coverage':{'missing_required_paths':0,'unknown_action_events':0}})
    data={'schema_version':1,'profile':clue.PROFILE,'features':clue.FEATURES,'rows':rows,
          'provenance':{'feature_code_sha256':clue.sha(clue.ROOT/'scripts/clue_features.py'),
                        'last_capture_day':'2020-01-12'}}
    path=tmp_path/'fixture.json'; path.write_text(json.dumps(data))
    return path,data,['2020-01-02','2020-01-07','2020-01-08','2020-01-09','2020-01-11']


def test_notebook_pins_implementation_and_separates_train_and_evaluate():
    notebook=build('a'*40)
    for cell in notebook['cells']:
        if cell['cell_type']=='code': ast.parse(''.join(cell['source']))
    text=json.dumps(notebook)
    assert 'RUN_TRAINING=False' in text and 'RUN_NORMAL_EVALUATION=False' in text
    with pytest.raises(ValueError): build('master')


def test_population_is_fit_only_and_invalid_cutoffs_refused(dataset):
    path,data,cuts=dataset
    population,parts=clue.select(data,cuts)
    assert [len(p) for p in parts]==[6,30,6,6,12]
    late=deepcopy(data['rows'][-7]); late.update(user='late-only',date='2020-01-10',capture_boundary=False)
    data['rows'].append(late)
    assert clue.select(data,cuts)[0]==population
    with pytest.raises(ValueError): clue.select(data,cuts[:-1]+['2020-01-12'])
    with pytest.raises(ValueError): clue.select(data,[cuts[0]]*5)


@pytest.mark.parametrize('fault',['contract','duplicate','quality','nonfinite'])
def test_bad_training_data_refused(dataset,tmp_path,fault):
    path,data,cuts=dataset
    if fault=='contract': data['features']=list(reversed(clue.FEATURES))
    elif fault=='duplicate': data['rows'].append(deepcopy(data['rows'][0]))
    elif fault=='quality': data['rows'][13]['coverage']['missing_required_paths']=1
    else: data['rows'][13]['features']['event_count']=float('nan')
    path.write_text(json.dumps(data))
    if fault in ('quality','nonfinite'): pytest.importorskip('torch')
    with pytest.raises(ValueError): clue.train(path,tmp_path/'candidate',cuts,epochs=2)


def test_train_only_scaling_calibration_holdout_isolation_and_saved_inference(dataset,tmp_path):
    torch=pytest.importorskip('torch')
    import joblib
    import numpy as np
    path,data,cuts=dataset
    bundle=tmp_path/'candidate'
    first=clue.train(path,bundle,cuts,epochs=2)
    _,parts=clue.select(data,cuts)
    scaler=joblib.load(bundle/'clue_scaler_v1.pkl')
    np.testing.assert_allclose(scaler.mean_,clue.matrix(parts[1]).mean(axis=0))
    model=clue.build_model()
    checkpoint=torch.load(bundle/'clue_ae_v1.pt',weights_only=True)
    model.load_state_dict(checkpoint['state_dict'])
    calibration=torch.tensor(scaler.transform(clue.matrix(parts[3])).astype(np.float32))
    assert float(np.quantile(clue.errors(model,calibration),0.99))==first['threshold_raw_mse']
    report=clue.evaluate(path,bundle,tmp_path/'evaluation.json')
    heldout=torch.tensor(scaler.transform(clue.matrix(parts[4])).astype(np.float32))
    assert report['normal_alerts']==int((clue.errors(model,heldout)>first['threshold_raw_mse']).sum())
    assert report['attack_recall'] is None and report['activated'] is False
    # Later feature values cannot affect fitted weights/scaler/calibration.
    for row in data['rows']:
        if row['date']>cuts[3]: row['features']['event_count']+=999999
    path.write_text(json.dumps(data))
    second=clue.train(path,tmp_path/'repeat',cuts,epochs=2)
    other=torch.load(tmp_path/'repeat/clue_ae_v1.pt',weights_only=True)
    for key,value in checkpoint['state_dict'].items(): assert torch.equal(value,other['state_dict'][key])
    assert first['threshold_raw_mse']==second['threshold_raw_mse']
    with pytest.raises(ValueError): clue.evaluate(path,bundle,tmp_path/'changed-data.json')
    with pytest.raises(ValueError): clue.train(path,bundle,cuts,epochs=2)


def test_tampered_artifact_is_refused_before_loading(dataset,tmp_path):
    pytest.importorskip('torch')
    path,_,cuts=dataset
    bundle=tmp_path/'candidate'
    clue.train(path,bundle,cuts,epochs=2)
    (bundle/'clue_scaler_v1.pkl').write_bytes(b'tampered')
    with pytest.raises(ValueError): clue.evaluate(path,bundle,tmp_path/'evaluation.json')
