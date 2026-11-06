import base64
import json
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from scripts import github_lab_app as app


def secret():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, {'id': 123, 'owner': {'login': 'Zhe-cyber'}, 'slug': 'argus-workload-lab-test',
                 'permissions': {'contents': 'write', 'metadata': 'read'},
                 'pem': key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()).decode()}


def test_manifest_requests_only_repo_contents_no_webhooks_or_user_oauth():
    d = app.manifest('statevalue')
    assert d['default_permissions'] == {'contents': 'write', 'metadata': 'read'}
    assert d['public'] is False and d['hook_attributes']['active'] is False
    assert d['hook_attributes']['url'].startswith('https://argus-access-demo.')
    assert '127.0.0.1' not in d['hook_attributes']['url']
    assert d['default_events'] == [] and d['request_oauth_on_install'] is False
    assert d['redirect_url'].startswith('http://127.0.0.1:8774/')


def test_jwt_signature_and_expiry_and_registration_scope():
    key, document = secret()
    app.validate_registration(document)
    a, b, signature = app.app_jwt(document).split('.')
    decode = lambda x: base64.urlsafe_b64decode(x+'='*((-len(x))%4))
    key.public_key().verify(decode(signature), (a+'.'+b).encode(), padding.PKCS1v15(), hashes.SHA256())
    payload = json.loads(decode(b))
    assert payload['iss'] == '123' and payload['exp']-payload['iat'] == 540
    for patch in [{'owner': {'login': 'other'}}, {'permissions': {'contents': 'write','issues':'write'}}, {'slug': 'other'}]:
        with pytest.raises(ValueError):
            app.validate_registration({**document, **patch})


def test_no_plaintext_fallback_or_overwrite(tmp_path, monkeypatch):
    path = tmp_path/'app.dpapi'
    def fail(*args):
        raise ValueError('no protection')
    monkeypatch.setattr(app, 'dpapi', fail)
    with pytest.raises(ValueError):
        app.save_secret(path, {'pem': 'PRIVATE'})
    assert not path.exists()
    monkeypatch.setattr(app, 'dpapi', lambda *args: b'encrypted')
    app.save_secret(path, {'pem': 'PRIVATE'})
    assert path.read_bytes() == b'encrypted'
    with pytest.raises(FileExistsError):
        app.save_secret(path, {'pem': 'replacement'})


def test_installation_token_is_bound_to_one_repo_and_owner(monkeypatch):
    _, document = secret()
    calls = []
    def api(method,path,token=None,body=None):
        calls.append((method,path,body))
        if path.endswith('/access_tokens'):
            assert body == {'repository_ids':[7],'permissions':{'contents':'write','metadata':'read'}}
            return {'token':'installation'}
        if path.startswith('/app/installations/'):
            return {'account':{'login':'Zhe-cyber'},'app_id':123,'repository_selection':'selected',
                    'permissions':{'contents':'write','metadata':'read'},'suspended_at':None}
        return {'id':7,'private':True}
    monkeypatch.setattr(app,'api',api)
    assert app.installation_token(document,7,9)=='installation'
    assert len(calls)==3
    monkeypatch.setattr(app,'api',lambda *args: {'account':{'login':'other'}})
    with pytest.raises(ValueError):
        app.installation_token(document,7,9)


def test_inventory_uses_metadata_only_token_and_rejects_extra_repos(monkeypatch):
    _, document = secret()
    extra = []
    def api(method,path,token=None,body=None):
        if path.endswith('/access_tokens'):
            assert body == {'permissions':{'metadata':'read'}}
            return {'token':'read-only-inventory'}
        if path == '/installation/repositories':
            assert token == 'read-only-inventory'
            return {'total_count':1+len(extra),'repositories':[{'id':7}]+extra}
        return {'account':{'login':'Zhe-cyber'},'app_id':123,'repository_selection':'selected',
                'permissions':{'contents':'write','metadata':'read'},'suspended_at':None}
    monkeypatch.setattr(app,'api',api)
    app.verify_repository_selection(document,7,9)
    extra.append({'id':8})
    with pytest.raises(ValueError):
        app.verify_repository_selection(document,7,9)
