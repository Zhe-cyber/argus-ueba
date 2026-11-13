"""L10 live autoencoder v2: synthetic events only; never pilot evidence."""
from datetime import date, datetime, timedelta, timezone
import json
import math
import random
import sqlite3

import pytest

pytest.importorskip('torch')

from backend import event_store as store, live_ae
from scripts.live_daily_method import empirical_threshold

ACCOUNT, STACK = '1' * 12, 'argus-lab'  # synthetic scope
NOW = datetime(2026, 11, 13, 2, 0, tzinfo=timezone.utc)
COLS = '"user",timestamp,source,action,resource,ip_address,metadata,ingested_at,event_id,source_account_id,account_key,account_label,account_kind'
PERSONAS = ('persona-01', 'persona-02', 'persona-03')
BOT = 'acct_bot'


def aws_key(p):
    return 'acct_aws_' + p


def cf_key(p):
    return 'acct_cf_' + p


def _insert(con, rows):
    con.executemany(f'INSERT INTO events ({COLS}) VALUES ({",".join("?" * 13)})', rows)


def _events(first=date(2026, 10, 25), last=date(2026, 11, 13), seed=7):
    rng, out, n = random.Random(seed), [], 0
    day = first
    while day <= last:
        for p in PERSONAS:
            for _ in range(rng.randint(2, 6)):
                n += 1
                ts = datetime(day.year, day.month, day.day, rng.choice([1, 2, 3, 5, 8, 14]), rng.randint(0, 59),
                              tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
                arn = f'arn:aws:sts::{ACCOUNT}:assumed-role/{STACK}-{p}/session'
                out.append((p, ts, 'aws_cloudtrail', rng.choice(['GetObject', 'GetObject', 'HeadObject', 'ListObjectsV2']),
                            f'{STACK}-b{rng.randint(1, 4 if rng.random() < .9 else 9)}', '', json.dumps({'userIdentity': {'arn': arn}}),
                            ts, f'aws-{n}', ACCOUNT, aws_key(p), f'{STACK}-{p}', 'role'))
            if rng.random() < .8:
                n += 1
                ts = f'{day.isoformat()}T0{rng.randint(1, 9)}:00:00Z'
                out.append(('token', ts, 'cloudflare_access', rng.choice(['login', 'login', 'GET']),
                            f'h.workers.dev/workloads/{p}/r{rng.randint(1, 3)}', '', '{}', ts, f'cf-{n}', 'cfacct',
                            cf_key(p), f'Cloudflare service {p}', 'service_token'))
        n += 1
        ts = f'{day.isoformat()}T03:00:00Z'
        out.append(('bot', ts, 'github_events', 'push', 'repo', '', '{}', ts, f'gh-{n}', 'org', BOT, 'argus-workload-lab-x[bot]', 'account'))
        day += timedelta(days=1)
    return out


def make_db(root, extra=()):
    root.mkdir(parents=True)
    db = root / 'copy.db'
    (root / 'workspace-copy.json').write_text(json.dumps({'not_live': True, 'copy_db': str(db)}))
    saved, store.DB_PATH = store.DB_PATH, db
    try:
        store.init_db()
    finally:
        store.DB_PATH = saved
    with sqlite3.connect(db) as con:
        _insert(con, _events() + list(extra))
    return db


@pytest.fixture(scope='module')
def trained(tmp_path_factory):
    root = tmp_path_factory.mktemp('live_ae_v2')
    db = make_db(root / 'db')
    return db, live_ae.train(db, root / 'bundle', NOW, synthetic=True), root / 'bundle'


def rows_of(db, account):
    with sqlite3.connect(db) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(f'SELECT {live_ae._COLUMNS} FROM events WHERE account_key=? ORDER BY id', (account,))]


def js(p, q):
    bins = len(p)
    p = [(c + 1 / bins) / (sum(p) + 1) for c in p]
    q = [(c + 1 / bins) / (sum(q) + 1) for c in q]
    return math.sqrt(sum(0.5 * a * math.log2(2 * a / (a + b)) + 0.5 * b * math.log2(2 * b / (a + b)) for a, b in zip(p, q)))


def test_features_hand_computed_and_learning():
    days = {date(2026, 10, 1): [(22, 'aws', 'ListBuckets', 'b2')]}  # outside the 28-day window: not history
    for d in range(1, 6):
        days[date(2026, 11, d)] = [(10, 'aws', 'GetObject', 'b1')] * 2
    day = date(2026, 11, 6)
    days[day] = [(10, 'aws', 'GetObject', 'b1'), (22, 'aws', 'ListBuckets', 'b2'), (22, 'aws', 'GetObject', '')]
    got = live_ae.features(days, day)
    hours_today, hours_prior = [0] * 24, [0] * 24
    hours_today[10], hours_today[22], hours_prior[10] = 1, 2, 10
    expected = {'event_count_log': math.log1p(3), 'unique_actions': 2, 'unique_resources': 2,
                'outside_usual_hours_share': 2 / 3,  # usual hours 9-11 (hour 10 widened by 1 h)
                'new_action_count': 1, 'volume_log_ratio': math.log1p(3) - math.log1p(2), 'new_resource_share': 0.5,
                'action_mix_js_distance': js([2, 1], [10, 0]), 'hour_profile_js_distance': js(hours_today, hours_prior)}
    assert list(got['features']) == live_ae.FEATURES and got['history_days'] == 5 and got['no_resource_today'] is False
    for name, value in expected.items():
        assert got['features'][name] == pytest.approx(value, abs=1e-12), name
    days[date(2026, 11, 7)] = [(10, 'aws', 'GetObject', '')]
    quiet = live_ae.features(days, date(2026, 11, 7))
    assert quiet['no_resource_today'] is True and quiet['features']['new_resource_share'] == 0.0
    assert live_ae.features(days, date(2026, 11, 5)) is None  # 4 prior active days in the window: Learning


def test_checkpoint_rule_keeps_earliest_minimum_and_stops_after_patience():
    best, selected, stopped = math.inf, 0, None
    curve = [3.0, 2.0, 1.0, 1.0, 1.5, 1.0, 2.0, 2.0, 2.0]
    for epoch, val in enumerate(curve, 1):
        best, selected, _, stop = live_ae.checkpoint_step(best, selected, epoch, val, patience=4)
        if stop:
            stopped = epoch
            break
    assert (best, selected, stopped) == (1.0, 3, 7)  # ties never move the checkpoint


def test_split_cutoff_and_rows(trained):
    db, manifest, _ = trained
    rows, info = live_ae.dataset(db)
    assert max(r['day'] for r in rows) == '2026-11-12' and manifest['last_day_used'] == '2026-11-12'
    assert info['events_after_cutoff'] > 0  # the 13 Nov events exist and were dropped
    for r in rows:
        d = date.fromisoformat(r['day'])
        assert r['split'] == ('fit' if d <= date(2026, 11, 8) else 'validation' if d <= date(2026, 11, 10) else 'calibration')
    assert manifest['rows'] == {s: sum(r['split'] == s for r in rows) for s in live_ae.SPLITS}
    assert manifest['rows_by_provider']['calibration'] == {'aws': 6, 'cloudflare': sum(
        r['split'] == 'calibration' and r['provider'] == 'cloudflare' for r in rows)}
    assert manifest['accounts'] == {'aws': 3, 'cloudflare': 3} and manifest['parameters'] == 168
    assert 1 <= manifest['selected_epoch'] <= manifest['stop_epoch'] <= 2000
    assert manifest['purpose'] == 'product comparator, not alerting' and manifest['alerting'] is False
    with pytest.raises(live_ae.Refusal, match='waits'):
        live_ae.train(db, db.parent / 'early', datetime(2026, 11, 12, 15, 59, tzinfo=timezone.utc), synthetic=True)


def test_events_after_cutoff_never_reach_training(trained, tmp_path):
    db, manifest, _ = trained
    late = [('x', f'2026-11-1{d}T02:00:00Z', 'aws_cloudtrail', 'DeleteBucket', 'new-bucket', '',
             json.dumps({'userIdentity': {'arn': f'arn:aws:sts::{ACCOUNT}:assumed-role/{STACK}-persona-01/s'}}),
             'now', f'late-{d}', ACCOUNT, aws_key('persona-01'), 'x', 'role') for d in (3, 4)]
    other = live_ae.train(make_db(tmp_path / 'db', late), tmp_path / 'bundle', NOW, synthetic=True)
    assert other['dataset_sha256'] == manifest['dataset_sha256'] and other['artifact_sha256'] == manifest['artifact_sha256']
    assert other['events_after_cutoff'] == manifest['events_after_cutoff'] + 2


def test_training_deterministic(trained, tmp_path):
    db, manifest, _ = trained
    again = live_ae.train(db, tmp_path / 'again', NOW, synthetic=True)
    for field in ('artifact_sha256', 'threshold', 'best_validation_mse', 'selected_epoch', 'stop_epoch', 'calibration'):
        assert again[field] == manifest[field]


def test_threshold_rule_and_shares(trained):
    db, manifest, out = trained
    bundle = live_ae.load(out, allow_synthetic=True)
    rows, _ = live_ae.dataset(db)
    calibration = live_ae.reconstruction(bundle['model'], bundle['scaler'], [r['features'] for r in rows if r['split'] == 'calibration'])
    expected = empirical_threshold([s for s, _ in calibration])
    assert manifest['calibration'] == expected and manifest['threshold'] == expected['threshold']
    assert manifest['calibration_above_threshold'] == sum(s > expected['threshold'] for s, _ in calibration) <= len(calibration) // 20
    for _, shares in calibration:
        assert list(shares) == live_ae.FEATURES and sum(shares.values()) == pytest.approx(1, abs=1e-12)


def test_tampered_or_synthetic_bundle_refused(trained, tmp_path):
    _, _, out = trained
    with pytest.raises(live_ae.Refusal, match='Synthetic'):
        live_ae.load(out)
    copy = tmp_path / 'b'
    copy.mkdir()
    for name in ('manifest.json', 'weights.pt', 'scaler.json'):
        (copy / name).write_bytes((out / name).read_bytes())
    scaler = json.loads((copy / 'scaler.json').read_text())
    scaler['mean'][0] += 1e-6
    (copy / 'scaler.json').write_bytes(live_ae.canonical(scaler))
    with pytest.raises(live_ae.Refusal, match='artifact changed'):
        live_ae.load(copy, allow_synthetic=True)
    manifest = json.loads((out / 'manifest.json').read_text())
    manifest['feature_contract_sha256'] = '0' * 64
    (copy / 'manifest.json').write_bytes(live_ae.canonical(manifest))
    with pytest.raises(live_ae.Refusal, match='contract'):
        live_ae.load(copy, allow_synthetic=True)


def test_same_features_at_training_and_scoring_and_scope(trained):
    db, _, out = trained
    bundle = live_ae.load(out, allow_synthetic=True)
    rows, _ = live_ae.dataset(db)
    for provider, key in (('aws', aws_key('persona-02')), ('cloudflare', cf_key('persona-03'))):
        row = next(r for r in rows if r['account_key'] == key and r['split'] == 'calibration')
        result = live_ae.score_day(bundle, key, date.fromisoformat(row['day']), rows_of(db, key))
        assert result['status'] == 'scored' and result['provider'] == provider and result['features'] == row['features']
        (score, _), = live_ae.reconstruction(bundle['model'], bundle['scaler'], [row['features']])
        assert result['score'] == score and result['flagged'] == (score > bundle['threshold'])
    assert live_ae.score_day(bundle, BOT, date(2026, 11, 10), rows_of(db, BOT))['status'] == 'not_applicable'
    first = live_ae.score_day(bundle, aws_key('persona-01'), date(2026, 10, 27), rows_of(db, aws_key('persona-01')))
    assert first['status'] == 'not_scored' and first['reason'].startswith('Learning: 2 of 5')
    other = {**rows_of(db, aws_key('persona-01'))[0],
             'metadata': json.dumps({'userIdentity': {'arn': 'arn:aws:iam::000000000000:user/ops'}})}
    assert live_ae.scope([other]) is None


def test_backfill_store_ingest_hook_and_workspace_view(trained, tmp_path):
    _, manifest, out = trained
    db = make_db(tmp_path / 'copy')
    with sqlite3.connect(db) as con:  # a v1-era row of an account v2 does not score is dropped
        con.execute("INSERT INTO ml_scores (account_key,day,threshold,model_sha256,scored_mode,computed_at) "
                    "VALUES ('acct_old','2026-11-01',1,'x','backfill','t')")
    counts = live_ae.backfill_copy(out, db, allow_synthetic=True, now=NOW)
    assert set(counts) <= {f'{p}_{s}' for p in ('aws', 'cloudflare') for s in ('scored', 'flagged', 'not_scored')}
    assert live_ae.backfill_copy(out, db, allow_synthetic=True, now=NOW) == counts
    with sqlite3.connect(db) as con:
        assert con.execute('SELECT COUNT(DISTINCT account_key), MIN(model_version), MAX(model_version) FROM ml_scores').fetchone() == (6, 'v2', 'v2')
        assert con.execute("SELECT COUNT(*) FROM ml_scores WHERE account_key IN ('acct_old', ?)", (BOT,)).fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM ml_scores').fetchone()[0] == sum(counts.values())
        row = con.execute('SELECT * FROM ml_scores LIMIT 1').fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(f'INSERT INTO ml_scores VALUES ({",".join("?" * len(row))})', row)
    bundle = live_ae.load(out, allow_synthetic=True)
    key = cf_key('persona-02')
    saved, store.DB_PATH = store.DB_PATH, db
    try:
        assert live_ae.on_event(BOT, '2026-11-10T02:00:00Z', NOW, bundle)['status'] == 'not_applicable'
        assert live_ae.on_event(key, '2026-11-05T02:00:00Z', NOW, bundle)['status'] == 'scored'
    finally:
        store.DB_PATH = saved
    with sqlite3.connect(db) as con:  # the late event's day and every later stored day in its window were rescored
        modes = dict(con.execute('SELECT day, scored_mode FROM ml_scores WHERE account_key=?', (key,)).fetchall())
    assert all(m == ('ingest' if '2026-11-05' <= d <= '2026-12-03' else 'backfill') for d, m in modes.items())
    from workspace_next import baseline_score
    view = baseline_score.ml_view(db, key, '2026-11-11')
    assert view['status'] == 'scored' and view['model_version'] == 'v2' and view['alerting'] is False
    assert len(view['top_features']) == 3 and all(f['label'] for f in view['top_features'])
    assert baseline_score.ml_view(db, BOT, '2026-11-11')['status'] == 'not_applicable'
    with pytest.raises(live_ae.Refusal, match='marked'):
        live_ae.backfill_copy(out, out / 'manifest.json', allow_synthetic=True)


def test_v1_table_gains_v2_columns(tmp_path):
    db = tmp_path / 'old.db'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE ml_scores (account_key TEXT NOT NULL, day TEXT NOT NULL, score DOUBLE PRECISION, '
                    'flagged INTEGER, threshold DOUBLE PRECISION NOT NULL, shares_json TEXT NOT NULL DEFAULT \'{}\', '
                    'features_json TEXT NOT NULL DEFAULT \'{}\', excluded_events INTEGER NOT NULL DEFAULT 0, note TEXT, '
                    'model_sha256 TEXT NOT NULL, scored_mode TEXT NOT NULL, computed_at TEXT NOT NULL, UNIQUE (account_key, day))')
        con.execute("INSERT INTO ml_scores (account_key,day,threshold,model_sha256,scored_mode,computed_at) VALUES ('a','d',1,'x','b','t')")
    saved, store.DB_PATH = store.DB_PATH, db
    try:
        live_ae.ensure_schema()
        live_ae.ensure_schema()
    finally:
        store.DB_PATH = saved
    with sqlite3.connect(db) as con:
        assert con.execute('SELECT model_version, no_resource_today FROM ml_scores').fetchone() == ('v1', None)


def test_secondary_rule_on_all_pre_freeze_days(trained):
    db, _, out = trained
    ordered = [float(v) for v in range(1, 41)]  # n 40 -> k 2: value at index 37 (38.0), flagged only if strictly greater
    rule = empirical_threshold(list(reversed(ordered)))
    assert rule['threshold'] == 38.0 and rule['normal_alerts'] == 2
    bundle = live_ae.load(out, allow_synthetic=True)
    rows, _ = live_ae.dataset(db)
    scores = [s for s, _ in live_ae.reconstruction(bundle['model'], bundle['scaler'], [r['features'] for r in rows])]
    got = live_ae.secondary_report(db, bundle)
    assert got['n'] == len(rows) and got['k'] == len(rows) // 20
    assert got['secondary_threshold'] == sorted(scores)[len(scores) - len(scores) // 20 - 1]
    assert got['above_secondary'] == sum(s > got['secondary_threshold'] for s in scores) <= got['k']
    assert {r['split'] for r in rows} == {'fit', 'validation', 'calibration'} and got['last_day_used'] <= '2026-11-12'
    assert sum(p['days'] for p in got['by_provider'].values()) == got['n']


@pytest.mark.parametrize('body', [{}, {'secondary_threshold': 1}, {'secondary_threshold': '0.5'},
                                  {'secondary_threshold': None}, {'secondary_threshold': True}])
def test_config_without_finite_secondary_is_refused(tmp_path, monkeypatch, body, trained):
    pin = tmp_path / 'pin.json'
    pin.write_text(json.dumps({'expected_manifest_sha256': live_ae.EXPECTED_MANIFEST_SHA256, **body}))
    with pytest.raises(live_ae.Refusal, match='secondary_threshold'):
        live_ae.secondary_threshold(pin)
    monkeypatch.setattr(live_ae, 'PIN_FILE', pin)
    with pytest.raises(live_ae.Refusal, match='secondary_threshold'):
        live_ae.load(trained[2], allow_synthetic=True)
    pin.write_text('{"secondary_threshold": NaN}')
    with pytest.raises(live_ae.Refusal):
        live_ae.secondary_threshold(pin)


def test_pin_declares_the_secondary_operating_point():
    pin = json.loads(live_ae.PIN_FILE.read_text(encoding='utf-8'))
    assert live_ae.secondary_threshold() == pin['secondary_threshold'] == 0.5090951323509216
    assert '104' in pin['secondary_basis'] and pin['secondary_computed_at']
