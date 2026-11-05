import pytest
from scripts import provision_cloudflare_machine as lab


class API:
    account='account'
    def __init__(self,wrong=False):self.calls=[];self.wrong=wrong
    def all(self,path):return [{'id':'token','name':lab.setup.NAME}] if path=='access/service_tokens' else []
    def call(self,method,path,body=None,mime=None):
        self.calls.append((method,path,body))
        if path=='access/apps':return {'id':'app'}
        if path.endswith('/policies'):
            return [{'decision':'non_identity','include':[{'service_token':{'token_id':'other' if self.wrong else 'token'}}]}]
        return {}


def args():return {'account':'account','token_id':'token','host':'argus-machine-lab.test.workers.dev'},{'id':'token'}


def test_inspect_has_no_writes(tmp_path):
    api=API();scope,token=args()
    assert lab.provision(api,scope,token,tmp_path)['changes']==0
    assert not api.calls


def test_enable_only_after_exact_service_auth_readback(tmp_path):
    api=API();scope,token=args()
    assert lab.provision(api,scope,token,tmp_path,True)['status']=='deployed'
    assert api.calls[-1][2]=={'enabled':True,'previews_enabled':False}
    assert any(path=='access/apps/app/policies' for _,path,_ in api.calls[:-1])
    assert all('argus-access-demo' not in path for _,path,_ in api.calls)


def test_wrong_policy_leaves_route_disabled_and_retains_claim(tmp_path):
    api=API(wrong=True);scope,token=args()
    with pytest.raises(ValueError):lab.provision(api,scope,token,tmp_path,True)
    assert not any(body=={'enabled':True,'previews_enabled':False} for _,_,body in api.calls)
    assert (tmp_path/'provisioning.json').exists()
