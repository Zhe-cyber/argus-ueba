"""Bounded evidence queries for the isolated analyst workspace.

Filters apply before page slicing. Scan caps are explicit, never full-coverage
claims. Timestamps are parsed to UTC before comparison/order, not sorted as text.
"""
from datetime import datetime, timezone
import json
import sqlite3
from backend import alert_store, event_store as store
from workspace_next import case_store as cases
from workspace_next.finding_context import context,object_value

from workspace_next import baseline_score
SCAN_LIMIT = 10000
ORIGINS = {'rarity_spike':'rule','anomalous_behavior':'rule',
           'ae_critical':'model','new_user':'observation','baseline_risk':'baseline'}
STATUSES = ('Open','Acknowledged','Resolved','False Positive')


def stamp(value):
    if not isinstance(value,str):
        raise ValueError('Timestamp must be text')
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return parsed.astimezone(timezone.utc)


def bounds(start,end):
    lo,hi=stamp(start) if start else None,stamp(end) if end else None
    if lo and hi and lo >= hi:
        raise ValueError('Start must be before end')
    return lo,hi


def _json(value):
    try:
        result=json.loads(value) if isinstance(value,str) else value
    except (ValueError,TypeError):
        return {}
    return result if isinstance(result,dict) else {}


def page(rows,limit,before):
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('limit must be 1–100')
    rows.sort(key=lambda r:(r['timestamp_utc'],r['id']),reverse=True)
    if before:
        if len(before)!=2:
            raise ValueError('Invalid cursor')
        key=(stamp(before[0]).isoformat(),int(before[1]))
        rows=[r for r in rows if (r['timestamp_utc'],r['id'])<key]
    more=len(rows)>limit
    output=rows[:limit]
    return output,([output[-1]['timestamp_utc'],str(output[-1]['id'])] if more else None),more


def _baseline(row):
    """Baseline {score,tier} for the finding's account on its MYT day (event time when known, else created_at)."""
    try:
        if row['alert_type']==baseline_score.ALERT_TYPE: day=datetime.strptime(row['details']['day'],'%Y-%m-%d').date()
        else: day=stamp(row.get('rule_event_time_utc') or row['created_at']).astimezone(baseline_score.MYT).date()
        return baseline_score.lookup(store.DB_PATH,row['user_id'],day)
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error): return {'tier':'Learning'}


def findings(limit=50,before=None,category='security',status='Open',provider=None,account=None,start=None,end=None,entity_context=None,triage=None,learning='include'):
    if learning not in {'include','exclude','only'}:
        raise ValueError('Invalid learning filter')
    if category not in {'security','observation','unverified','all'}:
        raise ValueError('Invalid category')
    if status not in {'All','Open','Acknowledged','Resolved','False Positive'}:
        raise ValueError('Invalid finding status')
    if entity_context not in {None,'','service_or_workload','other_or_unclassified'}:
        raise ValueError('Invalid entity context')
    if triage not in {None,'','review_first','automation_context','office_hours_context','infrastructure_context'}:
        raise ValueError('Invalid triage filter')
    lo,hi=bounds(start,end)
    clauses=[]; values=[]
    if status!='All': clauses.append('status='+store._PH); values.append(status)
    if account: clauses.append('user_id='+store._PH); values.append(account)
    where=' WHERE '+' AND '.join(clauses) if clauses else ''
    with store._db() as con:
        cur=store._cursor(con)
        cur.execute(f'SELECT * FROM alerts{where} ORDER BY id DESC LIMIT {store._PH}',(*values,SCAN_LIMIT+1))
        raw=store._rows(cur)  # rule and baseline findings (alert_type='baseline_risk', written by the backend scorer)
        cur.execute('SELECT case_id,target FROM analyst_case_links WHERE kind=\'finding\'')
        linked={}
        for item in store._rows(cur): linked.setdefault(item['target'],[]).append(item['case_id'])
    rows=[]; invalid=0
    directory=store.account_directory()
    event_cache={}
    triage_counts={}; learning_count=0
    for row in raw[:SCAN_LIMIT]:
        row['origin']=ORIGINS.get(row['alert_type'],'unverified')
        wanted={'security':{'rule','model','baseline'},'observation':{'observation'},'unverified':{'unverified'},'all':set(ORIGINS.values())|{'unverified'}}[category]
        if row['origin'] not in wanted: continue
        row['details']=_json(row['details'])
        row['provider']=row['details'].get('source') or directory.get(row['user_id'],{}).get('source')
        if provider and row['provider']!=provider: continue
        try: when=stamp(row['created_at'])
        except (ValueError,TypeError): invalid+=1; continue
        if lo and when<lo or hi and when>=hi: continue
        row.update(context(row,directory,event_cache))
        row['baseline']=_baseline(row)
        row['learning_period']=row['baseline'].get('tier')=='Learning'
        if entity_context and row['entity_context']!=entity_context: continue
        learning_count+=row['learning_period']
        if learning=='exclude' and row['learning_period'] or learning=='only' and not row['learning_period']: continue
        triage_counts[row['triage']]=triage_counts.get(row['triage'],0)+1
        if triage and row['triage']!=triage: continue
        row['timestamp_utc']=when.isoformat()
        row['case_ids']=sorted(linked.get(str(row['id']),[]))
        rows.append(row)
    total=len(rows)
    output,cursor,more=page(rows,limit,before)
    # Infrastructure last, then score desc, then newest (stable within the page; paging itself stays by time).
    output.sort(key=lambda r:(r['infrastructure'],-(r['baseline'].get('score') or -1),-stamp(r['created_at']).timestamp()))
    return {'findings':output,'next_cursor':cursor,'has_more':more,
            'matched_in_scan':total,'scan_capped':len(raw)>SCAN_LIMIT,
            'invalid_timestamps':invalid,'scan_limit':SCAN_LIMIT,'triage_counts':triage_counts,'learning_count':learning_count}


def finding(finding_id):
    with store._db() as con:
        cur=store._cursor(con)
        cur.execute(f'SELECT * FROM alerts WHERE id={store._PH}',(finding_id,))
        row=cur.fetchone()
        if row is None: raise cases.CaseNotFound('Finding not found')
        row=dict(row); row['details']=_json(row['details'])
        row['origin']=ORIGINS.get(row['alert_type'],'unverified')
        row['trigger_evidence']='baseline_account_day' if row['origin']=='baseline' else 'not_bound_legacy_signal'
        directory = store.account_directory()
        row.update(context(row, directory=directory))
        row['baseline']=_baseline(row)
        account = directory.get(row['user_id'])
        row['diagnostic_subject'] = ({k: account[k] for k in ('source', 'source_account_id', 'account_key')}
                                     if account else None)
        return row


def timeline(case_id,limit=50,before=None,provider=None,start=None,end=None):
    case=cases.get(case_id); lo,hi=bounds(start,end)
    accounts={r['target'] for r in case['links'] if r['kind']=='account'}
    direct={int(r['target']) for r in case['links'] if r['kind']=='event'}
    mappings=[]
    for link in case['links']:
        if link['kind']!='person': continue
        snap=link['snapshot']
        # Current revocation is surfaced, but never erases the historical scope.
        from backend import identity_links
        try:
            current={r['id']:r['effective_status'] for r in identity_links.person_view(link['target'])['links']}
        except (LookupError,ValueError): current={}
        for approved in snap['approved_links']:
            accounts.add(approved['account_key'])
            mappings.append({'person_id':link['target'],'link_id':approved['id'],
                             'account_key':approved['account_key'],'status_at_link':'approved',
                             'current_status':current.get(approved['id'],'unavailable')})
    clauses=[]; values=[]
    if accounts:
        clauses.append('account_key IN ('+','.join([store._PH]*len(accounts))+')'); values.extend(sorted(accounts))
    if direct:
        clauses.append('id IN ('+','.join([store._PH]*len(direct))+')'); values.extend(sorted(direct))
    raw=[]
    if clauses:
        with store._db() as con:
            cur=store._cursor(con)
            cur.execute(f'''SELECT id,timestamp,source,action,resource,ip_address,event_id,
                source_account_id,payload_digest,account_key FROM events WHERE
                ({' OR '.join(clauses)}) ORDER BY id DESC LIMIT {store._PH}''',(*values,SCAN_LIMIT+1))
            raw=store._rows(cur)
    rows=[]; invalid=0
    for row in raw[:SCAN_LIMIT]:
        if provider and row['source']!=provider: continue
        try: when=stamp(row['timestamp'])
        except (ValueError,TypeError): invalid+=1; continue
        if lo and when<lo or hi and when>=hi: continue
        row['timestamp_utc']=when.isoformat()
        row['evidence_relation']='linked_evidence' if row['id'] in direct else 'related_account_activity'
        row['resource_value']=object_value(row['resource'])
        rows.append(row)
    output,cursor,more=page(rows,limit,before)
    return {'events':output,'next_cursor':cursor,'has_more':more,'scan_capped':len(raw)>SCAN_LIMIT,
            'scan_limit':SCAN_LIMIT,'invalid_timestamps':invalid,'mapping_provenance':mappings,
            'coverage':'observed_activity_only_completeness_unknown','case_version':case['version']}


def set_status(finding_id,status,analyst,reason):
    """Analyst disposition of one finding (rule or baseline). Audited in workspace_finding_audit."""
    if status not in STATUSES: raise ValueError('Status must be one of: '+', '.join(STATUSES))
    analyst=(analyst or '').strip(); reason=(reason or '').strip()
    if not analyst: raise ValueError('Analyst name is required')
    if not reason: raise ValueError('Reason is required')
    if len(analyst)>200 or len(reason)>2000: raise ValueError('Analyst or reason is too long')
    now=datetime.now(timezone.utc).isoformat()
    terminal=status in ('Resolved','False Positive')
    with store.transaction():
        with store._db() as con:
            cur=store._cursor(con)
            cur.execute(cases.AUDIT_DDL)
            cur.execute(f'SELECT status,alert_type,details FROM alerts WHERE id={store._PH}',(finding_id,))
            row=cur.fetchone()
            if row is None: raise cases.CaseNotFound('Finding not found')
            row=dict(row)
            alert_store.update_status(finding_id,status)  # shares this transaction's connection
            if row['alert_type']==baseline_score.ALERT_TYPE:
                # the backend scorer never overrides an analyst; it only auto-resolves untouched Open findings
                details=_json(row['details']); details.pop('auto_resolved',None); details['analyst_touched']=True
                cur.execute(f'UPDATE alerts SET details={store._PH} WHERE id={store._PH}',(json.dumps(details),finding_id))
            cur.execute(f'INSERT INTO workspace_finding_audit (finding_id,old_status,new_status,analyst,reason,at_utc) VALUES ({",".join([store._PH]*6)})',
                        (finding_id,row['status'],status,analyst,reason,now))
    return {'id':finding_id,'status':status,'resolved_at':now if terminal else None,'previous_status':row['status']}
