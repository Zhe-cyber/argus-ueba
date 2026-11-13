"""Isolated signed GitHub evidence capture. No deployment or live-store integration."""
from datetime import datetime, timezone
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

MAX_BODY = 512 * 1024
EVENTS = frozenset(('ping', 'push', 'pull_request', 'issues', 'issue_comment', 'create', 'delete'))


class Conflict(ValueError):
    pass


def positive_int(value):
    return type(value) is int and value > 0


def parse_payload(body, event_type, repository_id, repository_name):
    def reject_constant(_):
        raise ValueError('Non-finite JSON value')

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result

    payload = json.loads(body.decode('utf-8'), parse_constant=reject_constant, object_pairs_hook=unique_object)
    if not isinstance(payload, dict):
        raise ValueError('Object required')
    repo, sender = payload.get('repository'), payload.get('sender')
    if (not isinstance(repo, dict) or not positive_int(repo.get('id'))
            or repo['id'] != repository_id or repo.get('full_name') != repository_name
            or not isinstance(sender, dict) or not positive_int(sender.get('id'))):
        raise ValueError('Unexpected repository or sender')
    if event_type == 'ping':
        valid = positive_int(payload.get('hook_id')) and isinstance(payload.get('zen'), str)
    elif event_type == 'push':
        valid = (isinstance(payload.get('ref'), str) and bool(payload['ref'])
                 and isinstance(payload.get('pusher'), dict)
                 and isinstance(payload.get('commits'), list)
                 and all(isinstance(payload.get(k), str) and re.fullmatch('(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})', payload[k])
                         for k in ('before', 'after')))
    elif event_type in ('create', 'delete'):
        valid = ((payload.get('ref_type') in ('branch', 'tag')
                  and isinstance(payload.get('ref'), str) and bool(payload['ref']))
                 or (event_type == 'create' and payload.get('ref_type') == 'repository'
                     and payload.get('ref') is None))
    else:
        target = {'pull_request': 'pull_request', 'issues': 'issue', 'issue_comment': 'comment'}[event_type]
        valid = (isinstance(payload.get('action'), str) and bool(payload['action'])
                 and isinstance(payload.get(target), dict) and positive_int(payload[target].get('id')))
    if not valid:
        raise ValueError('Payload does not match selected event schema')
    # Native type is explicit when supplied; do not infer a human from a login suffix.
    actor_type = sender.get('type') if sender.get('type') in ('User', 'Bot', 'Organization') else 'Unknown'
    return sender['id'], actor_type


def connect(database):
    db = sqlite3.connect(database, timeout=5)
    db.execute('PRAGMA synchronous=FULL')
    return db


def init_store(database):
    with connect(database) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS deliveries (
            delivery_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
            repository_id INTEGER NOT NULL, actor_id INTEGER NOT NULL, actor_type TEXT NOT NULL,
            received_at_utc TEXT NOT NULL, body_sha256 TEXT NOT NULL, signed_body BLOB NOT NULL,
            UNIQUE(body_sha256))''')


def persist(database, delivery, event_type, repository_id, actor_id, actor_type, body):
    sha = hashlib.sha256(body).hexdigest()
    with connect(database) as db:
        db.execute('BEGIN IMMEDIATE')
        prior = db.execute('SELECT event_type, body_sha256, signed_body FROM deliveries WHERE delivery_id=?',
                           (delivery,)).fetchone()
        if prior:
            if prior != (event_type, sha, body):
                raise Conflict('Delivery conflict')
            return True
        if db.execute('SELECT 1 FROM deliveries WHERE body_sha256=?', (sha,)).fetchone():
            raise Conflict('Repeated payload under another delivery ID')
        db.execute('INSERT INTO deliveries VALUES (?,?,?,?,?,?,?,?)',
                   (delivery, event_type, repository_id, actor_id, actor_type,
                    datetime.now(timezone.utc).isoformat(), sha, body))
    return False


def create_app(database, secret, repository_id, repository_name):
    database = Path(database).resolve()
    if (database.name != 'github-webhooks.db' or not database.parent.is_dir()
            or not isinstance(secret, bytes) or len(secret) < 32 or not positive_int(repository_id)
            or not isinstance(repository_name, str)
            or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository_name)):
        raise ValueError('Dedicated store, private 32-byte secret and pinned repository required')
    init_store(database)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.post('/github/webhook')
    async def webhook(request: Request):
        def header(name):
            values = request.headers.getlist(name)
            if len(values) != 1:
                raise HTTPException(400, 'Missing or repeated delivery header')
            return values[0]

        signature = header('x-hub-signature-256')
        event_type = header('x-github-event')
        delivery = header('x-github-delivery')
        content_type = header('content-type')
        if request.headers.get('content-encoding', 'identity').lower() != 'identity':
            raise HTTPException(415, 'Encoded payload unsupported')
        if content_type.split(';', 1)[0].strip().lower() != 'application/json':
            raise HTTPException(415, 'JSON required')
        if event_type not in EVENTS or not re.fullmatch(r'sha256=[0-9a-f]{64}', signature):
            raise HTTPException(400, 'Unsupported delivery format')
        try:
            if str(UUID(delivery)) != delivery:
                raise ValueError('Noncanonical UUID')
        except ValueError:
            raise HTTPException(400, 'Invalid delivery ID') from None
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY:
                raise HTTPException(413, 'Payload too large')
            body.extend(chunk)
        body = bytes(body)
        expected = 'sha256=' + hmac.new(secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(401, 'Invalid signature')
        try:
            actor_id, actor_type = parse_payload(body, event_type, repository_id, repository_name)
        except (ValueError, TypeError, RecursionError):
            raise HTTPException(422, 'Invalid or out-of-scope payload') from None
        try:
            duplicate = await run_in_threadpool(persist, database, delivery, event_type,
                                               repository_id, actor_id, actor_type, body)
        except Conflict:
            raise HTTPException(409, 'Delivery evidence conflict') from None
        except sqlite3.Error:
            raise HTTPException(503, 'Evidence storage unavailable') from None
        return {'stored': True, 'duplicate': duplicate, 'native_event_time': 'not_asserted', 'scored': False}

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--secret-file', required=True)
    parser.add_argument('--repository-id', type=int, required=True)
    parser.add_argument('--repository', required=True)
    args = parser.parse_args()
    app = create_app(args.database, Path(args.secret_file).read_bytes(), args.repository_id, args.repository)
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8014, access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
