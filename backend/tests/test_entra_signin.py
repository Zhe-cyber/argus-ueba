"""Entra ID sign-in: normaliser mapping of the Graph signIn schema and source-scoped identity keys.
Synthetic fixtures only (backend/tests/data/entra_signins_synthetic.json)."""
import json
from pathlib import Path

from backend import account_identity as identity
from backend.normalizer import normalize

FIXTURE = json.loads((Path(__file__).parent / 'data' / 'entra_signins_synthetic.json').read_text(encoding='utf-8'))
OK, FAIL, SP = FIXTURE['value']
TENANT = 'dddddddd-4444-4555-8666-777777777777'


def event(record, tenant=TENANT):
    return {**normalize(record, 'azure_ad'), 'source_account_id': tenant}


def test_success_signin_maps_graph_fields():
    e = normalize(OK, 'azure_ad')
    assert (e['timestamp'], e['user'], e['action']) == ('2026-10-20T02:15:00Z', 'alice@contoso.example', 'signin_success')
    assert e['resource'] == 'Office 365 Exchange Online' and e['ip_address'] == '203.0.113.10'
    m = e['metadata']
    assert m['country'] == 'MY' and m['clientApp'] == 'Browser' and m['errorCode'] == 0
    assert m['conditionalAccessStatus'] == 'success' and m['riskLevelDuringSignIn'] == 'none'
    assert e['event_id'] == OK['id']


def test_failure_signin_and_resource_fallback():
    e = normalize(FAIL, 'azure_ad')
    assert e['action'] == 'signin_failure' and e['metadata']['errorCode'] == 50126
    assert e['resource'] == 'Azure Portal' and e['metadata']['resourceDisplayName'].startswith('Windows Azure')
    no_app = {**FAIL, 'appDisplayName': ''}
    assert normalize(no_app, 'azure_ad')['resource'] == 'Windows Azure Service Management API'


def test_service_principal_user_label_falls_back():
    e = normalize(SP, 'azure_ad')
    assert e['user'] == 'nightly-export' and e['action'] == 'signin_success'


def test_legacy_non_graph_record_keeps_old_mapping():
    legacy = {k: v for k, v in OK.items() if k not in ('signInEventTypes', 'riskLevelDuringSignIn', 'isInteractive')}
    e = normalize(legacy, 'azure_ad')
    assert e['action'] == 'Office 365 Exchange Online'


def test_user_identity_key_is_object_id_not_upn():
    a = identity.identify(event(OK))
    assert a['account_kind'] == 'user' and a['account_basis'] == 'entra_user_object_id'
    assert a['account_label'] == 'Alice Example'
    renamed = {**OK, 'userPrincipalName': 'alice.new@contoso.example', 'userDisplayName': 'Alice Renamed'}
    b = identity.identify(event(renamed))
    assert a['account_key'] == b['account_key'] and b['account_label'] == 'Alice Renamed'
    other = {**OK, 'userId': 'eeeeeeee-1111-4222-8333-444444444444'}
    assert identity.identify(event(other))['account_key'] != a['account_key']


def test_service_principal_identity():
    s = identity.identify(event(SP))
    assert s['account_kind'] == 'service_principal' and s['account_basis'] == 'entra_service_principal_id'
    assert s['account_label'] == 'Nightly Export Job'
    app_only = {k: v for k, v in SP.items() if k != 'servicePrincipalId'}
    assert identity.identify(event(app_only))['account_basis'] == 'entra_app_id'


def test_identity_is_tenant_scoped_and_needs_evidence():
    assert identity.identify(event(OK))['account_key'] != identity.identify(event(OK, tenant='ffffffff-4444-4555-8666-777777777777'))['account_key']
    assert identity.identify({**event(OK), 'source_account_id': ''}) is None
    nothing = {**OK, 'userId': '00000000-0000-0000-0000-000000000000'}
    nothing.pop('appId')
    assert identity.identify(event(nothing)) is None
    assert identity.identify(event({**OK, 'userId': 'not-a-guid'})) is None  # a user sign-in never falls back to its app
