"""L10 live autoencoder v1 (history module backend/live_ae_v1.py): synthetic V3-shaped exports only. The product
uses v2 (test_live_ae.py); these keep the v1 bundle loadable and explainable."""
from datetime import date, datetime, timezone
import hashlib
import json
import sqlite3

import pytest

pytest.importorskip('torch')

from backend import event_store as store, live_ae_v1 as live_ae
from scripts import export_live_daily as exporter, live_daily_method as method, train_live_daily as v3
from scripts.tests.test_live_daily_export import export_study  # noqa: F401  (fixture)
from scripts.tests.test_live_daily_training import edit_data
from scripts.tests.test_live_history_readiness import ACCOUNT, NOW, STACK, study  # noqa: F401  (fixture)

GITHUB_KEY = 'acct_' + '0' * 64


def key(persona):
    return 'acct_' + hashlib.sha256(persona.encode()).hexdigest()


@pytest.fixture
def exported(export_study, tmp_path):
    path = tmp_path / 'export'
    exporter.export(*export_study, ACCOUNT, STACK, path, NOW)
    return path


def train(exported, tmp_path, name='bundle'):
    out = tmp_path / name
    return live_ae.train(exported, out, NOW, synthetic=True), out


@pytest.fixture
def copy_db(export_study, tmp_path):
    """A marked workspace copy holding the synthetic native events as backend rows, plus one GitHub account."""
    root = tmp_path / 'copy'
    root.mkdir()
    db = root / 'preview.db'
    (root / 'workspace-copy.json').write_text(json.dumps({'not_live': True, 'copy_db': str(db)}))
    saved, store.DB_PATH = store.DB_PATH, db
    try:
        store.init_db()
    finally:
        store.DB_PATH = saved
    cols = '"user",timestamp,source,action,resource,ip_address,metadata,ingested_at,event_id,source_account_id,account_key,account_label,account_kind'
    with sqlite3.connect(export_study[1]) as src, sqlite3.connect(db) as dst:
        for source, account, event_id, ts, action, resource, meta, ip in src.execute(
                'SELECT source,source_account_id,event_id,timestamp,action,resource,metadata,ip_address FROM events'):
            persona = json.loads(meta)['userIdentity']['arn'].rsplit('/', 1)[1].replace('argus-', '')
            dst.execute(f'INSERT INTO events ({cols}) VALUES ({",".join("?" * 13)})',
                        (persona, ts, source, action, resource, ip, meta, ts, event_id, account, key(persona),
                         f'{STACK}-{persona}', 'role'))
        dst.execute(f'INSERT INTO events ({cols}) VALUES ({",".join("?" * 13)})',
                    ('dev', '2026-11-10T02:00:00Z', 'github_events', 'push', 'repo', '', json.dumps({'actor_id': 7}),
                     '2026-11-10T02:00:00Z', 'gh-1', 'org', GITHUB_KEY, 'dev', 'account'))
    return db


def rows_of(db, account):
    with sqlite3.connect(db) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(f'SELECT {live_ae._COLUMNS} FROM events WHERE account_key=? ORDER BY id', (account,))]


def test_training_reproducible_architecture_and_tags(exported, tmp_path):
    first, _ = train(exported, tmp_path, 'a')
    second, _ = train(exported, tmp_path, 'b')
    for field in ('artifact_sha256', 'threshold', 'best_validation_mse', 'selected_epoch', 'calibration'):
        assert first[field] == second[field]
    assert first['ae_parameters'] == 98 and first['method']['ae_dimensions'] == [8, 4, 2, 4, 8]
    assert first['partition_rows'] == {'fit': 42, 'validation': 12, 'normal_calibration': 18}
    assert all(c == {'fit': 7, 'validation': 2, 'normal_calibration': 3} for c in first['persona_rows'].values())
    assert first['purpose'] == 'product comparator, not alerting' and first['alerting'] is False
    assert first['frozen_source_sha256'] == live_ae.frozen_hashes()
    with pytest.raises(live_ae.Refusal, match='fresh'):
        live_ae.train(exported, tmp_path / 'a', NOW, synthetic=True)


def test_threshold_is_frozen_empirical_rule_strictly_greater(exported, tmp_path):
    manifest, out = train(exported, tmp_path)
    bundle = live_ae.load(out, allow_synthetic=True)
    parts, _ = live_ae.load_export(exported, NOW)
    scores = [s for s, _ in live_ae.reconstruction(bundle['model'], bundle['scaler'], [r['features'] for r in parts['normal_calibration']])]
    expected = method.empirical_threshold(scores)
    assert manifest['calibration'] == expected and manifest['threshold'] == expected['threshold']
    above = sum(s > manifest['threshold'] for s in scores)
    assert above == expected['normal_alerts'] and above <= len(scores) // 20


def test_shares_sum_to_one_and_score_equals_frozen_score_rows(exported, tmp_path):
    _, out = train(exported, tmp_path)
    bundle = live_ae.load(out, allow_synthetic=True)
    parts, _ = live_ae.load_export(exported, NOW)
    rows = parts['validation'] + parts['normal_calibration']
    ours = live_ae.reconstruction(bundle['model'], bundle['scaler'], [r['features'] for r in rows])
    frozen = v3.score_rows(bundle['model'], bundle['scaler'], method.fit_references(parts['fit']), rows)
    assert [s for s, _ in ours] == [r['ae'] for r in frozen]
    for _, shares in ours:
        assert list(shares) == live_ae.FEATURES and sum(shares.values()) == pytest.approx(1, abs=1e-12)
        assert all(v >= 0 for v in shares.values())


def test_tampered_or_synthetic_bundle_refused(exported, tmp_path):
    _, out = train(exported, tmp_path)
    with pytest.raises(live_ae.Refusal, match='Synthetic'):
        live_ae.load(out)
    scaler = json.loads((out / 'scaler.json').read_text())
    scaler['mean'][0] += 1e-6
    (out / 'scaler.json').write_bytes(exporter.canonical(scaler))
    with pytest.raises(live_ae.Refusal, match='artifact changed'):
        live_ae.load(out, allow_synthetic=True)


def test_persona_with_fewer_than_five_fitting_rows_refused(exported, tmp_path):
    def drop(data):
        days = [r['date_local'] for r in data['rows'] if r['persona'] == 'persona-01' and r['partition'] == 'fit'][:3]
        data['rows'] = [r for r in data['rows'] if not (r['persona'] == 'persona-01' and r['date_local'] in days)]
        for r in data['readiness']['days']:
            if r['persona'] == 'persona-01' and r['day'] in days:
                r['status'] = 'incomplete'
    edit_data(exported, drop)
    with pytest.raises(live_ae.Refusal, match='fewer than 5 fitting rows: persona-01'):
        live_ae.train(exported, tmp_path / 'bundle', NOW, synthetic=True)
    assert not (tmp_path / 'bundle').exists()


def test_score_day_matches_export_vector_and_excludes_out_of_contract(exported, copy_db, tmp_path):
    _, out = train(exported, tmp_path)
    bundle = live_ae.load(out, allow_synthetic=True)
    data = json.loads((exported / 'dataset.json').read_text())
    row = next(r for r in data['rows'] if r['persona'] == 'persona-03' and r['date_local'] == '2026-11-10')
    events = rows_of(copy_db, key('persona-03'))
    result = live_ae.score_day(bundle, key('persona-03'), date(2026, 11, 10), events)
    assert result['status'] == 'scored' and result['features'] == row['features'] and result['excluded_events'] == 0
    expected, = live_ae.reconstruction(bundle['model'], bundle['scaler'], [row['features']])
    assert result['score'] == expected[0] and result['flagged'] == (expected[0] > bundle['threshold'])
    denied = {**events[-1], 'timestamp': '2026-11-10T03:00:00Z', 'action': 'ListObjectsV2',
              'metadata': json.dumps({**json.loads(events[-1]['metadata']), 'errorCode': 'AccessDenied'})}
    again = live_ae.score_day(bundle, key('persona-03'), date(2026, 11, 10), events + [denied])
    assert again['features'] == row['features'] and again['excluded_events'] == 1


def test_non_persona_accounts_not_applicable(exported, copy_db, tmp_path):
    _, out = train(exported, tmp_path)
    bundle = live_ae.load(out, allow_synthetic=True)
    github = live_ae.score_day(bundle, GITHUB_KEY, date(2026, 11, 10), rows_of(copy_db, GITHUB_KEY))
    assert github['status'] == 'not_applicable'
    event = rows_of(copy_db, key('persona-01'))[0]
    other = {**event, 'metadata': json.dumps({'userIdentity': {'type': 'IAMUser', 'arn': 'arn:aws:iam::000000000000:user/ops'}})}
    assert live_ae.persona_scope([other]) is None


def test_store_backfill_unique_guard_and_ingest_hook(exported, copy_db, tmp_path):
    _, out = train(exported, tmp_path)
    first = live_ae.backfill_copy(out, copy_db, allow_synthetic=True, now=NOW)
    assert sum(first.values()) == 72 and first.get('not_scored', 0) == 0
    assert live_ae.backfill_copy(out, copy_db, allow_synthetic=True, now=NOW) == first
    with sqlite3.connect(copy_db) as con:
        assert con.execute('SELECT COUNT(*), COUNT(DISTINCT account_key) FROM ml_scores').fetchone() == (72, 6)
        row = con.execute('SELECT * FROM ml_scores LIMIT 1').fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(f'INSERT INTO ml_scores VALUES ({",".join("?" * len(row))})', row)
    bundle = live_ae.load(out, allow_synthetic=True)
    saved, store.DB_PATH = store.DB_PATH, copy_db
    try:
        assert live_ae.on_event(GITHUB_KEY, '2026-11-10T02:00:00Z', NOW, bundle)['status'] == 'not_applicable'
        assert live_ae.on_event(key('persona-02'), '2026-11-09T02:00:00Z', NOW, bundle)['status'] == 'scored'
    finally:
        store.DB_PATH = saved
    with sqlite3.connect(copy_db) as con:
        assert con.execute('SELECT COUNT(*) FROM ml_scores').fetchone()[0] == 72
        assert con.execute("SELECT scored_mode FROM ml_scores WHERE account_key=? AND day='2026-11-09'",
                           (key('persona-02'),)).fetchone()[0] == 'ingest'
    with pytest.raises(live_ae.Refusal, match='marked'):
        live_ae.backfill_copy(out, exported / 'dataset.json', allow_synthetic=True)


def test_pipeline_end_to_end_on_synthetic_pilot(export_study, copy_db, tmp_path):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'ledger_dir': str(export_study[0].parent), 'connected_dir': str(export_study[1].parent),
                                  'account_id': ACCOUNT, 'stack': STACK}))
    with pytest.raises(live_ae.Refusal, match='waits'):
        live_ae.pipeline(config, tmp_path / 'early', now=datetime(2026, 11, 12, 16, 29, tzinfo=timezone.utc))
    assert not (tmp_path / 'early').exists()
    result = live_ae.pipeline(config, tmp_path / 'live-ae', demo_db=copy_db, now=NOW, synthetic=True)
    assert result['partition_rows'] == {'fit': 42, 'validation': 12, 'normal_calibration': 18}
    assert result['selected_epoch'] >= 1 and len(result['model_sha256']) == 64 and result['excluded_rows'] == 0
    assert sum(result['demo_backfill'].values()) == 72
    assert ACCOUNT not in json.dumps(result)
    from workspace_next import baseline_score  # the workspace shows v2 rows only; v1 rows are history
    assert baseline_score.ml_view(copy_db, key('persona-04'), '2026-11-11')['status'] == 'not_scored'
    with sqlite3.connect(copy_db) as con:
        assert {r[0] for r in con.execute('SELECT model_version FROM ml_scores')} == {'v1'}
