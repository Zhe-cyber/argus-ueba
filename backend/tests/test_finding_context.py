import json
from backend import event_store,alert_store
from backend.tests.test_case_workspace import db,client,seed
from workspace_next import queries,case_store
from workspace_next.finding_context import object_value,RULE_WINDOW


def test_timezone_wording_is_display_only_and_keeps_recorded_severity(client):
    seed()
    original=alert_store.create_alert('account-aws','anomalous_behavior','High',
        'First-time action outside business hours for account-aws',
        {'timestamp':'2026-10-30T01:04:00Z','action':'Read'})
    rendered=client.get('/findings/'+str(original['id'])).json()
    assert rendered['display_title']=='First-seen action outside the UTC rule window'
    assert rendered['rule_window']==RULE_WINDOW
    assert rendered['rule_event_time_utc']=='2026-10-30T01:04:00+00:00'
    assert rendered['severity']=='High' and rendered['title']==original['title']
    assert alert_store.get_alert(original['id'])==original


def test_native_service_classification_is_filterable_not_name_inference(client):
    seed()
    with event_store._db() as con:
        con.execute('UPDATE events SET metadata=?', (json.dumps({'userIdentity':{'sessionContext':{
            'sessionIssuer':{'arn':'arn:aws:iam::123456789012:role/aws-service-role/resource-explorer.amazonaws.com/AWSServiceRoleForResourceExplorer'}}}}),))
    finding=alert_store.create_alert('account-aws','rarity_spike','High','Signal')
    service=client.get('/findings?entity_context=service_or_workload').json()['findings']
    assert [row['id'] for row in service]==[finding['id']]
    assert service[0]['history_context']=='limited_observed_history'
    assert client.get('/findings?entity_context=other_or_unclassified').json()['findings']==[]
    with event_store._db() as con:
        con.execute("UPDATE events SET metadata='{}',account_label='AWSServiceRoleForResourceExplorer'")
    assert client.get('/findings?entity_context=service_or_workload').json()['findings']==[]


def test_resource_literal_is_parsed_without_rewriting_native_value(db):
    event_id=seed()
    text="{'type': 'custom', 'maxItems': '100'}"
    with event_store._db() as con: con.execute('UPDATE events SET resource=?',(text,))
    evidence=case_store.evidence(event_id)
    assert evidence['resource']==text
    assert evidence['resource_value']=={'type':'custom','maxItems':'100'}
    assert object_value("__import__('os').remove('x')")=="__import__('os').remove('x')"


def test_readable_title_and_account_label_preserve_internal_key(client):
    seed('acct_'+'a'*64)
    key='acct_'+'a'*64
    with event_store._db() as con: con.execute("UPDATE events SET account_label='Readable account'")
    alert=alert_store.create_alert(key,'rarity_spike','High','Signal for '+key)
    row=client.get('/findings/'+str(alert['id'])).json()
    assert row['account_label']=='Readable account' and row['user_id']==key
    assert row['display_title']=='Signal for Readable account'
    case=case_store.create('Review '+key,'','Analyst','readable-title')
    assert case['display_title']=='Review Readable account' and case['title']=='Review '+key
