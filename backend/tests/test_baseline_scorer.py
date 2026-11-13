"""L8: one scoring path in the backend. Method binding, independence from the business-hours setting, the
deployment sensitive list, the /ingest hook versus the backfill, stored provenance and the live user tier.
Temp SQLite and mocks only; no live data."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib
import inspect
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from backend import baseline_scorer as scorer, event_store, investigations, loader, main, rarity_scorer
from backend.tests.test_baseline_reference import CASES, compute

MYT = timezone(timedelta(hours=8))


# --- method binding ------------------------------------------------------------------------------

def test_method_binding_file_equals_running_scorer():
    bound = json.loads(scorer.METHOD_FILE.read_text(encoding='utf-8'))
    assert bound == json.loads(json.dumps(scorer.method()))
    assert scorer.METHOD_SHA256 == hashlib.sha256(scorer.METHOD_FILE.read_bytes()).hexdigest()
    assert bound['sensitive_resources_sha256'] == hashlib.sha256(scorer.SENSITIVE_FILE.read_bytes()).hexdigest()
    assert bound['reference_vectors_sha256'] == hashlib.sha256(scorer.REFERENCE_FILE.read_bytes()).hexdigest()


# --- business hours (rule only; never the baseline) ----------------------------------------------

def test_business_timezone_setting_does_not_change_any_baseline_output(monkeypatch):
    assert 'ARGUS_BUSINESS' not in inspect.getsource(scorer) and 'within_business_hours' not in inspect.getsource(scorer)
    outputs = []
    try:
        for tz in ('UTC', 'Asia/Kuala_Lumpur'):
            monkeypatch.setenv('ARGUS_BUSINESS_TZ', tz)
            importlib.reload(rarity_scorer)
            assert rarity_scorer.BUSINESS_TZ.key == tz
            outputs.append([compute(c) for c in CASES])
    finally:
        monkeypatch.delenv('ARGUS_BUSINESS_TZ')
        importlib.reload(rarity_scorer)
    assert outputs[0] == outputs[1] == [c['expected'] for c in CASES]


@pytest.fixture
def business(monkeypatch):
    def use(tz='Asia/Kuala_Lumpur', days='Mon-Fri', hours='08:00-18:00'):
        zone, allowed, minutes = rarity_scorer.parse_business_hours(tz, days, hours)
        monkeypatch.setattr(rarity_scorer, 'BUSINESS_TZ', zone)
        monkeypatch.setattr(rarity_scorer, 'BUSINESS_DAYS', allowed)
        monkeypatch.setattr(rarity_scorer, 'BUSINESS_MINUTES', minutes)
    use()
    return use


def off(local):
    """off_hours for a naive local MYT time, passed as a UTC stamp."""
    return rarity_scorer._flag_off_hours(local.replace(tzinfo=MYT).astimezone(timezone.utc).isoformat())


def test_malaysia_business_hours(business):
    assert not off(datetime(2026, 11, 12, 10))        # Thursday 10:00 MYT: inside
    assert off(datetime(2026, 11, 12, 2))             # 02:00 MYT: outside
    assert off(datetime(2026, 11, 14, 10))            # Saturday: outside
    assert not off(datetime(2026, 11, 12, 8)) and off(datetime(2026, 11, 12, 18))  # 08:00 in, 18:00 out
    assert rarity_scorer._flag_off_hours('2026-11-12T02:00:00Z') is False  # 10:00 MYT, the old UTC rule said inside too
    assert rarity_scorer._flag_off_hours('2026-11-12T11:00:00Z') is True   # 19:00 MYT; the old 07-19 UTC rule said inside


def test_midnight_wrap_and_bad_settings(business, caplog):
    business(hours='22:00-06:00', days='Mon-Sun')
    assert not off(datetime(2026, 11, 12, 23)) and not off(datetime(2026, 11, 13, 5, 59))
    assert off(datetime(2026, 11, 13, 7)) and off(datetime(2026, 11, 13, 21, 59))
    for bad in (('Mars/Base', 'Mon-Fri', '08:00-18:00'), ('UTC', 'Funday', '08:00-18:00'), ('UTC', 'Mon-Fri', '8-18')):
        with pytest.raises(ValueError):
            rarity_scorer.parse_business_hours(*bad)
    assert rarity_scorer.parse_business_hours('UTC', 'Fri-Mon', '09:00-17:00')[1] == {4, 5, 6, 0}


# --- deployment sensitive list --------------------------------------------------------------------

def test_sensitive_list_file_and_fallback(tmp_path, caplog):
    assert scorer.load_sensitive_list() == {'aws_cloudtrail': ['*-confidential', '*confidential*'],
                                            'github_events': [], 'cloudflare_access': []}
    assert scorer.load_sensitive_list(tmp_path / 'missing.json') == {}
    bad = tmp_path / 'bad.json'
    bad.write_text('{"version": 1, "providers": {"aws_cloudtrail": [""]}}')
    assert scorer.load_sensitive_list(bad) == {}
    assert 'built-in patterns only' in caplog.text


def _score(rows, deployment):
    saved = scorer._SENSITIVE
    scorer._SENSITIVE = scorer._compile(deployment)
    try:
        return scorer.score_day(scorer.group_days(rows), date(2026, 10, 20))
    finally:
        scorer._SENSITIVE = saved


def _rows(source, resource):
    hist = [[f'2026-10-{20 - d:02d}T02:00:00Z', source, 'GetObject', 'lab-p01'] for d in range(1, 7) for _ in range(4)]
    return hist + [['2026-10-20T02:00:00Z', source, 'GetObject', 'lab-p01']] * 3 + [['2026-10-20T02:00:00Z', source, 'GetObject', resource]]


def test_sensitive_list_affects_only_sensitive_new_and_only_its_provider():
    listed = scorer.load_sensitive_list()
    without, with_list = _score(_rows('aws_cloudtrail', 'argus-lab-confidential'), {}), _score(_rows('aws_cloudtrail', 'argus-lab-confidential'), listed)
    assert without['signals']['sensitive_new'] == 0.0 and with_list['signals']['sensitive_new'] == 1.0
    assert {k for k in without['signals'] if without['signals'][k] != with_list['signals'][k]} == {'sensitive_new'}
    assert with_list['tier'] == 'Medium' and any('sensitive resource' in f for f in with_list['facts'])
    other = _score(_rows('cloudflare_access', 'host/workloads/confidential'), listed)  # cloudflare list is empty
    assert other['signals']['sensitive_new'] == 0.0


# --- /ingest hook versus backfill -----------------------------------------------------------------

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


def ct(n, when, name='GetObject', bucket='lab-p01', user='persona-x'):
    return {'source': 'aws_cloudtrail', 'source_account_id': '111122223333', 'event': {
        'eventID': f'ev-{n}', 'eventTime': when, 'eventName': name, 'eventSource': 's3.amazonaws.com',
        'requestParameters': {'bucketName': bucket},
        'userIdentity': {'type': 'IAMUser', 'userName': user, 'principalId': 'AIDATESTPRINCIPAL', 'accountId': '111122223333'}}}


def stream():
    out = [ct(f'{d}-{i}', f'2026-10-{d:02d}T02:{i:02d}:00Z') for d in range(10, 17) for i in range(4)]
    out += [ct(f'r-{i}', f'2026-10-17T13:{i:02d}:00Z', 'GetObject', 'lab-confidential') for i in range(12)]  # 21:xx MYT
    out += [ct(f'l-{i}', f'2026-10-17T13:2{i}:00Z', 'GetBucketLocation', 'lab-confidential') for i in range(2)]
    out += [ct('late', '2026-10-09T03:00:00Z')]  # a new earlier active day, arriving after later days were scored
    return out


def snapshot():
    with sqlite3.connect(event_store.DB_PATH) as con:
        scores = con.execute('SELECT account_key,day,score,tier,signals_json,facts_json,history_days,events_today,'
                             'partial,rho_action,rho_resource,method_sha256 FROM baseline_scores ORDER BY 1,2').fetchall()
        alerts = [(u, d, sev, t, {k: v for k, v in json.loads(det).items() if k not in ('first_raised_at',)}, st)
                  for u, d, sev, t, det, st in con.execute(
                      "SELECT user_id,day,severity,title,details,status FROM alerts WHERE alert_type='baseline_risk' ORDER BY 1,2")]
        modes = {m for (m,) in con.execute('SELECT scored_mode FROM baseline_scores')}
        first = [json.loads(d).get('first_raised_at') for (d,) in con.execute("SELECT details FROM alerts WHERE alert_type='baseline_risk'")]
    return scores, alerts, modes, first


def test_ingest_stream_equals_backfill_and_keeps_provenance(live):
    for body in stream():
        assert live.post('/ingest', json=body).status_code == 200
    scores, alerts, modes, first = snapshot()
    assert modes == {'ingest'} and len(scores) == 9 and {r[11] for r in scores} == {scorer.METHOD_SHA256}
    # raised at Medium part-way through the evening, upgraded to High; the first-seen tier is kept
    assert [a[2] for a in alerts] == ['High'] and alerts[0][4]['first_tier'] == 'Medium' and all(first)
    scorer.backfill()
    again, alerts_again, modes_again, first_again = snapshot()
    assert again == scores and alerts_again == alerts and first_again == first  # first-seen is never overwritten
    assert modes_again == {'backfill'}
    users = live.get('/users').json()['users']
    assert users[0]['risk_level'] == 'High' and users[0]['baseline_day'] == '2026-10-17'
    assert users[0]['ae_score'] == 0.1 and users[0]['baseline_score'] == alerts[0][4]['score']
    stats = live.get('/stats').json()
    assert stats['high_risk'] == 1 and stats['high_threshold'] == 60


def test_late_event_rescores_later_days(live):
    for body in stream()[:-1]:
        live.post('/ingest', json=body)
    before = {r[1]: r for r in snapshot()[0]}
    live.post('/ingest', json=stream()[-1])
    after = {r[1]: r for r in snapshot()[0]}
    assert after['2026-10-17'][6] == before['2026-10-17'][6] + 1  # 9 Oct is now part of 17 Oct's history
    assert '2026-10-09' not in before and after['2026-10-09'][3] == 'Learning'


def test_scoring_failure_never_blocks_ingest(live, monkeypatch, caplog):
    monkeypatch.setattr(scorer, 'on_event', lambda *a, **k: 1 / 0)
    assert live.post('/ingest', json=ct('x', '2026-10-10T02:00:00Z')).status_code == 200
    assert 'Baseline score update failed: ZeroDivisionError' in caplog.text
    assert event_store.get_total_event_count(live.get('/users').json()['users'][0]['user']) == 1
