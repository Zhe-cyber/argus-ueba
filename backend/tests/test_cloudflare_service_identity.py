from backend.normalizer import normalize
from backend.account_identity import identify


def event(**patch):
    raw={'created_at':'2026-10-30T01:00:00Z','action':'login','allowed':True,
         'connection':'nonidentity','user_email':'a'*32+'.access','user_id':'',
         'app_uid':'app','app_domain':'toy.workers.dev','ray_id':'1234567890abcdef'}
    raw.update(patch)
    item=normalize(raw,'cloudflare_access');item['source_account_id']='account'
    return item


def test_native_nonidentity_client_id_is_machine_not_human():
    item=event();account=identify(item)
    assert item['metadata']['allowed'] is True
    assert item['metadata']['connection']=='nonidentity'
    assert account['account_kind']=='service_token'
    assert account['account_basis']=='cloudflare_service_client_id'
    assert account['account_key']!=identify(event(user_email='b'*32+'.access'))['account_key']
    item['source_account_id']='other'
    assert identify(item)['account_key']!=account['account_key']


def test_human_id_stays_separate_and_email_alone_never_authenticates():
    machine=identify(event())
    human=identify(event(connection='onetimepin',user_id='person-native'))
    assert human['account_kind']=='account'
    assert human['account_basis']=='cloudflare_user_id'
    assert human['account_key']!=machine['account_key']
    assert identify(event(connection='onetimepin')) is None
    assert identify(event(user_email='person@example.test',user_id='person-native')) is None


def test_missing_allowed_stays_missing_in_metadata_not_inferred_true():
    raw=event()['raw'];raw.pop('allowed')
    assert 'allowed' not in normalize(raw,'cloudflare_access')['metadata']
