"""Entra connector with mocked HTTP only (no network, no tenant). Synthetic records, fake secret."""
import copy
from datetime import datetime, timedelta, timezone
import json
import sys
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest
import requests

from backend import baseline_scorer, event_store, investigations, loader, main
from scripts import collect_entra
from scripts.collect_entra import CollectionError, collect_entra as collect

FIXTURE = json.loads((Path(__file__).parents[2] / 'backend' / 'tests' / 'data' / 'entra_signins_synthetic.json').read_text(encoding='utf-8'))
TENANT = 'dddddddd-4444-4555-8666-777777777777'
SECRET = 'FAKE~secret.value-for-tests-only'
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}

    def json(self):
        if self._body is None:
            raise ValueError('no body')
        return self._body


class Http:
    """Scripted token POST and GET responses; records every call."""
    def __init__(self, pages, token=None):
        self.pages, self.token, self.posts, self.gets = list(pages), token or Resp(200, {'access_token': 'tok-123'}), [], []

    def post(self, url, **kw):
        self.posts.append((url, kw))
        return self.token

    def get(self, url, **kw):
        self.gets.append((url, kw))
        return self.pages.pop(0)


class Backend:
    def __init__(self):
        self.seen, self.posts, self.fail = set(), [], False

    def post(self, source, namespace, record, native_id):
        self.posts.append((source, namespace, native_id))
        if self.fail:
            return None
        dup = (source, namespace, native_id) in self.seen
        self.seen.add((source, namespace, native_id))
        return dup


@pytest.fixture
def config(tmp_path):
    secret = tmp_path / 'secret.txt'
    secret.write_text(SECRET + '\n', encoding='utf-8')
    cfg = {'tenant_id': TENANT, 'client_id': 'eeeeeeee-5555-4666-8777-888888888888',
           'client_secret_file': str(secret), 'state_file': str(tmp_path / 'state.json')}
    path = tmp_path / 'entra.json'
    path.write_text(json.dumps(cfg), encoding='utf-8')
    return collect_entra.load_config(path)


def page(records, nxt=None):
    body = {'value': copy.deepcopy(records)}
    if nxt:
        body['@odata.nextLink'] = nxt
    return Resp(200, body)


NEXT = collect_entra.SIGNINS_URL + '?$filter=createdDateTime ge 2026-10-20T00:00:00Z&$skiptoken=abc'
NOSLEEP = lambda s: None


def test_token_request_shape(config):
    http = Http([page([])])
    collect(config, Backend(), NOW, http, NOSLEEP)
    url, kw = http.posts[0]
    assert url == f'https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token'
    assert kw['data'] == {'grant_type': 'client_credentials', 'client_id': config['client_id'],
                          'client_secret': SECRET, 'scope': 'https://graph.microsoft.com/.default'}
    get_url, get_kw = http.gets[0]
    assert get_url.startswith('https://graph.microsoft.com/v1.0/auditLogs/signIns?$filter=createdDateTime ge 2026-10-20T11:00:00Z')
    assert '$top=100' in get_url and get_kw['headers'] == {'Authorization': 'Bearer tok-123'}


def test_paging_posts_each_signin_as_azure_ad_with_id(config):
    http, backend = Http([page(FIXTURE['value'][:2], NEXT), page(FIXTURE['value'][2:])]), Backend()
    counts = collect(config, backend, NOW, http, NOSLEEP)
    assert http.gets[1][0] == NEXT
    assert backend.posts == [('azure_ad', TENANT, r['id']) for r in FIXTURE['value']]
    assert counts['inserted'] == 3 and counts['requests'] == 2 and counts['drained'] and counts['retained'] == 0


def test_watermark_overlap_and_dedup(config):
    backend = Backend()
    collect(config, backend, NOW, Http([page(FIXTURE['value'])]), NOSLEEP)
    assert json.loads(Path(config['state_file']).read_text())['watermark'] == '2026-10-20T03:00:00Z'
    second = Http([page(FIXTURE['value'])])  # overlap re-delivers the same records
    counts = collect(config, backend, NOW, second, NOSLEEP)
    assert 'createdDateTime ge 2026-10-20T02:00:00Z' in second.gets[0][0]  # watermark 03:00 minus 60 min
    assert counts['duplicates'] == 3 and counts['inserted'] == 0


def test_watermark_not_advanced_on_failed_post_or_capped_backlog(config):
    failing = Backend()
    failing.fail = True
    counts = collect(config, failing, NOW, Http([page(FIXTURE['value'])]), NOSLEEP)
    assert counts['retained'] == 3 and not Path(config['state_file']).exists()
    capped = {**config, 'max_requests': 1}
    counts = collect(capped, Backend(), NOW, Http([page(FIXTURE['value'], NEXT)]), NOSLEEP)
    assert counts['requests'] == 1 and counts['drained'] is False and not Path(config['state_file']).exists()


def test_malformed_records_are_retained_not_posted(config):
    bad = [{'id': 'x'}, {'createdDateTime': '2026-10-20T00:00:00Z'}, 'nope']
    backend = Backend()
    counts = collect(config, backend, NOW, Http([page(bad)]), NOSLEEP)
    assert counts['malformed'] == 3 and backend.posts == []


def test_429_honours_retry_after_then_succeeds(config):
    sleeps = []
    http = Http([Resp(429, {}, {'Retry-After': '7'}), Resp(429, {}, {'Retry-After': '9999'}), page(FIXTURE['value'])])
    counts = collect(config, Backend(), NOW, http, sleeps.append)
    assert sleeps == [7.0, 120] and counts['inserted'] == 3 and counts['requests'] == 3


def test_429_forever_gives_up(config):
    http = Http([Resp(429, {}, {'Retry-After': '1'})] * 10)
    with pytest.raises(CollectionError, match='throttling'):
        collect(config, Backend(), NOW, http, NOSLEEP)


def test_pages_are_paced(config):
    sleeps = []
    collect(config, Backend(), NOW, Http([page([], NEXT), page([])]), sleeps.append)
    assert sleeps == [collect_entra.PACE_SECONDS]


def test_foreign_next_link_is_refused(config):
    with pytest.raises(CollectionError, match='nextLink'):
        collect(config, Backend(), NOW, Http([page([], 'https://evil.example/steal')]), NOSLEEP)


def test_secret_never_in_exceptions_logs_or_output(config, caplog, capsys, tmp_path):
    caplog.set_level('DEBUG')
    echoing = Resp(401, {'error': 'invalid_client', 'echo': SECRET})
    with pytest.raises(CollectionError) as err:
        collect(config, Backend(), NOW, Http([], token=echoing), NOSLEEP)
    assert SECRET not in str(err.value) and err.value.__cause__ is None

    class Boom(Http):
        def post(self, url, **kw):
            raise requests.ConnectionError(f'connect failed {kw["data"]["client_secret"]}')
    with pytest.raises(CollectionError) as err:
        collect(config, Backend(), NOW, Boom([]), NOSLEEP)
    assert SECRET not in str(err.value) and err.value.__cause__ is None and err.value.__context__ is None
    cfg = tmp_path / 'c.json'
    cfg.write_text(json.dumps({k: config[k] for k in ('tenant_id', 'client_id', 'client_secret_file', 'state_file')}))
    assert collect_entra.main(['check', '--config', str(cfg)]) == 0
    seen = capsys.readouterr()
    assert SECRET not in seen.out + seen.err + caplog.text and 'would call' in seen.out.lower()


def test_check_makes_no_network_call(config, tmp_path, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError('network used')
    monkeypatch.setattr(requests.Session, 'request', forbidden)
    monkeypatch.setattr(requests, 'post', forbidden)
    cfg = tmp_path / 'c.json'
    cfg.write_text(json.dumps({k: config[k] for k in ('tenant_id', 'client_id', 'client_secret_file', 'state_file')}))
    assert collect_entra.main(['check', '--config', str(cfg)]) == 0


def test_config_validation(tmp_path):
    good = {'tenant_id': TENANT, 'client_id': TENANT, 'client_secret_file': str(tmp_path / 's'), 'state_file': str(tmp_path / 'st')}
    def load(**over):
        p = tmp_path / 'x.json'
        p.write_text(json.dumps({**good, **over}))
        return collect_entra.load_config(p)
    load()
    for bad in ({'tenant_id': 'contoso.example'}, {'client_secret_file': ''}, {'max_requests': 0},
                {'page_size': '100'}, {'state_file': str(collect_entra.ROOT / 'state.json')}):
        with pytest.raises(CollectionError):
            load(**bad)
    example = collect_entra.ROOT / 'config' / 'entra.example.json'
    template = json.loads(example.read_text(encoding='utf-8'))
    if sys.platform != 'win32':  # the template's C:/ paths are Windows paths; on a POSIX CI host point them outside the repo
        template.update(client_secret_file=str(tmp_path / 'secret.txt'), state_file=str(tmp_path / 'state.json'))
    copy = tmp_path / 'example-copy.json'
    copy.write_text(json.dumps(template))
    assert collect_entra.load_config(copy)['tenant_id'] == '00000000-0000-0000-0000-000000000000'


# --- end to end: 7 synthetic days for one user -> ingest -> baseline scorer ------------------------

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
    with TestClient(main.app) as client:
        yield client


class IngestBackend:
    """Stands in for LocalBackend: posts through the real /ingest in-process."""
    def __init__(self, client):
        self.client = client

    def post(self, source, namespace, record, native_id):
        r = self.client.post('/ingest', json={'source': source, 'source_account_id': namespace, 'event': record})
        assert r.status_code == 200, r.text
        assert r.json()['event_id'] == str(native_id)
        return r.json()['duplicate']


def user_stream():
    base = FIXTURE['value'][0]
    out = []
    for day in range(14, 21):  # 14..20 Oct, 7 days, 4 sign-ins each at 10:xx MYT (02:xx UTC)
        for i in range(4):
            r = copy.deepcopy(base)
            r['id'] = f'e2e-{day}-{i}'
            r['createdDateTime'] = f'2026-10-{day:02d}T02:{i * 10:02d}:00Z'
            out.append(r)
    return out


def test_seven_day_stream_goes_learning_then_a_tier(live, config):
    records = user_stream()
    pages = [page(records[i:i + 10], NEXT if i + 10 < len(records) else None) for i in range(0, len(records), 10)]
    counts = collect(config, IngestBackend(live), NOW, Http(pages), NOSLEEP)
    assert counts['inserted'] == 28 and counts['retained'] == 0
    with sqlite3.connect(event_store.DB_PATH) as con:
        rows = con.execute('SELECT day,tier,history_days FROM baseline_scores ORDER BY day').fetchall()
        keys = {r[0] for r in con.execute('SELECT DISTINCT account_key FROM events')}
        basis = con.execute('SELECT DISTINCT account_basis FROM events').fetchall()
    assert len(keys) == 1 and basis == [('entra_user_object_id',)]
    assert [r[1] for r in rows[:5]] == ['Learning'] * 5  # fewer than 5 prior days
    assert rows[-1][1] in ('Low', 'Medium', 'High') and rows[-1][2] == 6
    latest = baseline_scorer.latest_by_account()
    assert list(latest.values())[0]['tier'] == rows[-1][1]
    again = collect(config, IngestBackend(live), NOW, Http([page(records)]), NOSLEEP)
    assert again['duplicates'] == 28 and again['inserted'] == 0  # dedup by (source, tenant, signIn id)
