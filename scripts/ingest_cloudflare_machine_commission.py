"""Forward the exact captured machine commissioning log; never fabricate identity."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import cloudflare_lab_setup as setup
from scripts.github_lab_app import atomic,load_secret
from scripts.collect_live import LocalBackend
from backend.normalizer import normalize
from backend.account_identity import identify


def checked_event(event,scope,token,receipt):
    if (event.get('connection')!='nonidentity' or event.get('user_email')!=token.get('client_id')
            or not token.get('client_id') or token.get('id')!=scope.get('token_id')
            or event.get('app_uid')!=receipt.get('app_id') or not receipt.get('app_id')
            or event.get('allowed') is not True or event.get('ray_id')!=receipt.get('ray_id')
            or not event.get('ray_id') or not event.get('created_at')):
        raise ValueError('Native machine log does not match authenticated request/credential scope')
    normalized=normalize(event,'cloudflare_access');normalized['source_account_id']=scope['account']
    account=identify(normalized)
    if account is None or account['account_kind']!='service_token':
        raise ValueError('Explicit native machine identity is unavailable')
    return account


def main():
    scope=json.loads((setup.STATE/'scope.json').read_bytes())
    token=load_secret(setup.STATE/'persona-01.dpapi')
    receipt=json.loads((setup.STATE/'request-commissioning.json').read_bytes())
    event=json.loads((setup.STATE/'commissioning-native-log.json').read_bytes())
    account=checked_event(event,scope,token,receipt)
    backend=LocalBackend('http://127.0.0.1:8013');backend.preflight()
    duplicate=backend.post('cloudflare_access',scope['account'],event,event['ray_id'])
    if duplicate is None:raise ValueError('No durable ingestion receipt')
    result={'status':'ingested','duplicate':duplicate,'account_key':account['account_key'],
            'account_kind':'service_token','event_id':event['ray_id'],'scheduled_workload':False,'model_activated':False}
    atomic(setup.STATE/'ingestion-receipt.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['account_key','event_id']}))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'status':'stopped','error_type':type(error).__name__}));raise SystemExit(1)
