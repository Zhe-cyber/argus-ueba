import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend import clue_replay as replay


def write_bundle(root, rows=None):
    root.mkdir()
    policy = {'schema_version': 1, 'profile': replay.PROFILE, 'features': replay.FEATURES,
              'medium_threshold': .5, 'high_threshold': 1., 'medium_quantile': .95,
              'high_quantile': .99, 'quantile_method': 'linear', 'boundary_rule': 'strictly_greater',
              'units': 'raw_reconstruction_mse',
              'cutoffs_utc': ['2020-01-01', '2020-01-03', '2020-01-05', '2020-01-07', '2020-01-09'],
              **{k: 'a'*64 for k in ('model_sha256', 'scaler_sha256', 'dataset_sha256', 'candidate_manifest_sha256')},
              'private_extra': 'NEVER-SERVE-THIS'}
    if rows is None:
        rows = []
        for i, (day, split, value) in enumerate([('2020-01-06', 'calibration', 2),
                                                ('2020-01-08', 'heldout', .1),
                                                ('2020-01-08', 'heldout', .8),
                                                ('2020-01-09', 'heldout', 1.2)]):
            rows.append({'account': f'cohort-{i+1}', 'day': day, 'split': split, 'raw_mse': value,
                         'review_priority': replay.priority(value,.5,1),
                         'features': dict.fromkeys(replay.FEATURES, 1),
                         'residuals': {f: value if j == 0 else 0 for j,f in enumerate(replay.FEATURES)},
                         'raw_identity': 'NEVER-SERVE-THIS'})
    (root/'policy.json').write_text(json.dumps(policy))
    (root/'replay.json').write_text(json.dumps({'schema_version':1,'profile':replay.PROFILE,'rows':rows}))
    bind(root)
    return policy,rows


def bind(root):
    (root/'manifest.json').write_text(json.dumps({'schema_version':1,
        **{name+'_sha256':hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('policy.json','replay.json')}}))


def client():
    # Standalone router: no app lifespan, database, benchmark loader or model import.
    app=FastAPI();app.include_router(replay.router)
    return TestClient(app)


def test_default_is_heldout_and_projection_filters_private_fields(tmp_path,monkeypatch):
    root=tmp_path/'bundle';write_bundle(root);monkeypatch.setenv('CLUE_REPLAY_DIR',str(root))
    with client() as c:
        response=c.get('/replay/clue/rows');assert response.status_code==200
        data=response.json();assert data['split']=='heldout' and data['total']==3
        assert {r['review_priority'] for r in data['rows']}=={'Low','Medium','High'}
        assert 'NEVER-SERVE' not in response.text
        meta=c.get('/replay/clue/metadata')
        assert meta.json()['splits']['heldout']['counts']=={'Low':1,'Medium':1,'High':1}
        assert meta.json()['splits']['calibration']['account_days']==1
        assert 'NEVER-SERVE' not in meta.text
        assert c.get('/replay/clue/rows?split=calibration').json()['total']==1
        assert c.get('/replay/clue/rows?review_priority=High&day=2020-01-09').json()['total']==1
        assert c.get('/replay/clue/rows?split=fit').status_code==422


@pytest.mark.parametrize('value,expected',[(0,'Low'),(.5,'Low'),(.500001,'Medium'),(1,'Medium'),(1.000001,'High')])
def test_strict_boundaries(value,expected):
    assert replay.priority(value,.5,1)==expected


@pytest.mark.parametrize('fault',['digest','fit_row','duplicate','priority','residual','identifier','nan','private_feature'])
def test_invalid_bundle_fails_closed(tmp_path,monkeypatch,fault):
    root=tmp_path/'bundle';_,rows=write_bundle(root)
    if fault=='digest': rows[0]['raw_identity']='changed without rebinding'
    elif fault=='fit_row': rows[0]['day']='2020-01-02'
    elif fault=='duplicate': rows.append(rows[-1])
    elif fault=='priority': rows[-1]['review_priority']='Low'
    elif fault=='residual': rows[-1]['residuals'][replay.FEATURES[0]]=99
    elif fault=='identifier': rows[0]['account']='alice@example.invalid'
    elif fault=='nan': rows[-1]['raw_mse']=float('nan')
    elif fault=='private_feature':rows[0]['features']={'secret':123}
    (root/'replay.json').write_text(json.dumps({'schema_version':1,'profile':replay.PROFILE,'rows':rows}))
    if fault!='digest':bind(root)
    monkeypatch.setenv('CLUE_REPLAY_DIR',str(root))
    with client() as c:
        assert c.get('/replay/clue/metadata').json()['available'] is False
        assert c.get('/replay/clue/rows').status_code==503


def test_unconfigured_has_no_demo_fallback(monkeypatch):
    monkeypatch.delenv('CLUE_REPLAY_DIR',raising=False)
    with client() as c:
        assert c.get('/replay/clue/metadata').json()['available'] is False
        assert c.get('/replay/clue/rows').status_code==503
