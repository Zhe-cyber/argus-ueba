"""L14 review fixes: method enforcement, portable LIKE, score repair, pinned comparator, readiness command.
Synthetic events only."""
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sqlite3

import pytest
from fastapi.testclient import TestClient

pytest.importorskip('torch')

from backend import baseline_scorer as scorer, event_store, investigations, live_ae, loader, main, readiness
from backend.tests.live_ae_fixture import ACCOUNT, make_bundle, persona_event, persona_stream

REAL_BUNDLE = Path(r'C:\Users\yyzhe\argus-worktrees\l10-live-ae\data\live\live-ae\bundle-v2-20261113T010640')
SCORED_DAY = '2026-10-15'  # the sixth active day of persona_stream(): scorable by both scorers


@pytest.fixture
def comparator(tmp_path, monkeypatch):
    """A test-only comparator bundle, pinned for this test."""
    bundle = tmp_path / 'bundle'
    monkeypatch.setattr(live_ae, 'EXPECTED_MANIFEST_SHA256', make_bundle(bundle))
    monkeypatch.setenv('ARGUS_LIVE_AE_BUNDLE', str(bundle))
    monkeypatch.setattr(live_ae, '_CACHE', {})
    monkeypatch.setattr(live_ae, '_LOADED', {})
    return bundle


@pytest.fixture
def live(monkeypatch, tmp_path):
    monkeypatch.setenv('ARGUS_ACCOUNT_KEYS', 'source-principal-v1')
    monkeypatch.setattr(loader, 'LIVE_MODE', True)
    monkeypatch.setattr(main, 'LIVE_MODE', True)
    monkeypatch.setattr(main, 'ARGUS_MODE', 'live')
    monkeypatch.setattr(main, 'store', loader.DataStore())
    monkeypatch.setattr(event_store, 'DB_PATH', tmp_path / 'events.db')
    monkeypatch.setattr(investigations, 'INVESTIGATIONS_PATH', tmp_path / 'investigations.json')
    monkeypatch.setattr(main.cloud_ae_scorer, 'score_user', lambda *_: 0.1)
    monkeypatch.setattr(loader.pd, 'read_csv', lambda *a, **k: (_ for _ in ()).throw(AssertionError('benchmark read')))
    with TestClient(main.app) as client:
        yield client


def rows(table, day=None):
    with sqlite3.connect(event_store.DB_PATH) as con:
        sql = f'SELECT account_key, day FROM {table}' + (' WHERE day=?' if day else '')
        return con.execute(sql, (day,) if day else ()).fetchall()


# --- 1. method enforcement ------------------------------------------------------------------------------

def test_matching_binding_is_ready_and_scores(live):
    assert scorer.STATUS['scoring_ready'] is True and scorer.check_method() == scorer.STATUS
    assert live.get('/').json()['scoring_ready'] is True
    for body in persona_stream():
        assert live.post('/ingest', json=body).status_code == 200
    assert len(rows('baseline_scores')) == 6


@pytest.mark.parametrize('alter', ['constant', 'sensitive_list'])
def test_mismatched_binding_is_not_ready_and_writes_nothing(live, monkeypatch, alter, tmp_path, caplog):
    if alter == 'constant':
        monkeypatch.setattr(scorer, 'WEIGHTS', {**scorer.WEIGHTS, 'volume': 0.16})
    else:  # the deployment list the process loaded differs from the bound one
        altered = tmp_path / 'sensitive.json'
        altered.write_bytes(scorer.SENSITIVE_FILE.read_bytes().replace(b'"providers"', b'"providers" ', 1))
        monkeypatch.setattr(scorer, 'SENSITIVE_SHA256', hashlib.sha256(altered.read_bytes()).hexdigest())
    monkeypatch.setattr(scorer, 'STATUS', scorer.check_method())
    assert scorer.STATUS['scoring_ready'] is False
    assert ('weights' if alter == 'constant' else 'sensitive_resources_sha256') in scorer.STATUS['reason']
    for body in persona_stream():
        assert live.post('/ingest', json=body).status_code == 200  # collection continues
    assert rows('baseline_scores') == [] and scorer.backfill() == {} and rows('baseline_scores') == []
    health = live.get('/').json()
    assert health['scoring_ready'] is False and health['scoring_reason'] == scorer.STATUS['reason']
    assert live.get('/readiness').json()['ok'] is False
    with pytest.raises(SystemExit, match='refused'):
        scorer.main(['--repair-missing'])


# --- 2. no literal % in parameterised SQL -----------------------------------------------------------------

def test_no_literal_percent_in_backend_sql():
    for path in (Path(main.__file__).parent).glob('*.py'):
        assert not re.search(r"LIKE\s+'[^']*%", path.read_text(encoding='utf-8')), path.name


class PyformatCursor:
    """Applies psycopg2's rule to every parameterised query: `sql % args` (a bare % raises)."""
    def __init__(self):
        self.seen = []

    def execute(self, sql, args=None):
        if args is not None:
            self.seen.append(sql % tuple(repr(a) for a in args))

    def fetchone(self):
        return None


def test_scorer_queries_survive_pyformat_parameters(monkeypatch):
    from contextlib import contextmanager
    cur = PyformatCursor()

    @contextmanager
    def fake_db():
        yield None
    monkeypatch.setattr(event_store, '_PH', '%s')
    monkeypatch.setattr(event_store, '_db', fake_db)
    monkeypatch.setattr(event_store, '_cursor', lambda con: cur)
    monkeypatch.setattr(event_store, '_rows', lambda c: [])
    scorer._account_rows(cur, 'acct_k', date(2026, 11, 1), date(2026, 11, 2))
    live_ae.rescore_day({'threshold': 1, 'model_sha256': 'x'}, 'acct_k', date(2026, 11, 1))
    assert sum("NOT LIKE '____-__-__%'" in q for q in cur.seen) == 2


def test_prefilter_keeps_non_iso_stamps(live):
    with sqlite3.connect(event_store.DB_PATH) as con:
        con.execute("INSERT INTO events (\"user\",timestamp,source,action,resource,ingested_at,account_key) "
                    "VALUES ('u','Tue, 10 Nov 2026 02:00:00 +0000','aws_cloudtrail','A','r','x','acct_k')")
    with event_store._db() as con:
        got = scorer._account_rows(event_store._cursor(con), 'acct_k', date(2026, 11, 1), date(2026, 11, 2))
    assert len(got) == 1  # outside the ISO range, kept for exact parsing


# --- 2/3. ingest writes both rows; duplicate delivery repairs a failed first scoring ------------------------

def test_ingest_writes_baseline_and_ml_rows(live, comparator):
    for body in persona_stream():
        assert live.post('/ingest', json=body).status_code == 200
    assert len(rows('baseline_scores', SCORED_DAY)) == 1 and len(rows('ml_scores', SCORED_DAY)) == 1
    with sqlite3.connect(event_store.DB_PATH) as con:
        assert con.execute('SELECT score IS NOT NULL, model_sha256 FROM ml_scores WHERE day=?', (SCORED_DAY,)).fetchone() \
            == (1, live_ae.EXPECTED_MANIFEST_SHA256)
    assert readiness.missing_scores() == []


def test_duplicate_delivery_repairs_missing_scores(live, comparator, monkeypatch):
    for body in persona_stream():
        live.post('/ingest', json=body)
    real_baseline, real_ml = scorer.on_event, live_ae.on_event
    monkeypatch.setattr(scorer, 'on_event', lambda *a, **k: 1 / 0)
    monkeypatch.setattr(live_ae, 'on_event', lambda *a, **k: 1 / 0)
    assert live.post('/ingest', json=persona_event('new-day', '2026-10-16T02:00:00Z')).status_code == 200
    assert rows('baseline_scores', '2026-10-16') == [] and rows('ml_scores', '2026-10-16') == []
    missing = readiness.missing_scores()
    assert [(m['day'], m['missing']) for m in missing] == [('2026-10-16', ['baseline', 'ml'])]
    assert live.get('/readiness').json()['missing_scores'] == {'total': 1, 'baseline': 1, 'ml': 1}
    monkeypatch.setattr(scorer, 'on_event', real_baseline)
    monkeypatch.setattr(live_ae, 'on_event', real_ml)
    again = live.post('/ingest', json=persona_event('new-day', '2026-10-16T02:00:00Z'))
    assert again.json()['duplicate'] is True
    assert len(rows('baseline_scores', '2026-10-16')) == 1 and len(rows('ml_scores', '2026-10-16')) == 1
    assert readiness.missing_scores() == [] and live.get('/readiness').json()['missing_scores']['total'] == 0


def test_repair_commands_score_exactly_the_missing_days(live, comparator, capsys):
    for body in persona_stream():
        live.post('/ingest', json=body)
    with sqlite3.connect(event_store.DB_PATH) as con:
        con.execute('DELETE FROM baseline_scores WHERE day IN (?, ?)', ('2026-10-12', SCORED_DAY))
        con.execute('DELETE FROM ml_scores WHERE day=?', (SCORED_DAY,))
    assert {(m['day'], tuple(m['missing'])) for m in readiness.missing_scores()} == {
        ('2026-10-12', ('baseline',)), (SCORED_DAY, ('baseline', 'ml'))}
    scorer.main(['--repair-missing', '--db', str(event_store.DB_PATH)])
    assert 'account-days scored: 2' in capsys.readouterr().out
    live_ae.main(['repair-missing', '--bundle', str(comparator), '--db', str(event_store.DB_PATH)])
    assert json.loads(capsys.readouterr().out)['account_days_scored'] == 1
    assert readiness.missing_scores() == []


# --- 5. pinned comparator -------------------------------------------------------------------------------

def test_pin_is_the_preregistered_manifest():
    pin = json.loads(live_ae.PIN_FILE.read_text(encoding='utf-8'))
    assert pin['expected_manifest_sha256'] == 'd41e86a92cc24e6db706b161caef780a10d54f5f7c82592bcd7da6f2d7a2ffc0'
    assert pin['bundle'] == 'bundle-v2-20261113T010640' == REAL_BUNDLE.name


def test_right_hash_loads_and_other_bundle_is_refused(tmp_path, monkeypatch, live):
    monkeypatch.setattr(live_ae, '_CACHE', {})
    monkeypatch.setattr(live_ae, '_LOADED', {})
    other = tmp_path / 'other'
    make_bundle(other)  # self-consistent (artifact hashes match) but not the pinned manifest
    with pytest.raises(live_ae.Refusal, match='pinned'):
        live_ae.load(other)
    monkeypatch.setenv('ARGUS_LIVE_AE_BUNDLE', str(other))
    assert live_ae.configured() is None
    recorded = json.loads((tmp_path / live_ae.LOADED_FILE).read_text(encoding='utf-8'))
    assert recorded['comparator'] == 'not_evaluated' and recorded['loaded_manifest_sha256'] is None
    assert readiness.comparator()['ok'] is False
    if (REAL_BUNDLE / 'manifest.json').is_file():
        right = REAL_BUNDLE
    else:  # the real bundle is git-ignored and may be absent: pin a fixture instead
        right = tmp_path / 'right'
        monkeypatch.setattr(live_ae, 'EXPECTED_MANIFEST_SHA256', make_bundle(right, seed=1))
    monkeypatch.setenv('ARGUS_LIVE_AE_BUNDLE', str(right))
    assert live_ae.configured()['model_sha256'] == live_ae.EXPECTED_MANIFEST_SHA256
    recorded = json.loads((tmp_path / live_ae.LOADED_FILE).read_text(encoding='utf-8'))
    assert recorded['comparator'] == 'loaded' and recorded['loaded_manifest_sha256'] == live_ae.EXPECTED_MANIFEST_SHA256
    assert recorded['at_utc'] and readiness.comparator()['ok'] is True


def _parity_events():
    """Fixed synthetic persona day (13 Nov) with 12 days of history; recorded before the L14 changes."""
    arn = json.dumps({'userIdentity': {'arn': f'arn:aws:sts::{ACCOUNT}:assumed-role/argus-lab-persona-01/s'}})
    ev = [{'timestamp': f'2026-11-{d:02d}T0{1 + i % 4}:{i:02d}:00Z', 'source': 'aws_cloudtrail',
           'action': ['GetObject', 'HeadObject'][i % 2], 'resource': f'argus-lab-b{i % 3}', 'metadata': arn,
           'source_account_id': ACCOUNT, 'account_kind': 'role'} for d in range(1, 13) for i in range(3 + d % 3)]
    return ev + [{'timestamp': f'2026-11-13T1{i}:00:00Z', 'source': 'aws_cloudtrail',
                  'action': ['GetObject', 'DeleteObject', 'ListObjectsV2'][i % 3], 'resource': f'argus-lab-new{i % 4}',
                  'metadata': arn, 'source_account_id': ACCOUNT, 'account_kind': 'role'} for i in range(9)]


def test_comparator_score_unchanged(tmp_path):
    if (REAL_BUNDLE / 'manifest.json').is_file():
        bundle, expected = live_ae.load(REAL_BUNDLE), 6.238516807556152  # real v2 bundle, value before L14
    else:
        make_bundle(tmp_path / 'fx', run_kind='synthetic_contract_test')
        bundle, expected = live_ae.load(tmp_path / 'fx', allow_synthetic=True), 4.9863715171813965
    result = live_ae.score_day(bundle, 'acct_x', date(2026, 11, 13), _parity_events())
    assert result['status'] == 'scored' and result['score'] == expected


# --- 6. readiness command --------------------------------------------------------------------------------

def test_readiness_command(live, comparator, capsys):
    for body in persona_stream():
        live.post('/ingest', json=body)
    db = str(event_store.DB_PATH)
    with pytest.raises(SystemExit) as stop:
        readiness.main(['--db', db])
    out = capsys.readouterr().out
    assert stop.value.code == 1 and 'NOT READY' in out and 'events dated 13 Nov 2026 MYT or later: 0' in out
    assert 'method binding: ok' in out and 'schema columns: all present' in out and 'missing scores: 0' in out
    assert live.post('/ingest', json=persona_event('nov', '2026-11-13T02:00:00Z')).status_code == 200
    with pytest.raises(SystemExit) as stop:
        readiness.main(['--db', db])
    out = capsys.readouterr().out
    assert stop.value.code == 0 and out.strip().endswith('READY') and 'NOT' not in out
    assert f"loaded manifest sha256 {live_ae.EXPECTED_MANIFEST_SHA256} == expected" in out
    with sqlite3.connect(db) as con:
        con.execute('DELETE FROM ml_scores')
    with pytest.raises(SystemExit) as stop:
        readiness.main(['--db', db])
    assert stop.value.code == 1 and 'ml 7' in capsys.readouterr().out
