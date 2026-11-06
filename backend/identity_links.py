"""Explicit reviewed account ownership links; never joins detector inputs."""
from datetime import datetime, timezone
import json
import sqlite3
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from backend import event_store as store

router = APIRouter(prefix='/identities', tags=['Identity mappings'])
SUPPORTED = {'github_events', 'cloudflare_access'}


def now():
    return datetime.now(timezone.utc)


def stamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    return dt.astimezone(timezone.utc)


def init_db():
    with store._db() as con:
        cur = store._cursor(con)
        cur.execute('''CREATE TABLE IF NOT EXISTS identity_people (
            id TEXT PRIMARY KEY, display_name TEXT NOT NULL, created_at TEXT NOT NULL)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS identity_links (
            id TEXT PRIMARY KEY, person_id TEXT NOT NULL, account_key TEXT NOT NULL,
            status TEXT NOT NULL, approved_by TEXT NOT NULL, evidence TEXT NOT NULL,
            approved_at TEXT NOT NULL, expires_at TEXT, revoked_at TEXT)''')
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_identity_active_account ON identity_links(account_key) WHERE status='approved'")
        cur.execute('CREATE INDEX IF NOT EXISTS idx_identity_person ON identity_links(person_id)')
        cur.execute('''CREATE TABLE IF NOT EXISTS identity_link_audit (
            id TEXT PRIMARY KEY, person_id TEXT NOT NULL, link_id TEXT,
            action TEXT NOT NULL, recorded_by TEXT NOT NULL, note TEXT NOT NULL, at_utc TEXT NOT NULL)''')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_identity_audit_person ON identity_link_audit(person_id)')


def audit(cur, person_id, link_id, action, actor, note):
    cur.execute(f"INSERT INTO identity_link_audit VALUES ({','.join([store._PH]*7)})",
                (uuid4().hex, person_id, link_id, action, actor, note, now().isoformat()))


def create_person(name, actor):
    name, actor = name.strip(), actor.strip()
    if not name or not actor:
        raise ValueError('Name and recorder are required')
    person = {'id': 'person_' + uuid4().hex, 'display_name': name, 'created_at': now().isoformat()}
    with store.transaction(), store._db() as con:
        cur = store._cursor(con)
        cur.execute(f"INSERT INTO identity_people VALUES ({','.join([store._PH]*3)})", tuple(person.values()))
        audit(cur, person['id'], None, 'person_created', actor, name)
    return person


def get_person(person_id):
    with store._db() as con:
        cur = store._cursor(con); cur.execute(f'SELECT * FROM identity_people WHERE id={store._PH}', (person_id,))
        rows = store._rows(cur)
    return rows[0] if rows else None


def link_status(link, directory, at=None):
    if link['status'] != 'approved':
        return link['status']
    if link['expires_at'] and stamp(link['expires_at']) <= (at or now()):
        return 'expired'
    if link['account_key'] not in directory:
        return 'missing_account'
    return 'approved'


def approve(person_id, key, actor, evidence, expires_at=None):
    directory = store.account_directory()
    account = directory.get(key)
    if not get_person(person_id):
        raise LookupError('Identity not found')
    if account is None or account['source'] not in SUPPORTED:
        raise ValueError('Select an observed GitHub or Cloudflare native account. AWS ownership is not enabled in this release.')
    if account.get('account_kind') == 'service_token':
        raise ValueError('Cloudflare machine credentials cannot be approved as a human identity.')
    if not actor.strip() or not evidence.strip():
        raise ValueError('Recorder and ownership evidence are required')
    expiry = stamp(expires_at).isoformat() if expires_at else None
    if expiry and stamp(expiry) <= now():
        raise ValueError('Expiry must be in the future')
    with store.transaction(), store._db() as con:
        cur = store._cursor(con)
        cur.execute(f"SELECT * FROM identity_links WHERE account_key={store._PH} AND status='approved'", (key,))
        previous = store._rows(cur)
        if previous:
            old = previous[0]
            if old['expires_at'] and stamp(old['expires_at']) <= now():
                cur.execute(f"UPDATE identity_links SET status='expired' WHERE id={store._PH}", (old['id'],))
                audit(cur, old['person_id'], old['id'], 'link_expired', actor, 'Prior approval expired')
            elif old['person_id'] == person_id:
                return old
            else:
                raise ValueError('This account already has an approved identity. Revoke that link before reassignment.')
        link = {'id': 'link_' + uuid4().hex, 'person_id': person_id, 'account_key': key,
                'status': 'approved', 'approved_by': actor.strip(), 'evidence': evidence.strip(),
                'approved_at': now().isoformat(), 'expires_at': expiry, 'revoked_at': None}
        cur.execute(f"INSERT INTO identity_links VALUES ({','.join([store._PH]*9)})", tuple(link.values()))
        audit(cur, person_id, link['id'], 'link_approved', actor.strip(), evidence.strip())
    return link


def revoke(link_id, actor, note):
    if not actor.strip() or not note.strip():
        raise ValueError('Recorder and revocation reason are required')
    with store.transaction(), store._db() as con:
        cur = store._cursor(con); cur.execute(f'SELECT * FROM identity_links WHERE id={store._PH}', (link_id,))
        rows = store._rows(cur)
        if not rows:
            raise LookupError('Link not found')
        row = rows[0]
        if row['status'] != 'revoked':
            cur.execute(f"UPDATE identity_links SET status='revoked',revoked_at={store._PH} WHERE id={store._PH}", (now().isoformat(), link_id))
            audit(cur, row['person_id'], link_id, 'link_revoked', actor, note)
    return {'status': 'revoked', 'id': link_id}


def person_view(person_id):
    person = get_person(person_id)
    if not person:
        raise LookupError('Identity not found')
    directory = store.account_directory()
    with store._db() as con:
        cur = store._cursor(con); cur.execute(f'SELECT * FROM identity_links WHERE person_id={store._PH} ORDER BY approved_at,id', (person_id,))
        links = store._rows(cur)
        cur.execute(f'SELECT * FROM identity_link_audit WHERE person_id={store._PH} ORDER BY at_utc,id', (person_id,))
        history = store._rows(cur)
    for link in links:
        link['effective_status'] = link_status(link, directory)
        link['account'] = directory.get(link['account_key'])
    return {**person, 'links': links, 'audit': history,
            'active_links': sum(link['effective_status'] == 'approved' for link in links)}


def timeline(person_id, limit=100):
    person = person_view(person_id)
    links = {link['account_key']: link for link in person['links'] if link['effective_status'] == 'approved'}
    records = []
    if links:
        with store._db() as con:
            cur = store._cursor(con)
            cur.execute(f'''SELECT id,timestamp,source,action,resource,ip_address,event_id,
                source_account_id,account_key FROM events WHERE account_key IN
                ({','.join([store._PH]*len(links))}) ORDER BY id DESC LIMIT 5001''', tuple(links))
            records = store._rows(cur)
    bounded = len(records) > 5000
    invalid, valid = 0, []
    for row in records[:5000]:
        try:
            timestamp = stamp(row['timestamp'])
        except (ValueError, TypeError):
            invalid += 1; continue
        row['account_label'] = links[row['account_key']]['account']['account_label']
        row['timestamp_utc'] = timestamp.isoformat()
        valid.append(row)
    valid.sort(key=lambda row: (row['timestamp_utc'], row['source'], row['id']), reverse=True)
    sources = sorted({link['account']['source'] for link in links.values()})
    return {'person_id': person_id, 'events': valid[:limit], 'scanned_events': len(records[:5000]),
            'has_more': bounded or len(valid) > limit, 'scan_capped': bounded,
            'invalid_timestamps': invalid, 'linked_sources': sources,
            'unlinked_sources': sorted({'aws_cloudtrail', 'github_events', 'cloudflare_access'} - set(sources)),
            'coverage': 'observed_activity_only_completeness_unknown', 'score_policy': 'per_account_no_person_score'}


class PersonRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    display_name: str = Field(min_length=1, max_length=100)
    recorded_by: str = Field(min_length=1, max_length=100)


class LinkRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    account_key: str = Field(pattern=r'^acct_[0-9a-f]{64}$')
    recorded_by: str = Field(min_length=1, max_length=100)
    evidence: str = Field(min_length=1, max_length=2000)
    expires_at: str | None = None


class RevokeRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    recorded_by: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)


def call(function, *args):
    try:
        return function(*args)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        if isinstance(exc, sqlite3.IntegrityError) or getattr(exc, 'pgcode', None) == '23505':
            raise HTTPException(status_code=409, detail='Account link conflicts with an existing approval') from exc
        raise


@router.get('')
def list_people():
    with store._db() as con:
        cur = store._cursor(con); cur.execute('SELECT id FROM identity_people ORDER BY created_at,id')
        people = store._rows(cur)
    return [person_view(person['id']) for person in people]


@router.get('/accounts')
def available_accounts():
    return [account for account in store.account_directory().values()
            if account['source'] in SUPPORTED and account.get('account_kind') != 'service_token']


@router.post('')
def add_person(body: PersonRequest):
    return call(create_person, body.display_name, body.recorded_by)


@router.post('/links/{link_id}/revoke')
def revoke_link(link_id: str, body: RevokeRequest):
    return call(revoke, link_id, body.recorded_by.strip(), body.reason.strip())


@router.get('/{person_id}/timeline')
def get_timeline(person_id: str, limit: int = Query(100, ge=1, le=200)):
    return call(timeline, person_id, limit)


@router.post('/{person_id}/links')
def add_link(person_id: str, body: LinkRequest):
    return call(approve, person_id, body.account_key, body.recorded_by, body.evidence, body.expires_at)


@router.get('/{person_id}')
def get_identity(person_id: str):
    return call(person_view, person_id)
