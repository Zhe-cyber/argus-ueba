"""Read-only overview and operational snapshots for the isolated workspace."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo
from backend import event_store as store, collector_status
from workspace_next.queries import stamp, findings

PROVIDERS={'aws_cloudtrail':'AWS CloudTrail','cloudflare_access':'Cloudflare Access','github_events':'GitHub'}
STATES={'recent','attention','stale','unavailable','ended'}
MY=ZoneInfo('Asia/Kuala_Lumpur')


def activity_window(config,now,aws=False):
    """Outer eligibility window only; not evidence that an action is running."""
    try:
        start=config['actor_start' if aws else 'start']
        end=config['actor_end' if aws else 'end']
        first=datetime.fromisoformat(start).date(); last=datetime.fromisoformat(end).date()
        local=now.astimezone(MY)
        state=('not_started' if local.date()<first else 'ended' if local.date()>last
               else 'outside_hours' if not 8<=local.hour<20 else 'within_hours')
        return {'status':state,'start_date':first.isoformat(),'end_date':last.isoformat(),
                'timezone':'Asia/Kuala_Lumpur','from_hour':8,'until_hour':20}
    except (TypeError,KeyError,ValueError): return {'status':'unavailable'}


def workload_history(path,day):
    empty={'available':False,'day':day}
    try:
        with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=2) as con:
            rows=con.execute('SELECT day,status,COUNT(*) FROM actions WHERE day<=? GROUP BY day,status LIMIT 513',(day,)).fetchall()
        if len(rows)>512: return empty
        totals={'today':{},'prior_days':{}}
        for recorded,state,count in rows:
            if state not in collector_status.STATES or type(count) is not int: return empty
            datetime.fromisoformat(recorded).date()
            bucket=totals['today' if recorded==day else 'prior_days']
            bucket[state]=bucket.get(state,0)+count
        result={'available':True,'day':day}
        for period,states in totals.items():
            result[period]={'unresolved':sum(states.get(key,0) for key in ['claimed_unknown','api_ok_identity_pending']),
                            'missed':states.get('missed',0),'verified':states.get('provider_verified',0),
                            'pending_receipts':sum(states.get(key,0) for key in ['api_ok_activity_pending','api_ok_log_pending','response_error_log_pending','api_ok_audit_pending'])}
        return result
    except (OSError,sqlite3.Error,ValueError,TypeError): return empty


def read_snapshot(path):
    raw=collector_status.read_status(path) if path else None
    empty={'captured_at':None,'sources':{},'mode':'snapshot_unavailable'}
    if not raw:
        return empty
    try:
        captured=stamp(raw['captured_at']).isoformat()
        values=raw['sources']
        if not isinstance(values,dict): return empty
    except (KeyError,ValueError,TypeError):
        return empty
    result={}
    for provider in PROVIDERS:
        if provider not in values: continue
        source=values.get(provider,{})
        if not isinstance(source,dict): continue
        result[provider]={}
        for kind in ['collector','workload']:
            value=source.get(kind,{})
            if not isinstance(value,dict): continue
            state=value.get('status','unavailable')
            if state not in STATES: state='unavailable'
            try: checked=stamp(value['last_checked_at']).isoformat() if value.get('last_checked_at') else None
            except (ValueError,TypeError): checked=None; state='unavailable'
            entry={'status':state,'last_checked_at':checked}
            if checked:
                entry['age_seconds_at_capture']=max(0,int((stamp(captured)-stamp(checked)).total_seconds()))
            for key in ['unresolved','missed','pending_receipts']:
                if type(value.get(key)) is int and value[key]>=0: entry[key]=value[key]
            result[provider][kind]=entry
        window=source.get('activity_window',{})
        if isinstance(window,dict) and window.get('status') in {'outside_hours','within_hours','not_started','ended'}:
            # Recompute from declared dates at the capture timestamp; never trust a supplied label.
            result[provider]['activity_window']=activity_window({'start':window.get('start_date'),'end':window.get('end_date')},stamp(captured))
        history=source.get('workload_history',{})
        if isinstance(history,dict) and history.get('available') is True and history.get('day')==stamp(captured).astimezone(MY).date().isoformat():
            periods={}
            for period in ['today','prior_days']:
                period_values=history.get(period,{})
                if isinstance(period_values,dict) and all(type(period_values.get(k)) is int and period_values[k]>=0 for k in ['unresolved','missed','verified','pending_receipts']):
                    periods[period]={k:period_values[k] for k in ['unresolved','missed','verified','pending_receipts']}
            if len(periods)==2: result[provider]['workload_history']={'available':True,'day':history['day'],**periods}
        run=source.get('latest_run_status')
        if run in {'completed','attention_required','stopped','stopped_review_required','expired'}:
            result[provider]['latest_run_status']=run
    return {'captured_at':captured,'sources':result,'mode':'dated_snapshot'}


def connections(snapshot_path=None):
    snapshot=read_snapshot(snapshot_path)
    with store._db() as con:
        cur=store._cursor(con)
        cur.execute('''SELECT source,COUNT(*) AS event_count,
            COUNT(DISTINCT account_key) AS account_count FROM events GROUP BY source''')
        totals={row['source']:row for row in store._rows(cur)}
        cur.execute('SELECT source,timestamp,ingested_at FROM events ORDER BY id DESC LIMIT 10001')
        recent=store._rows(cur)
    latest={}; invalid={}
    for row in recent[:10000]:
        source=row['source']
        try:
            at=stamp(row['timestamp']).isoformat()
            latest[source]=max(at,latest.get(source,at))
        except (TypeError,ValueError): invalid[source]=invalid.get(source,0)+1
    rows=[]
    for source,title in PROVIDERS.items():
        counts=totals.get(source,{})
        checks=snapshot['sources'].get(source,{})
        if not counts and not checks: continue
        workload=dict(checks.get('workload',{'status':'unavailable','last_checked_at':None}))
        history=checks.get('workload_history',{'available':False})
        if (workload['status']=='attention' and checks.get('latest_run_status')=='attention_required'
                and history.get('available') and history['today']['unresolved']==0
                and history['today']['pending_receipts']==0 and history['today']['missed']==0
                and history['prior_days']['unresolved']>0):
            workload['attention_scope']='historical'
        rows.append({'source':source,'title':title,'event_count':counts.get('event_count',0),
                     'account_count':counts.get('account_count',0),
                     'latest_observed_in_scan':latest.get(source),
                     'invalid_timestamps_in_scan':invalid.get(source,0),
                     'collector':checks.get('collector',{'status':'unavailable','last_checked_at':None}),
                     'workload':workload,'activity_window':checks.get('activity_window',{'status':'unavailable'}),
                     'workload_history':history})
    return {'sources':rows,'captured_at':snapshot['captured_at'],'mode':snapshot['mode'],
            'event_scan_capped':len(recent)>10000,'scan_limit':10000,
            'coverage':'observed_activity_only_completeness_unknown','refresh_policy':'dated_copy_no_live_polling'}


def overview(snapshot_path=None):
    with store._db() as con:
        cur=store._cursor(con)
        cur.execute("SELECT alert_type,COUNT(*) AS n FROM alerts WHERE status='Open' GROUP BY alert_type")
        counts={row['alert_type']:row['n'] for row in store._rows(cur)}
        cur.execute("SELECT COUNT(*) AS n FROM analyst_cases WHERE status!='Closed'")
        active=dict(cur.fetchone())['n']
        cur.execute("SELECT id,title,owner,status,priority FROM analyst_cases WHERE status!='Closed' ORDER BY updated_at DESC,id DESC LIMIT 3")
        recent=store._rows(cur)
    from workspace_next.case_store import display_title
    for row in recent: row['display_title']=display_title(row['title'])
    checks=connections(snapshot_path)
    issues=sum(any(row[kind]['status'] in {'attention','stale'} for kind in ['collector','workload']) for row in checks['sources'])
    return {'open_security_findings':sum(counts.get(kind,0) for kind in ['rarity_spike','anomalous_behavior','ae_critical']),
            'open_observations':counts.get('new_user',0),'active_cases':active,
            'sources_needing_review_at_capture':issues,'operations_captured_at':checks['captured_at'],
            'recent_cases':recent,'recent_findings':findings(limit=5)['findings'],
            'scoring':'not_enabled_in_workspace_preview','mode':'isolated_copy'}


def capture(connected_dir,source_root,output):
    """Explicit local read; never runs a collector or retries workload actions."""
    import json
    now=datetime.now(timezone.utc)
    value={'captured_at':now.isoformat(),
           'sources':collector_status.summaries(connected_dir,source_root,now)}
    shared=Path(connected_dir).parent
    for provider,folder,aws in [('aws_cloudtrail',shared/'pilot-local-v1',True),
                               ('cloudflare_access',Path(source_root)/'data/live/cloudflare-workload-lab-v1',False),
                               ('github_events',Path(source_root)/'data/live/github-app-lab-v1',False)]:
        source=value['sources'][provider]
        config=collector_status.read_status(folder/('config.json' if aws else 'pilot-config.json'))
        source['activity_window']=activity_window(config,now,aws)
        ledger=shared/'persona-history-v1/ledger.db' if aws else folder/'machine-ledger.db'
        source['workload_history']=workload_history(ledger,now.astimezone(MY).date().isoformat())
        raw=collector_status.read_status(folder/('last_tick.json' if aws else 'last-pilot-status.json'))
        if isinstance(raw,dict): source['latest_run_status']=raw.get('status')
    Path(output).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    return {'captured':True,'sources':len(value['sources']),'live_actions':0}
