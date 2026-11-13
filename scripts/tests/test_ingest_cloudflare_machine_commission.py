import pytest
from scripts.ingest_cloudflare_machine_commission import checked_event


def test_native_machine_receipt_scope_without_fabricated_fields():
    e={'connection':'nonidentity','user_email':'a'*32+'.access','app_uid':'app','allowed':True,
       'ray_id':'ray','created_at':'2026-10-30T03:00:00Z','action':'login','app_domain':'toy.example.test'}
    scope={'token_id':'token','account':'account'}
    t={'id':'token','client_id':e['user_email']};receipt={'app_id':'app','ray_id':'ray'}
    original=e.copy()
    assert checked_event(e,scope,t,receipt)['account_kind']=='service_token'
    assert e==original
    for key,value in [('connection','onetimepin'),('user_email','other.access'),('app_uid','other'),('allowed',False),('ray_id','other')]:
        with pytest.raises(ValueError):checked_event({**e,key:value},scope,t,receipt)
