"""Additive case workspace. Explicit initialization; never writes on import.

Uses the event store transaction so associations, audit and retry receipts commit
together. This module is not registered in the live application yet.
"""
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4, uuid5, NAMESPACE_URL

from backend import event_store as store

STATUSES = {'New', 'In progress', 'Closed'}
RESOLUTIONS = {'Security incident confirmed', 'Expected or authorized activity',
               'Detection false positive', 'Insufficient evidence'}
PRIORITIES = {'Low', 'Medium', 'High', 'Critical'}


class CaseConflict(ValueError):
    pass


class CaseNotFound(LookupError):
    pass


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _text(value, name, maximum=2000, required=True):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValueError(f'Invalid {name}')
    return value


def _now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    with store.transaction(), store._db() as con:
        cur = store._cursor(con)
        for ddl in [
            '''CREATE TABLE IF NOT EXISTS analyst_cases (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, priority TEXT NOT NULL,
                status TEXT NOT NULL, resolution TEXT, closing_reason TEXT,
                owner TEXT NOT NULL, notes TEXT NOT NULL, version INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                legacy_json TEXT)''',
            '''CREATE TABLE IF NOT EXISTS analyst_case_links (
                case_id TEXT NOT NULL REFERENCES analyst_cases(id),
                kind TEXT NOT NULL, target TEXT NOT NULL, reason TEXT NOT NULL,
                snapshot_json TEXT NOT NULL, linked_at TEXT NOT NULL,
                PRIMARY KEY(case_id,kind,target))''',
            '''CREATE TABLE IF NOT EXISTS analyst_case_audit (
                id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES analyst_cases(id),
                version INTEGER NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL,
                at_utc TEXT NOT NULL, detail_json TEXT NOT NULL)''',
            '''CREATE TABLE IF NOT EXISTS analyst_case_requests (
                request_key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                case_id TEXT NOT NULL REFERENCES analyst_cases(id), response_json TEXT NOT NULL)''',
            'CREATE INDEX IF NOT EXISTS idx_case_updated ON analyst_cases(updated_at,id)',
        ]:
            cur.execute(ddl)


def _one(cur, case_id):
    cur.execute(f'SELECT * FROM analyst_cases WHERE id={store._PH}', (case_id,))
    row = cur.fetchone()
    if row is None:
        raise CaseNotFound(case_id)
    return dict(row)


def _view(cur, case_id):
    row = _one(cur, case_id)
    legacy = row.pop('legacy_json')
    row['legacy'] = json.loads(legacy) if legacy is not None else None
    row['display_title']=display_title(row['title'])
    cur.execute(f'SELECT * FROM analyst_case_links WHERE case_id={store._PH} ORDER BY kind,target', (case_id,))
    row['links'] = [{**r, 'snapshot': json.loads(r['snapshot_json'])} for r in store._rows(cur)]
    for link in row['links']:
        link.pop('snapshot_json')
    cur.execute(f'SELECT * FROM analyst_case_audit WHERE case_id={store._PH} ORDER BY version,id', (case_id,))
    row['history'] = [{**r, 'detail': json.loads(r['detail_json'])} for r in store._rows(cur)]
    for entry in row['history']:
        entry.pop('detail_json')
    return row


def get(case_id):
    with store._db() as con:
        return _view(store._cursor(con), case_id)


def list_cases(limit=50, before=None):
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError('limit must be 1–100')
    with store._db() as con:
        cur = store._cursor(con)
        params, condition = [], ''
        if before:
            # Stable keyset pagination: cursor includes timestamp and id.
            if not isinstance(before, (list, tuple)) or len(before) != 2:
                raise ValueError('Invalid cursor')
            condition = f'WHERE (updated_at < {store._PH} OR (updated_at = {store._PH} AND id < {store._PH}))'
            params = [before[0], before[0], before[1]]
        cur.execute(f'SELECT * FROM analyst_cases {condition} ORDER BY updated_at DESC,id DESC LIMIT {store._PH}', (*params, limit + 1))
        rows = store._rows(cur)
        more = len(rows) > limit
        rows = rows[:limit]
        for row in rows:
            legacy = row.pop('legacy_json')
            row['legacy'] = json.loads(legacy) if legacy is not None else None
            row['display_title']=display_title(row['title'])
        return {'cases': rows, 'has_more': more,
                'next_cursor': [rows[-1]['updated_at'], rows[-1]['id']] if more else None}


def _audit(cur, case_id, version, action, actor, detail):
    cur.execute(f'INSERT INTO analyst_case_audit VALUES ({",".join([store._PH]*7)})',
                (str(uuid4()), case_id, version, action, actor, _now(), _json(detail)))


def _fingerprint(payload):
    return hashlib.sha256(_json(payload).encode()).hexdigest()


def _retry(cur, key, fingerprint):
    cur.execute(f'SELECT * FROM analyst_case_requests WHERE request_key={store._PH}', (key,))
    row = cur.fetchone()
    if row is None:
        return None
    row = dict(row)
    if row['fingerprint'] != fingerprint:
        raise CaseConflict('Request key reused with different content')
    return json.loads(row['response_json'])


def _receipt(cur, key, fingerprint, case_id):
    result = _view(cur, case_id)
    cur.execute(f'INSERT INTO analyst_case_requests VALUES ({",".join([store._PH]*4)})',
                (key, fingerprint, case_id, _json(result)))
    return result


def create(title, owner, actor, request_key, priority='Medium', notes='', *, legacy=None, context=None):
    for value, name, maximum, required in [(title,'title',240,True), (owner,'owner',200,False),
            (actor,'actor',200,True), (request_key,'request key',128,True), (notes,'notes',20000,False)]:
        _text(value, name, maximum, required)
    if priority not in PRIORITIES:
        raise ValueError('Invalid priority')
    payload = dict(title=title, owner=owner, actor=actor, priority=priority, notes=notes, legacy=legacy, context=context)
    fp, key = _fingerprint(payload), 'create:' + request_key
    # Stable id serializes simultaneous retries on Postgres as well as SQLite.
    cid = str(uuid5(NAMESPACE_URL, 'argus-case:' + request_key))
    with store.transaction(), store._db() as con:
        cur = store._cursor(con)
        replay = _retry(cur, key, fp)
        if replay is not None:
            return replay
        now = _now()
        cur.execute(f'''INSERT INTO analyst_cases VALUES ({','.join([store._PH]*12)})
            ON CONFLICT(id) DO NOTHING''', (cid,title,priority,'New',None,None,owner,notes,1,now,now,
                                           _json(legacy) if legacy is not None else None))
        if cur.rowcount == 0:
            replay = _retry(cur, key, fp)
            if replay is None:
                raise CaseConflict('Case creation request is incomplete')
            return replay
        _audit(cur,cid,1,'legacy_imported' if legacy is not None else 'created',actor,payload)
        return _receipt(cur,key,fp,cid)


def _mutate(case_id, expected_version, actor, request_key, action, payload, apply):
    _text(actor,'actor',200); _text(request_key,'request key',128)
    if type(expected_version) is not int or expected_version < 1:
        raise ValueError('Invalid expected version')
    fp = _fingerprint(dict(version=expected_version,actor=actor,action=action,payload=payload))
    key = case_id + ':' + request_key
    with store.transaction(), store._db() as con:
        cur = store._cursor(con)
        replay = _retry(cur,key,fp)
        if replay is not None:
            return replay
        row = _one(cur,case_id)
        if row['status'] == 'Closed':
            raise CaseConflict('Closed cases cannot be edited or silently reopened')
        cur.execute(f'''UPDATE analyst_cases SET version=version+1,updated_at={store._PH}
            WHERE id={store._PH} AND version={store._PH}''', (_now(),case_id,expected_version))
        if cur.rowcount != 1:
            # Another writer may have completed the exact request while we waited.
            replay = _retry(cur,key,fp)
            if replay is not None:
                return replay
            raise CaseConflict('Stale case version; reload before editing')
        apply(cur,row)
        _audit(cur,case_id,expected_version+1,action,actor,payload)
        return _receipt(cur,key,fp,case_id)


def update(case_id, expected_version, actor, request_key, changes):
    allowed = {'title','owner','notes','priority','status','resolution','closing_reason','change_reason'}
    if not changes or set(changes) - allowed:
        raise ValueError('Invalid case fields')
    for field in ('title','owner','notes','closing_reason'):
        if field in changes:
            maximum = {'title':240,'owner':200,'notes':20000,'closing_reason':2000}[field]
            _text(changes[field],field,maximum, field == 'title')
    if 'change_reason' in changes:
        _text(changes['change_reason'],'change reason',2000)
    fields = {key:value for key,value in changes.items() if key != 'change_reason'}
    if not fields:
        raise ValueError('No case fields to change')
    if 'priority' in changes and changes['priority'] not in PRIORITIES:
        raise ValueError('Invalid priority')
    if 'status' in changes and changes['status'] not in STATUSES:
        raise ValueError('Invalid lifecycle')
    closing = changes.get('status') == 'Closed'
    if closing:
        if changes.get('resolution') not in RESOLUTIONS or not changes.get('closing_reason','').strip():
            raise ValueError('Closing requires a resolution and reason')
    elif {'resolution','closing_reason'} & set(changes):
        raise ValueError('Resolution is only set when closing')

    def apply(cur, row):
        if 'priority' in fields and fields['priority'] != row['priority'] and not changes.get('change_reason','').strip():
            raise ValueError('Priority change requires a reason')
        cur.execute(f'UPDATE analyst_cases SET {",".join(field+"="+store._PH for field in fields)} WHERE id={store._PH}',
                    (*fields.values(),case_id))
    return _mutate(case_id,expected_version,actor,request_key,'updated',changes,apply)


def _evidence(cur, event_id):
    cur.execute(f'''SELECT id,timestamp,source,action,resource,ip_address,event_id,
        source_account_id,payload_digest,account_key FROM events WHERE id={store._PH}''', (event_id,))
    row = cur.fetchone()
    if row is None:
        raise CaseNotFound('Event not found')
    from workspace_next.finding_context import object_value
    return {**dict(row), 'resource_value':object_value(dict(row)['resource']),
            'representation':'normalized_event', 'original_payload_status':'not_resolved'}


def display_title(title):
    for key,account in store.account_directory().items():
        title=title.replace(key,account['account_label'])
    return title


def evidence(event_id):
    with store._db() as con:
        return _evidence(store._cursor(con),event_id)


def retain_diagnostic(case_id, expected_version, actor, request_key, reason, snapshot):
    """Retain server-validated account-day context; never a triggering event or verdict."""
    _text(reason, 'diagnostic context reason', 2000)
    if (not isinstance(snapshot, dict) or snapshot.get('association') != 'account_day_context_not_trigger_attribution'
            or not isinstance(snapshot.get('receipt'), dict)
            or snapshot.get('live_activation') is not False or snapshot.get('risk_tier') is not None):
        raise ValueError('Validated diagnostic context required')
    target = _fingerprint(snapshot)
    def apply(cur, row):
        cur.execute(f'''INSERT INTO analyst_case_links VALUES ({','.join([store._PH]*6)})
            ON CONFLICT(case_id,kind,target) DO NOTHING''',
                    (case_id, 'diagnostic', target, reason, _json(snapshot), _now()))
    return _mutate(case_id, expected_version, actor, request_key, 'diagnostic_context_retained',
                   {'target': target, 'reason': reason, 'snapshot': snapshot}, apply)


def link(case_id, expected_version, actor, request_key, kind, target, reason):
    if kind not in {'finding','account','event','person'}:
        raise ValueError('Unsupported link kind')
    _text(target,'target',256); _text(reason,'link reason',2000)

    def apply(cur, row):
        if kind == 'event':
            if not target.isdecimal():
                raise ValueError('Invalid event id')
            snapshot = _evidence(cur,int(target))
        elif kind == 'finding':
            if not target.isdecimal():
                raise ValueError('Invalid finding id')
            cur.execute(f'SELECT * FROM alerts WHERE id={store._PH}', (int(target),))
            found = cur.fetchone()
            if found is None:
                raise CaseNotFound('Finding not found')
            snapshot = dict(found)
            snapshot['association'] = 'analyst_selected_not_automatic_trigger_evidence'
        elif kind == 'person':
            from backend import identity_links
            try:
                person = identity_links.person_view(target)
            except (LookupError, ValueError) as exc:
                raise CaseNotFound('Person not found') from exc
            approved = [item for item in person['links']
                        if item['effective_status'] == 'approved'
                        and item.get('account',{}).get('source') in identity_links.SUPPORTED]
            if not approved:
                raise ValueError('Person has no currently approved supported accounts')
            snapshot = {'person_id':target,'display_name':person['display_name'],
                        'approved_links':approved,'association':'approved_mapping_snapshot'}
        else:
            snapshot = store.account_directory().get(target)
            if snapshot is None:
                raise CaseNotFound('Account not found')
            snapshot = {**snapshot,'association':'related_account_not_person_ownership_proof'}
        cur.execute(f'''INSERT INTO analyst_case_links VALUES ({','.join([store._PH]*6)})
            ON CONFLICT(case_id,kind,target) DO NOTHING''', (case_id,kind,target,reason,_json(snapshot),_now()))
    return _mutate(case_id,expected_version,actor,request_key,'linked',
                   dict(kind=kind,target=target,reason=reason),apply)


def import_legacy(records, source_id):
    """Explicit all-or-nothing import. Does not touch the legacy writer/store.

    Source id is stable across retries. A changed source record conflicts rather
    than overwriting the imported analyst's later work. All original fields,
    including timestamps, history and status, are retained verbatim in legacy.
    """
    _text(source_id,'source id',200)
    if not isinstance(records,dict):
        raise ValueError('Legacy export must be keyed by account')
    result = []
    with store.transaction():
        for account, record in sorted(records.items()):
            _text(account,'legacy account',500)
            if not isinstance(record,dict) or not isinstance(record.get('history',[]),list):
                raise ValueError('Malformed legacy record')
            key = hashlib.sha256((source_id+'\0'+account).encode()).hexdigest()
            result.append(create('Imported investigation: '+account[:200],record.get('analyst',''),
                'Legacy import',key,notes=record.get('notes',''),
                legacy={'account':account,'record':record,'source_id':source_id}))
    return result
