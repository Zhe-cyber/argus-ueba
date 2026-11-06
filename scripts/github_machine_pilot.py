"""Finite one-bot workload and native activity collection; no LLM/model calls."""
import argparse
import base64
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

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import github_lab_app as app, github_lab_workload as lab, local_pilot as pilot
from scripts.collect_live import LocalBackend
from backend.github_activity import receipt_id

START='2026-10-31';END='2026-11-13';RECONCILE_END='2026-11-14'
MY=ZoneInfo('Asia/Kuala_Lumpur')
WINDOWS={1:(8,11),2:(10,17),3:(11,17),4:(16,19),5:(8,10),6:(12,16)}
FILES=['scripts/github_machine_pilot.py','scripts/github_lab_app.py','scripts/github_lab_workload.py',
       'scripts/collect_live.py','scripts/local_pilot.py','backend/github_activity.py',
       'specs/W35-github-controlled-machine-pilot.md']


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def state():return app.STATE_DIR
def pins():return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in FILES}


def plan(day):
    day=datetime.fromisoformat(day).date().isoformat()
    if not START<=day<=END:return []
    profiles=[f'persona-{n:02d}' for n in WINDOWS]
    count=2+int(digest([20261031,day,'count']),16)%5
    chosen=sorted(profiles,key=lambda p:(digest([20261031,day,p,'active']),p))[:count]
    rows=[]
    for profile in chosen:
        lo,hi=WINDOWS[int(profile[-2:])]
        due=datetime.combine(datetime.fromisoformat(day).date(),daytime(lo),MY)+timedelta(minutes=int(digest([20261031,day,profile,'time']),16)%((hi-lo)*60-45))
        rows.append({'id':digest(['github-machine-v1',day,profile]),'day':day,'profile':profile,
                     'due':due.isoformat(),'until':(due+timedelta(minutes=45)).isoformat(),
                     'path':f'workloads/{profile}/{day}.json'})
    return sorted(rows,key=lambda r:(r['due'],r['profile']))


def configure():
    path=state()/'pilot-config.json'
    if path.exists() or (state()/'machine-ledger.db').exists():raise ValueError('Existing pilot state requires review')
    proof=json.loads(lab.RECEIPT.read_bytes())
    installed=json.loads((state()/'status.json').read_bytes())
    if (proof.get('status')!='ingested' or proof.get('collection_authority')!='repository_activity_only'
            or proof.get('repo')!=app.REPO or installed.get('status')!='installed_verified'
            or installed.get('repo_id')!=proof.get('repo_id')):raise ValueError('Ingested activity commissioning required')
    cfg={'schema':'github_controlled_machine_pilot_v1','repo':app.REPO,'repo_id':proof['repo_id'],
         'bot_actor_id':proof['bot_actor_id'],'owner_namespace':proof['source_account_id'],'slug':proof['slug'],
         'installation_id':installed['installation_id'],
         'start':START,'end':END,'reconcile_end':RECONCILE_END,'max_writes_day':6,'max_writes_pilot':84,
         'model_activated':False,'commission_sha256':hashlib.sha256(lab.RECEIPT.read_bytes()).hexdigest(),
         'source_sha256':pins()}
    cfg['scope_sha256']=digest({k:v for k,v in cfg.items() if k not in ['source_sha256']})
    validate(cfg)
    with path.open('xb') as out:out.write(json.dumps(cfg,sort_keys=True).encode());out.flush();os.fsync(out.fileno())
    with database() as db:bind_scope(db,cfg)
    return {'status':'configured','start':START,'end':END,'native_bot_accounts':1,'profile_templates':6,'scheduled':False}


def validate(cfg):
    scope={k:v for k,v in cfg.items() if k not in ['scope_sha256','source_sha256']}
    if (cfg.get('schema')!='github_controlled_machine_pilot_v1' or cfg.get('repo')!=app.REPO
            or cfg.get('source_sha256')!=pins() or cfg.get('scope_sha256')!=digest(scope)
            or cfg.get('start')!=START or cfg.get('end')!=END or cfg.get('reconcile_end')!=RECONCILE_END
            or cfg.get('max_writes_day')!=6 or cfg.get('max_writes_pilot')!=84 or cfg.get('model_activated') is not False
            or any(type(cfg.get(key)) is not int or cfg[key]<=0 for key in ['repo_id','bot_actor_id','installation_id'])
            or not re.fullmatch(r'github-owner:[0-9]+',cfg.get('owner_namespace',''))
            or cfg.get('commission_sha256')!=hashlib.sha256(lab.RECEIPT.read_bytes()).hexdigest()):
        raise ValueError('GitHub pilot source/scope differs')


@contextmanager
def database():
    db=sqlite3.connect(state()/'machine-ledger.db',timeout=10);db.row_factory=sqlite3.Row
    db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE IF NOT EXISTS scope(id INTEGER PRIMARY KEY CHECK(id=1),digest TEXT NOT NULL)')
    db.execute('''CREATE TABLE IF NOT EXISTS actions(action_id TEXT PRIMARY KEY,day TEXT,profile TEXT,path TEXT,
                  status TEXT,claimed_at TEXT,commit_sha TEXT,native_activity_id INTEGER,verified_at TEXT)''')
    try:
        with db:yield db
    finally:db.close()


def bind_scope(db,cfg):
    old=db.execute('SELECT digest FROM scope WHERE id=1').fetchone()
    if old is None:db.execute('INSERT INTO scope VALUES(1,?)',(cfg['scope_sha256'],))
    elif old[0]!=cfg['scope_sha256']:raise ValueError('Ledger scope differs')


def context(cfg):
    status,token=lab.context()
    if (status.get('repo_id')!=cfg['repo_id'] or status.get('slug')!=cfg['slug']
            or status.get('installation_id')!=cfg['installation_id']):raise ValueError('App scope differs')
    meta=app.api('GET','/repos/'+app.REPO,token)
    if (meta.get('id')!=cfg['repo_id'] or meta.get('full_name')!=app.REPO or meta.get('private') is not True
            or 'github-owner:'+str(meta.get('owner',{}).get('id'))!=cfg['owner_namespace']):raise ValueError('Repository scope differs')
    return token


def archive_activity(raw):
    payload=json.dumps(raw,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    directory=state()/'native-activity';directory.mkdir(exist_ok=True)
    path=directory/(hashlib.sha256(payload).hexdigest()+'.json')
    try:
        with path.open('xb') as out:out.write(payload);out.flush();os.fsync(out.fileno())
    except FileExistsError:
        if path.read_bytes()!=payload:raise ValueError('Native archive conflict')


def reconcile(cfg,token,backend,now):
    events=app.api('GET','/repos/'+app.REPO+'/activity',token)
    if not isinstance(events,list) or len(events)>30:raise ValueError('Unexpected bounded activity response')
    inserted=verified=0
    with database() as db:pending=[dict(r) for r in db.execute("SELECT * FROM actions WHERE status IN ('api_ok_identity_pending','api_ok_activity_pending') LIMIT 20")]
    for row in pending:
        if row['status']=='api_ok_identity_pending':
            commit=app.api('GET','/repos/'+app.REPO+'/commits/'+row['commit_sha'],token)
            if lab.check_commit(commit,row['commit_sha'],cfg['slug'])!=cfg['bot_actor_id']:raise ValueError('Wrong native Bot')
            with database() as db:db.execute("UPDATE actions SET status='api_ok_activity_pending' WHERE action_id=?",(row['action_id'],))
        matches=[e for e in events if lab.matches_activity(e,{'bot_actor_id':cfg['bot_actor_id'],'commit_sha':row['commit_sha']})]
        if len(matches)>1:raise ValueError('Ambiguous native push evidence')
        if not matches:continue
        raw=matches[0];receipt_id(cfg['repo_id'],raw.get('id'));archive_activity(raw)
        duplicate=backend.post_github_activity(cfg['owner_namespace'],app.REPO,cfg['repo_id'],raw)
        if duplicate is None:continue
        with database() as db:db.execute("UPDATE actions SET status='provider_verified',native_activity_id=?,verified_at=? WHERE action_id=?",(raw['id'],now.isoformat(),row['action_id']))
        inserted+=not duplicate;verified+=1
    return {'inserted':inserted,'newly_provider_verified':verified,'activity_cap_hit':len(events)==30,'bounded_sample':True}


def claim(cfg,item,now):
    local=now.astimezone(MY)
    if local<datetime.fromisoformat(item['due']):return None
    missed=local>=datetime.fromisoformat(item['until'])
    with database() as db:
        if db.execute('SELECT 1 FROM actions WHERE action_id=?',(item['id'],)).fetchone():return None
        if not missed:
            if db.execute("SELECT COUNT(*) FROM actions WHERE status IN ('claimed_unknown','api_ok_identity_pending')").fetchone()[0]:return None
            if db.execute("SELECT COUNT(*) FROM actions WHERE status!='missed'").fetchone()[0]>=84:raise ValueError('Pilot write cap')
            if db.execute("SELECT COUNT(*) FROM actions WHERE day=? AND status!='missed'",(item['day'],)).fetchone()[0]>=6:raise ValueError('Daily write cap')
        db.execute('INSERT INTO actions(action_id,day,profile,path,status,claimed_at) VALUES(?,?,?,?,?,?)',
                   (item['id'],item['day'],item['profile'],item['path'],'missed' if missed else 'claimed_unknown',now.isoformat()))
    return 'missed' if missed else 'claimed_unknown'


def perform(cfg,item,token):
    if item not in plan(item['day']):raise ValueError('Write outside the frozen plan')
    with database() as db:row=db.execute('SELECT * FROM actions WHERE action_id=?',(item['id'],)).fetchone()
    if (row is None or row['status']!='claimed_unknown' or row['path']!=item['path']
            or row['profile']!=item['profile'] or row['day']!=item['day']):raise ValueError('Durable matching claim required')
    payload={'provenance':'controlled_machine_workload','independent_human_user':False,
             'action_id':item['id'],'day':item['day'],'profile_template':item['profile']}
    body={'message':'[Argus controlled machine workload] '+item['id'],
          'content':base64.b64encode((json.dumps(payload,sort_keys=True)+'\n').encode()).decode()}
    result=app.api('PUT','/repos/'+app.REPO+'/contents/'+item['path'],token,body)
    sha=result.get('commit',{}).get('sha')
    if not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('Unknown commit response; do not retry')
    with database() as db:db.execute("UPDATE actions SET status='api_ok_identity_pending',commit_sha=? WHERE action_id=?",(sha,item['id']))


def tick(now=None):
    now=now or datetime.now(timezone.utc);day=now.astimezone(MY).date().isoformat()
    if day>RECONCILE_END:return {'status':'expired','new_actions':0,'model_activated':False}
    cfg=json.loads((state()/'pilot-config.json').read_bytes());validate(cfg)
    pilot_cfg=json.loads(Path(r'C:/Users/yyzhe/.codex/worktrees/argus-cloud-live/fyp-ueba/data/live/pilot-local-v1/config.json').read_bytes())
    pilot.validate(pilot_cfg);pilot.health(pilot_cfg)
    backend=LocalBackend(pilot_cfg['api']);backend.preflight()
    with pilot.lock(state()/'machine-pilot.lock'):
        with database() as db:bind_scope(db,cfg)
        token=context(cfg);collected=reconcile(cfg,token,backend,now);new=0
        slots=[];cursor=datetime.fromisoformat(START).date();last=min(day,END)
        while cursor.isoformat()<=last:
            slots.extend(plan(cursor.isoformat()));cursor+=timedelta(days=1)
        for item in slots:
            outcome=claim(cfg,item,now)
            if outcome!='claimed_unknown':continue
            perform(cfg,item,token);new+=1
            # Identity gate before another write; a verified push may arrive later.
            extra=reconcile(cfg,token,backend,now)
            for key in ['inserted','newly_provider_verified']:collected[key]+=extra[key]
            collected['activity_cap_hit']|=extra['activity_cap_hit']
        with database() as db:states=dict(db.execute('SELECT status,COUNT(*) FROM actions GROUP BY status').fetchall())
    return {'status':'attention_required' if states.get('claimed_unknown') or states.get('api_ok_identity_pending') else 'completed',
            'at_utc':now.isoformat(),'new_actions':new,'action_states':states,'collection':collected,
            'provenance':'controlled_machine_workload_one_bot','model_activated':False}


def journal(result):
    app.atomic(state()/'last-pilot-status.json',result)
    with (state()/'pilot-attempts.jsonl').open('a',encoding='utf-8') as out:
        out.write(json.dumps(result,sort_keys=True)+'\n');out.flush();os.fsync(out.fileno())


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['configure','tick']);args=parser.parse_args()
    try:result=configure() if args.mode=='configure' else tick()
    except Exception as error:
        result={'status':'stopped_review_required','at_utc':datetime.now(timezone.utc).isoformat(),
                'error_type':type(error).__name__,'model_activated':False}
        journal(result)
        if sys.stdout is not None:print(json.dumps(result))
        return 1
    journal(result)
    if sys.stdout is not None:print(json.dumps(result))
    return 1 if result.get('status')=='attention_required' else 0


if __name__=='__main__':raise SystemExit(main())
