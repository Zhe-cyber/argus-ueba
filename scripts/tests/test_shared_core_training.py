import json
import pytest
from scripts import train_shared_core_ae as trainer
from scripts.shared_core_features import PROFILE, FEATURES


def row(account, day, n=10):
    return {'account': account, 'day': day, 'eligible': True, 'prior_active_days': 5, 'issues': {},
            'features': dict(zip(FEATURES, [n, 2, 1, 0.25, 1]))}


def test_partitions_do_not_use_development_or_ineligible_rows():
    rows = [row('a', date) for date in ['2017-07-13', '2017-07-27', '2017-08-01', '2017-08-05']]
    rows.append({**row('b', '2017-07-13'), 'eligible': False, 'features': None})
    assert [[r['day'] for r in part] for part in trainer.partitions({'rows': rows})] == [['2017-07-13'], ['2017-07-27'], ['2017-08-01']]


def test_fraction_stays_unlogged_and_count_invariants_enforced():
    import numpy as np
    vector = trainer.matrix([row('a', '2017-07-13')])[0]
    assert vector[3] == 0.25 and vector[0] == np.log1p(10)
    invalid = row('a', '2017-07-13'); invalid['features']['new_action_count'] = 3
    with pytest.raises(ValueError, match='invariant'):
        trainer.matrix([invalid])


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    original = trainer.ROOT
    for name in trainer.SOURCE_FILES:
        target = tmp_path / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((original / name).read_bytes())
    monkeypatch.setattr(trainer, 'ROOT', tmp_path)
    population = [f'account-{index:02d}' for index in range(55)]
    rows = [row(account, day, 3 + index % 10) for index, account in enumerate(population)
            for day in ['2017-07-13', '2017-07-14', '2017-07-27', '2017-08-01', '2017-08-02', '2017-08-03', '2017-08-04']]
    data = {'profile': PROFILE, 'features': FEATURES, 'k': 5, 'reserved_access': False, 'population': population,
            'rows': rows, 'bindings': {'sources': {'shared_core_features.py': trainer.sha(tmp_path / 'scripts/shared_core_features.py')}}}
    path = tmp_path / 'data/input.json'; path.parent.mkdir(); path.write_text(json.dumps(data))
    return path, tmp_path / 'data/prereg.json', tmp_path / 'data/candidate'


def test_preregistration_binds_data_before_training(prepared):
    data, prereg, output = prepared
    assert trainer.preregister(data, prereg)['reserved_access_authorised'] is False
    document = json.loads(data.read_text()); document['rows'][0]['features']['event_count'] += 1
    data.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='preregistration mismatch'):
        trainer.train(data, prereg, output)
    assert not output.exists()


def test_future_rows_refused_before_model_or_thresholds(prepared):
    data, prereg, _ = prepared
    document = json.loads(data.read_text()); document['rows'].append(row(document['population'][0], '2017-08-11'))
    data.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='reserved/future'):
        trainer.preregister(data, prereg)
    assert not prereg.exists()


def test_engineering_training_saved_parity_no_activation_and_no_overwrite(prepared):
    data, prereg, output = prepared
    trainer.preregister(data, prereg)
    report = trainer.train(data, prereg, output)
    assert report['partition_rows'] == {'fit': 110, 'validation': 55, 'normal_calibration': 220}
    assert report['saved_score_parity'] == 'exact' and report['activated'] is False
    assert report['evaluation_status'] == 'not_evaluated'
    assert json.loads((output / 'scaler.json').read_text())['fit_samples'] == 110
    with pytest.raises(ValueError, match='New private output'):
        trainer.train(data, prereg, output)
