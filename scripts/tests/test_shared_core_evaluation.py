import json
import numpy as np
import pytest
from scripts import evaluate_shared_core_ae as evaluation, shared_core_features as features, train_shared_core_ae as training
from scripts.tests.test_shared_core_training import prepared


def native(day, uid, native_id, params=None):
    return {'id': native_id, 'uid': uid, 'uidType': 'name', 'type': 'file_accessed',
            'time': day+'T10:00:00Z', 'params': {'path': '/same/file'} if params is None else params}


def fixture_events():
    rows = []
    for day in ['2017-07-07','2017-07-08','2017-07-09','2017-07-10','2017-07-11','2017-08-11','2017-08-25']:
        for uid in ['a','b']:
            rows.append(native(day,uid,len(rows)+1))
    return rows


def fake_score(vector):
    return {'ae': float(vector['event_count']+vector['off_hours_fraction']),
            'max_deviation': float(vector['event_count'])}


def thresholds():
    return {str(b): {detector: {'threshold': 1.5} for detector in ['ae','max_deviation']}
            for b in training.METHOD['budgets']}


def population():
    return {features.project_clue(native('2017-07-07',uid,1)).account for uid in ['a','b']}


def test_complete_fixture_pipeline_keeps_identical_switch_as_positive():
    result = evaluation.analyse(fixture_events(), population(), evaluation.TEST_WINDOW, fake_score, thresholds())
    assert result['summary']['normal_scored_days'] == 2
    assert result['summary']['generated_cases'] == {'account_switch':1,'mass_access':2,'new_action':2,'off_hours':2}
    assert result['summary']['zero_feature_change']['account_switch'] == 1
    assert result['metrics']['account_switch']['ae']['injected_cases'] == 1
    assert result['metrics']['account_switch']['ae']['auroc'] == 0.5
    assert result['metrics']['off_hours']['ae']['auroc'] == 1
    assert result['metrics']['off_hours']['max_deviation']['auroc'] == 0.5
    assert result['summary']['switch_design']=={'pairs':1,'target_accounts':1,'donor_only_accounts':1,
        'unpaired_accounts':0,'non_target_observed_days':{'donor_only':1}}


def test_missing_input_is_not_a_negative_and_inactive_population_not_idle_days():
    rows = fixture_events()
    for row in rows:
        if row['time'].startswith('2017-08-11') and row['uid']=='a': row['params']={}
    pop=population() | {'absent-fitting-selected-account'}
    result=evaluation.analyse(rows,pop,evaluation.TEST_WINDOW,fake_score,thresholds())
    assert result['summary']['normal_scored_days']==1
    assert result['summary']['normal_unscored']=={'input_quality':1}
    assert result['summary']['identities_without_test_activity']==1
    assert result['metrics']['mass_access']['ae']['normal_days']==1


def test_missing_post_window_boundary_refuses_partial_result():
    rows=[row for row in fixture_events() if not row['time'].startswith('2017-08-25')]
    with pytest.raises(ValueError,match='boundary'):
        evaluation.analyse(rows,population(),evaluation.TEST_WINDOW,fake_score,thresholds())


def test_release_hash_rejected_before_source_iteration(tmp_path,monkeypatch):
    release=tmp_path/'release.json';release.write_text('{}')
    monkeypatch.setattr(evaluation,'stream_archive',lambda *_: (_ for _ in ()).throw(AssertionError('Reserved access')))
    with pytest.raises(ValueError,match='Release hash'):
        evaluation.evaluate(release,'0'*64,tmp_path/'output')
    assert not (tmp_path/'output').exists()


def test_wrong_official_source_refused_before_opening_member(tmp_path,monkeypatch):
    release=tmp_path/'release.json'
    record={'kind':'shared_core_reserved_release_v1','window':list(evaluation.TEST_WINDOW),
            'source_hashes':{name:training.sha(evaluation.ROOT/name) for name in evaluation.RELEASE_SOURCES},
            'artifacts':{name:{'path':'unopened','sha256':'0'*64} for name in
                         ['archive','data','preregistration','manifest','model','scaler','rehearsal']},'live_activation':False}
    release.write_text(json.dumps(record))
    monkeypatch.setattr(evaluation,'stream_archive',lambda *_: (_ for _ in ()).throw(AssertionError('Reserved access')))
    with pytest.raises(ValueError,match='official source'):
        evaluation.evaluate(release,training.sha(release),tmp_path/'output')


def test_canonical_inference_calibration_preserves_weights_and_quantile_policy(prepared):
    import torch
    data,prereg,candidate=prepared
    training.preregister(data,prereg);training.train(data,prereg,candidate)
    before={name:training.sha(candidate/name) for name in ['model.pt','scaler.json','manifest.json']}
    score,manifest,document=evaluation.candidate_scorer(candidate,data,prereg)
    calibration=training.partitions(document)[2]
    scores=[score(row['features']) for row in calibration]
    scaler=json.loads((candidate/'scaler.json').read_bytes())
    values=training.matrix(calibration)
    x=torch.tensor((values-np.asarray(scaler['mean']))/np.asarray(scaler['scale']),dtype=torch.float32)
    restored=training.build_model();restored.load_state_dict(torch.load(candidate/'model.pt',weights_only=True));restored.eval()
    with torch.no_grad():
        reference=[float(((restored(x[i:i+1])-x[i:i+1])**2).mean(dim=1)[0]) for i in range(len(x))]
    assert reference==[row['ae'] for row in scores]
    for b in training.METHOD['budgets']:
        for detector in ['ae','max_deviation']:
            expected=float(np.quantile([row[detector] for row in scores],1-b,method='higher'))
            assert manifest['thresholds'][str(b)][detector]['threshold']==expected
    assert before=={name:training.sha(candidate/name) for name in before}
    assert 'training_thresholds' in manifest and manifest['activated'] is False


def test_live_guard_does_not_learn_unknown_action_hidden_by_resource_gap():
    from scripts.shared_core_live_guard import project_live
    row={'source':'github_events','source_account_id':'repo','account_key':'acct_'+'a'*64,
         'event_id':'event','payload_digest':'b'*64,'timestamp':'2026-10-30T02:00:00Z',
         'action':'PushEvent','resource':'','metadata':{}}
    day=features.Day();day.add(project_live(row))
    assert day.issues=={'unknown_action':1} and not day.actions
    row.update(source='cloudflare_access',action='access')
    day=features.Day();day.add(project_live(row))
    assert day.issues=={'native_action_missing_or_default_ambiguous':1} and not day.actions


def test_failure_after_access_start_keeps_receipt_not_a_success(tmp_path,monkeypatch):
    root=tmp_path/'data';candidate=root/'candidate';candidate.mkdir(parents=True)
    paths={'archive':root/'archive.zip','data':root/'input.json','preregistration':root/'prereg.json',
           'manifest':candidate/'manifest.json','model':candidate/'model.pt',
           'scaler':candidate/'scaler.json','rehearsal':root/'rehearsal.json'}
    for path in paths.values():path.write_bytes(b'engineering-fixture')
    official=training.sha(paths['archive'])
    monkeypatch.setattr(evaluation,'ARCHIVE_SHA',official)
    monkeypatch.setattr(training,'ROOT',tmp_path)
    manifest={'thresholds':thresholds(),'evaluation_numerics':{}}
    monkeypatch.setattr(evaluation,'candidate_scorer',lambda *_:(fake_score,manifest,{'population':[], 'rows':[]}))
    def failing_stream(*_):raise RuntimeError('Engineering injected parser failure')
    monkeypatch.setattr(evaluation,'stream_archive',failing_stream)
    record={'kind':'shared_core_reserved_release_v1','window':list(evaluation.TEST_WINDOW),
        'source_hashes':{name:training.sha(evaluation.ROOT/name) for name in evaluation.RELEASE_SOURCES},
        'artifacts':{name:{'path':str(path),'sha256':training.sha(path)} for name,path in paths.items()},
        'live_activation':False,'evaluation_thresholds':thresholds(),'evaluation_numerics':{}}
    release=root/'release.json';release.write_text(json.dumps(record));out=root/'output'
    with pytest.raises(RuntimeError,match='injected parser failure'):
        evaluation.evaluate(release,training.sha(release),out)
    assert json.loads((out/'access-receipt.json').read_text())['status']=='failed_after_access_started'
    assert not (out/'evaluation.json').exists()


def test_original_training_hash_chain_already_blocks_changed_scenario_source(prepared,monkeypatch):
    data,prereg,candidate=prepared
    training.preregister(data,prereg);training.train(data,prereg,candidate)
    monkeypatch.setattr(evaluation,'ROOT',training.ROOT)
    source=training.ROOT/'scripts/shared_core_scenarios.py'
    source.write_text(source.read_text()+'\n# engineering tamper fixture\n')
    with pytest.raises(ValueError,match='Training-frozen sources changed'):
        evaluation.candidate_scorer(candidate,data,prereg)


def test_release_requires_the_actual_development_rehearsal_window(tmp_path,monkeypatch):
    check=tmp_path/'rehearsal.json'
    check.write_text(json.dumps({'status':'passed_engineering_only','window':list(evaluation.TEST_WINDOW),'reserved_access':False}))
    monkeypatch.setattr(evaluation,'candidate_scorer',lambda *_:(fake_score,{'thresholds':thresholds()},{}))
    monkeypatch.setattr(evaluation,'archive_hash',lambda *_:(_ for _ in ()).throw(AssertionError('Should not inspect archive')))
    with pytest.raises(ValueError,match='rehearsal required'):
        evaluation.release('unused','unused','unused','unused',check,tmp_path/'release.json')


def test_actual_evaluate_entrypoint_blocks_scenario_edit_before_stream(tmp_path,monkeypatch):
    original=evaluation.ROOT
    for name in evaluation.RELEASE_SOURCES:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((original/name).read_bytes())
    monkeypatch.setattr(evaluation,'ROOT',tmp_path)
    record={'kind':'shared_core_reserved_release_v1','window':list(evaluation.TEST_WINDOW),
            'source_hashes':{name:training.sha(tmp_path/name) for name in evaluation.RELEASE_SOURCES}}
    release=tmp_path/'release.json';release.write_text(json.dumps(record))
    changed=tmp_path/'scripts/shared_core_scenarios.py';changed.write_text(changed.read_text()+'\n# tamper fixture\n')
    monkeypatch.setattr(evaluation,'stream_archive',lambda *_:(_ for _ in ()).throw(AssertionError('Reserved stream reached')))
    with pytest.raises(ValueError,match='Evaluator release mismatch'):
        evaluation.evaluate(release,training.sha(release),tmp_path/'uncreated-output')
    assert not (tmp_path/'uncreated-output').exists()
