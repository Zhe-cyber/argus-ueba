"""Provision one isolated machine-only Access Worker; no existing-app edits."""
import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from scripts import cloudflare_lab_setup as setup
from scripts.setup_cloudflare import multipart
from scripts.github_lab_app import atomic, load_secret

WORKER = 'argus-machine-lab'
MARKER = 'Argus machine workload: authenticated'


def provision(client, scope, token, state=setup.STATE, deploy=False):
    state = Path(state)
    if client.account != scope['account'] or token.get('id') != scope['token_id']:
        raise ValueError('Credential/account binding differs')
    if datetime.now(timezone.utc) >= setup.EXPIRY:
        raise ValueError('Pilot expired')
    scripts, apps, tokens = client.all('workers/scripts'), client.all('access/apps'), client.all('access/service_tokens')
    native = [t for t in tokens if t.get('id') == scope['token_id'] and t.get('name') == setup.NAME]
    if len(native) != 1 or any(s.get('id') == WORKER for s in scripts) or any(a.get('domain') == scope['host'] for a in apps):
        raise ValueError('Token unavailable or same-name app/Worker already exists')
    if not re.fullmatch(r'argus-machine-lab\.[a-z0-9-]+\.workers\.dev',scope['host']):
        raise ValueError('Unexpected machine-lab hostname')
    if not deploy:
        return {'status':'ready','changes':0,'scheduled':False}
    claim=state/'provisioning.json'
    if claim.exists():
        raise ValueError('Previous provisioning attempt requires inspection')
    current={'status':'started','scheduled':False,'model_activated':False,'at_utc':datetime.now(timezone.utc).isoformat()}
    with claim.open('x',encoding='utf-8') as handle:json.dump(current,handle)
    body,mime=multipart({'main_module':'worker.mjs','compatibility_date':'2025-01-01','bindings':[]},
                        (ROOT/'infra/cloudflare-machine-lab.mjs').read_text())
    client.call('PUT','workers/scripts/'+WORKER,body,mime)
    client.call('POST','workers/scripts/'+WORKER+'/subdomain',{'enabled':False,'previews_enabled':False})
    current.update(status='worker_created_route_disabled');atomic(claim,current)
    expected=[{'service_token':{'token_id':scope['token_id']}}]
    app=client.call('POST','access/apps',{'type':'self_hosted','name':'Argus controlled machine workloads',
        'domain':scope['host'],'app_launcher_visible':False,'session_duration':'1h',
        'policies':[{'name':'Exact lab service token only','decision':'non_identity','include':expected}]})
    current.update(status='app_created_policy_pending',app_id=app['id']);atomic(claim,current)
    policies=client.call('GET','access/apps/'+app['id']+'/policies')
    if (len(policies)!=1 or policies[0].get('decision')!='non_identity' or policies[0].get('include')!=expected
            or policies[0].get('exclude') or policies[0].get('require')):
        raise ValueError('Policy read-back differs; route stays disabled')
    client.call('POST','workers/scripts/'+WORKER+'/subdomain',{'enabled':True,'previews_enabled':False})
    current.update(status='deployed',app_id=app['id'],url='https://'+scope['host']);atomic(claim,current)
    return {'status':'deployed','scheduled':False,'existing_app_changed':False}


def commission(state=setup.STATE):
    state=Path(state)
    claim_path=state/'request-commissioning.json'
    if claim_path.exists():
        raise ValueError('Commissioning request already claimed; inspect/reconcile instead of repeating')
    scope=json.loads((state/'scope.json').read_bytes()); deployed=json.loads((state/'provisioning.json').read_bytes())
    if deployed['status']!='deployed' or deployed['url']!='https://'+scope['host']:
        raise ValueError('Verified deployment required')
    token=load_secret(state/'persona-01.dpapi')
    if token['id']!=scope['token_id']:
        raise ValueError('Service token binding differs')
    url=deployed['url']+'/workloads/persona-01/commissioning'
    with requests.Session() as session:
        session.trust_env=False
        denied=session.get(url,timeout=30,allow_redirects=False)
        if denied.status_code not in (301,302,303,307,308,401,403) or MARKER in denied.text:
            raise ValueError('Unauthenticated request was not denied')
        claim={'status':'claimed_unknown','at_utc':datetime.now(timezone.utc).isoformat(),
               'app_id':deployed['app_id'],'token_id':scope['token_id'],'unauthenticated_status':denied.status_code,
               'scheduled':False,'model_activated':False}
        with claim_path.open('x',encoding='utf-8') as handle:json.dump(claim,handle)
        response=session.get(url,timeout=30,allow_redirects=False,
                              headers={'CF-Access-Client-Id':token['client_id'],'CF-Access-Client-Secret':token['client_secret']})
        claim.update(http_status=response.status_code)
        atomic(claim_path,claim)
        if response.status_code!=200 or MARKER not in response.text:
            raise ValueError('Machine request did not authenticate successfully')
        ray=response.headers.get('CF-Ray','').split('-')[0]
        if not re.fullmatch('[0-9a-fA-F]{16}',ray):
            raise ValueError('Native Cloudflare request ID unavailable')
        claim.update(status='request_verified_log_pending',ray_id=ray.lower())
        atomic(claim_path,claim)
    return {'status':'request_verified_log_pending','http_status':200,'scheduled':False}


def inspect_log(client,state=setup.STATE):
    state=Path(state);receipt=json.loads((state/'request-commissioning.json').read_bytes())
    now=datetime.now(timezone.utc)
    query=urlencode({'limit':100,'direction':'desc','since':(now-timedelta(hours=1)).isoformat(),'until':now.isoformat()})
    records=client.call('GET','access/logs/access_requests?'+query)
    found=[r for r in records if r.get('app_uid')==receipt['app_id'] and str(r.get('ray_id','')).lower()==receipt['ray_id']]
    if not found:
        return {'status':'awaiting_native_log','sample_rows':len(records),'scheduled':False}
    if len(found)!=1 or found[0].get('allowed') is not True:
        raise ValueError('Native request log is ambiguous or denied')
    atomic(state/'commissioning-native-log.json',found[0])
    return {'status':'native_log_captured','fields':sorted(found[0]),
            'has_user_id':bool(found[0].get('user_id')),'has_user_email':bool(found[0].get('user_email')),
            'scheduled':False,'ingested':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['inspect','deploy','commission','inspect-log'])
    args=parser.parse_args()
    try:
        if args.mode=='commission':result=commission()
        elif args.mode=='inspect-log':result=inspect_log(setup.api())
        else:
            scope=json.loads((setup.STATE/'scope.json').read_bytes())
            token=load_secret(setup.STATE/'persona-01.dpapi')
            result=provision(setup.api(),scope,token,deploy=args.mode=='deploy')
        print(json.dumps(result))
    except Exception as error:
        result={'status':'stopped','error_type':type(error).__name__,'scheduled':False}
        if hasattr(error,'status'):result['http_status']=error.status
        atomic(setup.STATE/'last-provision-status.json',result)
        print(json.dumps(result));raise SystemExit(1)
