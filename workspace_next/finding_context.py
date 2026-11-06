"""Display context only: never changes recorded detector severity or features."""
import ast
from datetime import datetime, timezone
import json
import re
from zoneinfo import ZoneInfo
from backend import event_store as store

RULE_WINDOW='Mon–Fri 07:00–19:00 UTC = 15:00–03:00 next day MYT (UTC weekends outside window)'
# Display-only triage context. The detector, its UTC window and the recorded severity are unchanged.
# ponytail: one tenant time zone and office-hours constant; make these per-tenant settings when multi-tenancy returns.
TENANT_TZ=ZoneInfo('Asia/Kuala_Lumpur'); OFFICE_HOURS=(8,18)
TRIAGE_LABELS={'review_first':'Review first',
               'automation_context':'Context: automation or service account',
               'office_hours_context':'Context: inside Malaysian office hours'}


def local_time(event_at):
    if not event_at: return None,None
    local=event_at.astimezone(TENANT_TZ)
    return local.isoformat(),local.weekday()<5 and OFFICE_HOURS[0]<=local.hour<OFFICE_HOURS[1]


def triage(alert_type,entity_context,in_office_hours):
    if entity_context=='service_or_workload': return 'automation_context'
    if alert_type=='anomalous_behavior' and in_office_hours: return 'office_hours_context'
    return 'review_first'


def object_value(value):
    if not isinstance(value,str) or len(value)>16384: return value
    try: result=json.loads(value)
    except (ValueError,TypeError):
        try: result=ast.literal_eval(value)
        except (ValueError,SyntaxError,RecursionError,MemoryError): return value
    return result if isinstance(result,(dict,list)) else value


def stamp(value):
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (ValueError,TypeError,AttributeError): return None


def context(row,directory=None,event_cache=None):
    directory=store.account_directory() if directory is None else directory
    event_cache={} if event_cache is None else event_cache
    account=directory.get(row['user_id'])
    details=object_value(row.get('details'))
    details=details if isinstance(details,dict) else {}
    label=(account['account_label'] if account else row['user_id']) or 'Account unavailable'
    result={'account_label':label,'account_kind':account.get('account_kind') if account else 'unclassified',
            'entity_context':'other_or_unclassified','history_context':'unavailable',
            'prior_observed_active_days':None,'rule_window':None}
    if account:
        if account.get('account_kind') in {'service_token','service','bot'}:
            result['entity_context']='service_or_workload'
        if row['user_id'] not in event_cache:
            with store._db() as con:
                cur=store._cursor(con)
                cur.execute(f'SELECT timestamp,ingested_at,metadata FROM events WHERE account_key={store._PH} ORDER BY id LIMIT 10001',(row['user_id'],))
                event_cache[row['user_id']]=store._rows(cur)
        events=event_cache[row['user_id']]
        at=stamp(row.get('created_at')); prior=set()
        for event in events[:10000]:
            metadata=object_value(event['metadata'])
            if isinstance(metadata,dict):
                identity=metadata.get('userIdentity',{})
                if isinstance(identity,dict):
                    session=identity.get('sessionContext',{})
                    issuer=session.get('sessionIssuer',{}) if isinstance(session,dict) else {}
                    arn=issuer.get('arn','') if isinstance(issuer,dict) else ''
                    if ':role/aws-service-role/' in arn or re.fullmatch(r'arn:aws:iam::[0-9]{12}:role/argus-ueba-actors-persona-0[1-6]',arn):
                        result['entity_context']='service_or_workload'
            observed,arrived=stamp(event['timestamp']),stamp(event['ingested_at'])
            if at and observed and arrived and arrived<at and observed<at: prior.add(observed.date().isoformat())
        if len(events)<=10000 and at:
            result['prior_observed_active_days']=len(prior)
            # A display cue only, not a model gate or a claim of sufficient baseline.
            result['history_context']='limited_observed_history' if len(prior)<5 else 'observed_history'
    if row['alert_type']=='anomalous_behavior':
        result['display_title']='First-seen action outside the UTC rule window'
        result['rule_window']=RULE_WINDOW
        event_at=stamp(details.get('timestamp'))
        result['rule_event_time_utc']=event_at.isoformat() if event_at else None
    else:
        result['display_title']=row['title']
        if account: result['display_title']=result['display_title'].replace(row['user_id'],label)
        event_at=stamp(details.get('timestamp')) or stamp(row.get('created_at'))
    result['event_time_myt'],result['in_myt_office_hours']=local_time(event_at)
    result['triage']=triage(row['alert_type'],result['entity_context'],result['in_myt_office_hours'])
    result['triage_label']=TRIAGE_LABELS[result['triage']]
    return result
