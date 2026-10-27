import json

import pytest

from scripts import train_clue_ae as training
from scripts.inspect_clue_candidate import prepare
from scripts.tests.test_clue_training import dataset


def test_review_reproduces_normal_alerts_and_selection_ignores_heldout_values(dataset,tmp_path):
    pytest.importorskip('torch')
    source,data,cuts=dataset
    first=tmp_path/'first'
    training.train(source,first,cuts,epochs=2)
    normal=training.evaluate(source,first,first/'normal_holdout_report.json')
    diagnostics,plan=prepare(source,first,tmp_path/'review-first')
    assert diagnostics['normal_alerts']==normal['normal_alerts']
    assert plan['executed'] is False and len(plan['cases'])==3
    assert len({c[k] for c in plan['cases'] for k in ('left','right')})==6
    assert plan['switch_day_utc']=='2020-01-10'
    for row in data['rows']:
        if row['date']>cuts[3]: row['features']['event_count']+=999999
    source.write_text(json.dumps(data))
    second=tmp_path/'second'
    training.train(source,second,cuts,epochs=2)
    training.evaluate(source,second,second/'normal_holdout_report.json')
    _,other=prepare(source,second,tmp_path/'review-second')
    assert other['cases']==plan['cases']


def test_review_refuses_changed_report_binding(dataset,tmp_path):
    pytest.importorskip('torch')
    source,_,cuts=dataset
    bundle=tmp_path/'candidate'
    training.train(source,bundle,cuts,epochs=2)
    training.evaluate(source,bundle,bundle/'normal_holdout_report.json')
    p=bundle/'normal_holdout_report.json'
    report=json.loads(p.read_text()); report['manifest_sha256']='0'*64
    p.write_text(json.dumps(report))
    with pytest.raises(ValueError): prepare(source,bundle,tmp_path/'refused')
