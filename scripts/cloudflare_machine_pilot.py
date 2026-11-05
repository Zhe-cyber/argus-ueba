"""Bounded six-profile machine traffic and exact native-log ingestion.

Separate from the frozen AWS study. One request/profile/day, no backfill or
retry of claimed actions. No model activation, human identity or forged logs.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone, time as daytime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from zoneinfo import ZoneInfo

import requests

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import cloudflare_lab_setup as setup
from scripts.github_lab_app import atomic,load_secret,save_secret
from scripts.collect_live import LocalBackend
from scripts.local_pilot import lock

MY=ZoneInfo('Asia/Kuala_Lumpur')
START='2026-10-30';END='2026-11-13';RECONCILE_END='2026-11-14'
WINDOWS={1:(8,11),2:(10,17),3:(11,17),4:(16,19),5:(8,10),6:(12,16)}
SOURCE_FILES=['scripts/cloudflare_machine_pilot.py','scripts/cloudflare_lab_setup.py',
              'scripts/setup_cloudflare.py','scripts/github_lab_app.py','scripts/collect_live.py','scripts/local_pilot.py',
              'specs/W32-cloudflare-controlled-machine-pilot.md']


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def plan(day):
    day=datetime.fromisoformat(day).date().isoformat()
    if not START<=day<=END:return []
    result=[]
    for n,(lo,hi) in WINDOWS.items():
        actor=f'persona-{n:02d}';seed=int(digest([20261030,day,actor]),16)
        due=datetime.combine(datetime.fromisoformat(day).date(),daytime(lo),MY)+timedelta(minutes=seed%((hi-lo)*60-45))
        result.append({'id':digest(['cf-machine-v1',day,actor]),'day':day,'persona':actor,
                       'due':due.isoformat(),'until':(due+timedelta(minutes=45)).isoformat()})
    return result


def pin_config(config):
    config['source_sha256']={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in SOURCE_FILES}
    config['scope_sha256']=digest({k:config[k] for k in ['account','app_id','host','tokens']})
    return config


def configure():
    if (setup.STATE/'pilot-config.json').exists():raise ValueError('Pilot already configured')
    proof=json.loads((setup.STATE/'ingestion-receipt.json').read_bytes())
    if proof['status']!='ingested' or proof['account_kind']!='service_token':raise ValueError('Commissioning round-trip required')
    client=setup.api();scope=json.loads((setup.STATE/'scope.json').read_bytes())
    deployed=json.loads((setup.STATE/'provisioning.json').read_bytes())
    policy=client.call('GET','access/apps/'+deployed['app_id']+'/policies')
    expected=[{'service_token':{'token_id':scope['token_id']}}]
    if len(policy)!=1 or policy[0].get('decision')!='non_identity' or policy[0].get('include')!=expected:
        raise ValueError('Initial exact-token policy differs')
    attempt=setup.STATE/'expansion-attempt.json'
    if attempt.exists():raise ValueError('Previous expansion requires inspection')
    all_tokens=client.all('access/service_tokens')
    if any(t.get('name','').startswith('argus-machine-lab-persona-') and t.get('id')!=scope['token_id'] for t in all_tokens):
        raise ValueError('Unexpected existing machine-lab tokens')
    atomic(attempt,{'status':'started','scheduled':False})
    inventory={'persona-01':{'id':scope['token_id'],'client_id':load_secret(setup.STATE/'persona-01.dpapi')['client_id']}}
    for n in range(2,7):
        actor=f'persona-{n:02d}';path=setup.STATE/(actor+'.dpapi')
        token=client.call('POST','access/service_tokens',{'name':'argus-machine-lab-'+actor,
              'duration':str(int((setup.EXPIRY-datetime.now(timezone.utc)).total_seconds()))+'s'})
        save_secret(path,token)
        inventory[actor]={'id':token['id'],'client_id':token['client_id']}
        atomic(attempt,{'status':'tokens_created','actors_created':list(inventory),'scheduled':False})
    includes=[{'service_token':{'token_id':inventory[p]['id']}} for p in sorted(inventory)]
    body={'name':'Exact six lab machine tokens only','decision':'non_identity','include':includes}
    client.call('PUT','access/apps/'+deployed['app_id']+'/policies/'+policy[0]['id'],body)
    readback=client.call('GET','access/apps/'+deployed['app_id']+'/policies')
    if (len(readback)!=1 or readback[0].get('decision')!='non_identity'
            or sorted(x['service_token']['token_id'] for x in readback[0].get('include',[]))!=sorted(t['id'] for t in inventory.values())
            or readback[0].get('exclude') or readback[0].get('require')):raise ValueError('Expanded policy read-back differs')
    cfg=pin_config({'schema':'cf_controlled_machine_pilot_v1','account':scope['account'],'app_id':deployed['app_id'],
         'host':scope['host'],'tokens':inventory,'start':START,'end':END,'reconcile_end':RECONCILE_END,
         'requests_per_profile_day':1,'max_workload_calls_day':6,'max_workload_calls_pilot':90,
         'provenance':'controlled_machine_workload_not_human','model_activated':False})
    atomic(setup.STATE/'pilot-config.json',cfg)
    with database() as db:pass
    atomic(attempt,{'status':'configured','profiles':6,'scheduled':False})
    return {'status':'configured','profiles':6,'workload_requests_per_day':6,'scheduled':False}


@contextmanager
def database():
    db=sqlite3.connect(setup.STATE/'machine-ledger.db',timeout=10)
    db.execute('''CREATE TABLE IF NOT EXISTS actions(action_id TEXT PRIMARY KEY,day TEXT,persona TEXT,
                   status TEXT,claimed_at TEXT,ray_id TEXT,http_status INTEGER,verified_at TEXT)''')
    db.execute('CREATE TABLE IF NOT EXISTS scope(id INTEGER PRIMARY KEY CHECK(id=1),digest TEXT NOT NULL)')
    try:
        with db:yield db
    finally:db.close()


def validate(cfg):
    if (cfg.get('schema')!='cf_controlled_machine_pilot_v1' or cfg.get('start')!=START or cfg.get('end')!=END
            or cfg.get('reconcile_end')!=RECONCILE_END or cfg.get('model_activated') is not False
            or not re.fullmatch(r'argus-machine-lab\.[a-z0-9-]+\.workers\.dev',cfg.get('host',''))
            or set(cfg.get('tokens',{}))!={f'persona-{n:02d}' for n in range(1,7)}
            or cfg.get('scope_sha256')!=digest({k:cfg[k] for k in ['account','app_id','host','tokens']})
            or cfg.get('source_sha256')!={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in SOURCE_FILES}):
        raise ValueError('Pilot scope/source binding differs')


def collect(cfg,backend,now):
    from urllib.parse import urlencode
    query=urlencode({'limit':100,'direction':'desc','since':(now-timedelta(hours=24)).isoformat(),'until':now.isoformat()})
    records=setup.api().call('GET','access/logs/access_requests?'+query)
    clients={v['client_id'] for v in cfg['tokens'].values()};inserted=0;verified=0
    for row in records:
        if (row.get('app_uid')!=cfg['app_id'] or row.get('connection')!='nonidentity'
                or row.get('user_email') not in clients or type(row.get('allowed')) is not bool
                or not row.get('ray_id') or not row.get('created_at')):continue
        duplicate=backend.post('cloudflare_access',cfg['account'],row,row['ray_id'])
        if duplicate is None:continue
        inserted+=not duplicate
        with database() as db:
            cur=db.execute("UPDATE actions SET status='provider_verified',verified_at=? WHERE ray_id=? AND status IN ('api_ok_log_pending','response_error_log_pending')",
                           (now.isoformat(),row['ray_id']))
            verified+=cur.rowcount
    return {'inserted':inserted,'newly_provider_verified':verified,'bounded_sample':True}


def tick(now=None):
    now=now or datetime.now(timezone.utc)
    cfg=json.loads((setup.STATE/'pilot-config.json').read_bytes());validate(cfg)
    local=now.astimezone(MY);day=local.date().isoformat()
    if day>RECONCILE_END:return {'status':'expired','new_actions':0,'model_activated':False}
    backend=LocalBackend('http://127.0.0.1:8013');backend.preflight()
    with lock(setup.STATE/'machine-pilot.lock'):
        with database() as db:
            row=db.execute('SELECT digest FROM scope WHERE id=1').fetchone()
            if row is None:db.execute('INSERT INTO scope VALUES(1,?)',(cfg['scope_sha256'],))
            elif row[0]!=cfg['scope_sha256']:raise ValueError('Ledger scope differs')
            prior_unknown=db.execute("SELECT COUNT(*) FROM actions WHERE status='claimed_unknown'").fetchone()[0]
        new_actions=0
        for item in plan(day):
            due=datetime.fromisoformat(item['due']);until=datetime.fromisoformat(item['until'])
            if local<due:continue
            with database() as db:
                if db.execute('SELECT 1 FROM actions WHERE action_id=?',(item['id'],)).fetchone():continue
                missed=local>=until
                if not missed:
                    if db.execute("SELECT COUNT(*) FROM actions WHERE status!='missed'").fetchone()[0]>=90:raise ValueError('Pilot call cap')
                    if db.execute("SELECT COUNT(*) FROM actions WHERE day=? AND status!='missed'",(day,)).fetchone()[0]>=6:raise ValueError('Daily call cap')
                db.execute('INSERT INTO actions(action_id,day,persona,status,claimed_at) VALUES(?,?,?,?,?)',
                           (item['id'],day,item['persona'],'missed' if missed else 'claimed_unknown',now.isoformat()))
            if missed:continue
            token=load_secret(setup.STATE/(item['persona']+'.dpapi'))
            if token['id']!=cfg['tokens'][item['persona']]['id'] or token['client_id']!=cfg['tokens'][item['persona']]['client_id']:
                raise ValueError('Credential scope differs; existing claim remains unknown')
            url='https://'+cfg['host']+'/workloads/'+item['persona']+'/'+item['id'][:24]
            with requests.Session() as session:
                session.trust_env=False
                response=session.get(url,headers={'CF-Access-Client-Id':token['client_id'],'CF-Access-Client-Secret':token['client_secret']},
                                     timeout=25,allow_redirects=False)
            ray=response.headers.get('CF-Ray','').split('-')[0].lower()
            if not re.fullmatch('[0-9a-f]{16}',ray):raise ValueError('Native ray ID missing; no retry')
            status='api_ok_log_pending' if response.status_code==200 and 'Argus machine workload: authenticated' in response.text else 'response_error_log_pending'
            with database() as db:db.execute('UPDATE actions SET status=?,ray_id=?,http_status=? WHERE action_id=?',
                                            (status,ray,response.status_code,item['id']))
            new_actions+=1
        collected=collect(cfg,backend,now)
        with database() as db:states=dict(db.execute('SELECT status,COUNT(*) FROM actions GROUP BY status').fetchall())
    # Old uncertain claims remain evidence gaps; they do not mean this tick failed.
    # Exceptions still stop the tick and exit nonzero, without retrying the claim.
    new_unknown=max(0,states.get('claimed_unknown',0)-prior_unknown)
    return {'status':'attention_required' if new_unknown else 'completed',
            'new_unknown':new_unknown,'historical_unknown':prior_unknown,
            'at_utc':now.isoformat(),'new_actions':new_actions,'action_states':states,
            'collection':collected,'model_activated':False,'provenance':'controlled_machine_workload'}


def journal(result):
    atomic(setup.STATE/'last-pilot-status.json',result)
    with (setup.STATE/'pilot-attempts.jsonl').open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(result,sort_keys=True)+'\n');stream.flush();os.fsync(stream.fileno())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['configure','tick']);args=parser.parse_args()
    try:
        result=configure() if args.mode=='configure' else tick()
        journal(result)
        if sys.stdout is not None:print(json.dumps(result))
        if result.get('status')=='attention_required':raise SystemExit(1)
    except Exception as error:
        result={'status':'stopped','at_utc':datetime.now(timezone.utc).isoformat(),
                'error_type':type(error).__name__,'model_activated':False}
        journal(result)
        if sys.stdout is not None:print(json.dumps(result))
        raise SystemExit(1)
