from datetime import datetime, timezone
import json
import pytest
from scripts import cloudflare_lab_setup as lab
from scripts.setup_cloudflare import APIError


class API:
    account='0'*32
    def __init__(self, denied=False, collision=False):
        self.denied,self.collision,self.calls=denied,collision,[]
    def all(self,path):
        return [{'name':lab.NAME}] if self.collision and path=='access/service_tokens' else []
    def call(self,method,path,body=None):
        self.calls.append((method,path,body))
        if method=='GET':return {'subdomain':'test'}
        if self.denied:raise APIError('permission denied',403)
        return {'id':'native-id','client_id':'client','client_secret':'secret'}


NOW=datetime(2026,10,30,tzinfo=timezone.utc)


def test_create_encrypts_one_secret_and_never_edits_existing_app(tmp_path,monkeypatch):
    api=API(); saved=[]
    monkeypatch.setattr(lab,'dpapi',lambda value,encrypt:value)
    monkeypatch.setattr(lab,'save_secret',lambda path,value:saved.append(value))
    assert lab.create_token(api,tmp_path,NOW)['app_deployed'] is False
    writes=[c for c in api.calls if c[0]!='GET']
    assert len(writes)==1 and writes[0][1]=='access/service_tokens'
    assert writes[0][2]['duration']==str(int((lab.EXPIRY-NOW).total_seconds()))+'s'
    assert saved[0]['client_secret']=='secret'
    assert 'secret' not in (tmp_path/'scope.json').read_text()
    assert 'secret' not in (tmp_path/'token-attempt.json').read_text()


def test_permission_denial_is_recorded_without_credentials(tmp_path,monkeypatch):
    monkeypatch.setattr(lab,'dpapi',lambda value,encrypt:value)
    monkeypatch.setattr(lab,'save_secret',lambda *args:pytest.fail('No token returned'))
    with pytest.raises(APIError):lab.create_token(API(denied=True),tmp_path,NOW)
    assert json.loads((tmp_path/'token-attempt.json').read_text())['status']=='permission_denied'


def test_unknown_outcome_collision_expiry_and_failed_encryption_block_writes(tmp_path,monkeypatch):
    api=API(collision=True)
    with pytest.raises(ValueError):lab.create_token(api,tmp_path,NOW)
    assert all(c[0]=='GET' for c in api.calls)
    api=API()
    with pytest.raises(ValueError):lab.create_token(api,tmp_path,lab.EXPIRY)
    assert not api.calls
    (tmp_path/'token-attempt.json').write_text('{"status":"claimed_unknown"}')
    with pytest.raises(ValueError):lab.create_token(api,tmp_path,NOW)
    assert not api.calls
