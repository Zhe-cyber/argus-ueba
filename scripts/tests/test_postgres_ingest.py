"""Opt-in PostgreSQL integration in a disposable, explicitly local test database.

Never uses DATABASE_URL from the developer environment or production .env.
"""
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import pytest


def test_postgres_atomic_ingestion():
    url = os.environ.get('ARGUS_TEST_PG_URL')
    if not url:
        pytest.skip('Set ARGUS_TEST_PG_URL for an isolated local PostgreSQL integration run')
    parsed = urlsplit(url)
    assert parsed.scheme in ('postgres', 'postgresql')
    assert parsed.hostname == '127.0.0.1' and parsed.port == 55432
    assert parsed.path == '/argus_ingest_test', 'Refusing a non-test database'
    import psycopg2
    from psycopg2 import sql
    schema = 'argus_test_' + uuid4().hex
    con = psycopg2.connect(url)
    con.autocommit = True
    try:
        with con.cursor() as cur:
            cur.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        query = dict(parse_qsl(parsed.query))
        query['options'] = '-csearch_path=' + schema
        isolated_url = urlunsplit(parsed._replace(query=urlencode(query)))
        code = r'''
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from backend import event_store as db, main
from backend.normalizer import normalize
assert db._PG is True
# Seed the old schema before startup, then exercise repeated migrations.
with db._db() as con:
    cur=db._cursor(con)
    cur.execute(db._DDL_EVENTS)
    cur.execute("INSERT INTO events (\"user\",timestamp,source,action,resource,ingested_at) VALUES ('legacy','old','cert_logon','Logon','pc1','old')")
db.init_db()
db.init_db()
assert db.get_total_event_count('legacy')==1
body={'source':'aws_cloudtrail','source_account_id':'123456789012','event':{'eventID':'postgres-one','eventTime':'2026-10-27T12:00:00Z','eventName':'ListBuckets','userIdentity':{'userName':'postgres-test','accountId':'123456789012'}}}
main.cloud_ae_scorer.score_user=lambda *args: None
with TestClient(main.app,raise_server_exceptions=False) as client:
    one=client.post('/ingest',json=body)
    assert one.status_code==200, one.status_code
    two=client.post('/ingest',json=body)
    assert two.status_code==200 and two.json()['duplicate'] is True
    assert db.get_total_event_count('postgres-test')==1
    assert db.get_live_score('postgres-test')['ae_live'] is None
    changed={**body,'event':{**body['event'],'eventID':'postgres-failure'}}
    def fail(*args): raise RuntimeError('injected scoring error')
    main.cloud_ae_scorer.score_user=fail
    assert client.post('/ingest',json=changed).status_code==500
    assert db.get_total_event_count('postgres-test')==1
    main.cloud_ae_scorer.score_user=lambda *args: None
    assert client.post('/ingest',json=changed).json()['duplicate'] is False
    # SQL failures in optional alert creation must not abort the outer PG commit.
    original=main.astore.create_alert
    def bad_alert(*args):
        original(*args)
        with db._db() as con:
            db._cursor(con).execute('SELECT * FROM nonexistent_alert_test_table')
    main.astore.create_alert=bad_alert
    alert_body={**body,'event':{**body['event'],'eventID':'postgres-alert','userIdentity':{'userName':'alert-test','accountId':'123456789012'}}}
    assert client.post('/ingest',json=alert_body).status_code==200
    assert db.get_total_event_count('alert-test')==1
    with db._db() as con:
        cur=db._cursor(con)
        cur.execute("SELECT COUNT(*) AS n FROM alerts WHERE user_id='alert-test'")
        assert cur.fetchone()['n']==0
event=normalize({**body['event'],'eventID':'concurrent-key'},'aws_cloudtrail')
def insert(_):
    with db.transaction(): return db.insert_event(event)
with ThreadPoolExecutor(max_workers=4) as pool:
    assert list(pool.map(insert,range(8))).count(True)==1
print('Postgres migration, receipts, null scores, rollback, alert savepoints and concurrent inserts passed')
'''
        environment = dict(os.environ, DATABASE_URL=isolated_url, ARGUS_MODE='live', DEMO_MODE='false')
        result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[2],
                                env=environment, capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        # This schema was created above in the guarded local test database only.
        with con.cursor() as cur:
            cur.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        con.close()
