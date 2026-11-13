"""L7/L7a/L7b results generator on synthetic fixtures only (temp SQLite, fake run records, fake ticks and ledgers)."""
from datetime import date, datetime, timedelta, timezone
import json
import re
import sqlite3

import pytest

pytest.importorskip('torch')

from backend import event_store as store, live_ae
from backend.tests.live_ae_fixture import make_bundle
from scripts import live_eval_report as report

ACCOUNT, STACK = '1' * 12, 'argus-lab'  # synthetic scope; must never appear in an output
MYT = timezone(timedelta(hours=8))
COLS = ('"user",timestamp,source,action,resource,ip_address,metadata,ingested_at,event_id,source_account_id,'
        'account_key,account_label,account_kind')
NOW = '2026-11-18T06:00:00+08:00'  # 12-16 Nov decided, 17 Nov pending


def aws_key(p):
    return f'acct_{p.replace("-", "")}aws'


def aws_event(p, when, bucket, rid):
    arn = f'arn:aws:sts::{ACCOUNT}:assumed-role/{STACK}-{p}/session'
    meta = json.dumps({'userIdentity': {'arn': arn}, 'requestID': rid})
    return (p, when, 'aws_cloudtrail', 'GetObject', bucket, '', meta, when, rid, ACCOUNT, aws_key(p), f'{STACK}-{p}', 'role')


def events():
    out = []
    for n in range(1, 18):
        d = date(2026, 11, n)
        if d.isoformat() in ('2026-11-14', '2026-11-15'):
            continue  # the reserved runner refused: no ordinary persona activity
        for p in ('persona-02', 'persona-04', 'persona-05'):
            out += [aws_event(p, f'{d}T02:0{i}:00Z', f'{STACK}-b{p[-1]}', f'r-{p}-{n}-{i}') for i in range(3)]
        ts = f'{d}T03:00:00Z'
        out.append(('bot', ts, 'github_events', 'push', 'repo', '', '{}', ts, f'gh-{n}', 'org', 'acct_bot',
                    'argus-workload-lab-x[bot]', 'account'))
        out.append(('svc', ts, 'aws_cloudtrail', 'Decrypt', 'key', '', '{}', ts, f'svc-{n}', ACCOUNT, 'acct_svc',
                    'cloudtrail.amazonaws.com', 'service'))
        if n >= 9:  # persona-06 Cloudflare token: Learning on 12 and 13 Nov
            out.append(('tok', ts, 'cloudflare_access', 'GET', f'h.workers.dev/workloads/persona-06/r{n}', '', '{}', ts,
                        f'cf{n:014d}', 'cfacct', 'acct_cf06', 'Cloudflare service persona-06', 'service_token'))
    out.append(aws_event('persona-04', '2026-11-14T03:00:00Z', f'{STACK}-confidential', 'REQ-S3'))  # S3
    out += [aws_event('persona-02', f'2026-11-14T13:0{i}:00Z', f'{STACK}-b2', f'REQ-S1-{i}') for i in (1, 2)]  # S1
    out.append(aws_event('persona-05', '2026-11-15T13:10:00Z', f'{STACK}-b5', 'REQ-S2a'))  # S2 attempt 1
    out.append(aws_event('persona-05', '2026-11-16T13:10:00Z', f'{STACK}-b5', 'REQ-S2b'))  # S2 attempt 2
    return out


def run_record(folder, scenario, persona, started, calls):
    rec = {'scenario': scenario, 'persona': persona, 'started_utc': started, 'finished_utc': started,
           'calls': [{'time_utc': started, 'step': 1, 'operation': 'GetObject', 'bucket': 'p0', 'status': 200,
                      'request_id': rid} for rid in calls], 'cloudflare_calls': []}
    (folder / f'run-{scenario}-{started[:19].replace(":", "")}.json').write_text(json.dumps(rec))


def tick_files(folder):
    for n in range(12, 18):
        lines = []
        start = datetime(2026, 11, n, tzinfo=MYT)
        for k in range(288):
            at = start + timedelta(minutes=5 * k)
            gap = n == 15 and 13 <= at.hour < 14  # AWS collector gap of an hour on 15 Nov
            phases = {'aws': {'ok': not gap, 'exit_code': 0 if not gap else 1, 'received': 1},
                      'cloudflare': {'ok': True, 'exit_code': 0, 'received': 3},
                      'github': {'ok': True, 'exit_code': 0, 'received': 3}}
            if n in (14, 15):
                phases['actors'] = {'ok': False, 'exit_code': 1}
            lines.append(json.dumps({'at_utc': at.astimezone(timezone.utc).isoformat(),
                                     'date_local': start.date().isoformat(), 'phases': phases, 'ok': not gap}))
        (folder / f'2026-11-{n}-ticks.jsonl').write_text('\n'.join(lines))


def ledger(path, rows, who='persona', when='observed_at'):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        con.execute(f'CREATE TABLE actions (action_id TEXT, day TEXT, {who} TEXT, status TEXT, {when} TEXT)')
        con.executemany('INSERT INTO actions VALUES (?,?,?,?,?)', rows)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / 'in'
    root.mkdir()
    db = root / 'copy.db'
    saved, store.DB_PATH = store.DB_PATH, db
    try:
        store.init_db()
    finally:
        store.DB_PATH = saved
    with sqlite3.connect(db) as con:
        con.executemany(f'INSERT INTO events ({COLS}) VALUES ({",".join("?" * 13)})', events())
        con.execute('CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY, user_id TEXT, alert_type TEXT, '
                    'severity TEXT, title TEXT, details TEXT, status TEXT, created_at TEXT, resolved_at TEXT, day TEXT)')
        con.execute("INSERT INTO alerts (user_id,alert_type,severity,title,details,status,created_at,day) VALUES "
                    "(?, 'baseline_risk', 'Medium', 't', ?, 'Open', 'x', '2026-11-14')",
                    (aws_key('persona-04'), json.dumps({'first_raised_at': '2026-11-14T03:20:00+00:00', 'first_tier': 'Medium'})))
    sha = make_bundle(tmp_path / 'bundle', threshold=-1.0)  # every scored day flagged at the primary point
    monkeypatch.setattr(live_ae, 'EXPECTED_MANIFEST_SHA256', sha)
    monkeypatch.setattr(report, 'L7A_MANIFEST_SHA256', sha)
    (root / 'live-ae-loaded.json').write_text(json.dumps({'comparator': 'loaded', 'loaded_manifest_sha256': sha}))
    (root / 'groups.json').write_text(json.dumps([{'group': 'persona-02', 'label': 'x', 'members': [aws_key('persona-02')]}]))
    runs = root / 'runs'
    runs.mkdir()
    run_record(runs, 'S3', 'persona-04', '2026-11-14T02:59:00+00:00', ['REQ-S3'])
    run_record(runs, 'S1', 'persona-02', '2026-11-14T13:00:00+00:00', ['REQ-S1-1', 'REQ-S1-2'])
    run_record(runs, 'S2', 'persona-05', '2026-11-15T13:09:00+00:00', ['REQ-S2a'])
    run_record(runs, 'S2', 'persona-05', '2026-11-16T13:09:00+00:00', ['REQ-S2b'])
    ticks = root / 'ticks'
    ticks.mkdir()
    tick_files(ticks)
    pilot = [(f'a{d}{p}{i}', f'2026-11-{d}', p, 'provider_verified', f'2026-11-{d}T05:00:00+00:00')
             for d in (12, 13) for p in ('persona-02', 'persona-04', 'persona-05') for i in range(3)]
    ops = [(f'o{d}{p}{i}', f'2026-11-{d}', p, 'provider_verified', f'2026-11-{d}T05:00:00+00:00')
           for d in (16, 17) for p in ('persona-02', 'persona-04', 'persona-05') for i in range(3)]
    ledger(root / 'pilot' / 'ledger.db', pilot)
    ledger(root / 'ops' / 'ledger.db', ops)
    (root / 'ops' / 'ops-ledger.json').write_text('{}')
    ledger(root / 'cf' / 'machine-ledger.db', [], when='verified_at')
    argv = ['--db', str(db), '--runs', str(runs), '--ticks', str(ticks), '--groups', str(root / 'groups.json'),
            '--bundle', str(tmp_path / 'bundle'), '--ledger', f'aws={root / "pilot" / "ledger.db"}',
            '--ledger', f'aws={root / "ops" / "ledger.db"}', '--ledger', f'cloudflare={root / "cf" / "machine-ledger.db"}',
            '--now', NOW]
    return argv, tmp_path


def produce(setup, name='out'):
    argv, tmp = setup
    assert report.main(argv + ['--out', str(tmp / name)]) == 0
    return json.loads((tmp / name / 'results.json').read_text()), tmp / name


def scenario(result, name):
    return next(s for s in result['scenarios'] if s['scenario'] == name)


# --- coverage rule, one condition at a time --------------------------------------------------------------

def ticks_for(points, seen_day=date(2026, 11, 20), truncated=()):
    t = {'health': {'aws': set(points), 'cloudflare': set(points)}, 'seen': {'aws': {seen_day}, 'cloudflare': {seen_day}},
         'fetches': {'cloudflare': {p: p in truncated for p in points}}, 'reserved': {}, 'files': []}
    return t


def test_condition1_gap_and_unknown():
    d = date(2026, 11, 20)
    start = datetime(2026, 11, 20, 7, tzinfo=MYT)
    every5 = [start + timedelta(minutes=5 * k) for k in range(193)]
    assert report.condition1('aws', d, ticks_for(every5))['status'] == 'passed'
    holed = [p for p in every5 if not (12 <= p.hour < 13)]
    assert report.condition1('aws', d, ticks_for(holed))['status'] == 'failed'
    assert report.condition1('aws', date(2026, 11, 21), ticks_for(every5))['status'] == 'unknown'


def test_condition2_claims_scripts_and_deadline():
    deadline = report.day_end(date(2026, 11, 14)) + timedelta(hours=24)
    ok = {'status': 'provider_verified', 'confirmed_at': '2026-11-14T05:00:00+00:00'}
    late = {'status': 'provider_verified', 'confirmed_at': '2026-11-16T00:00:00+00:00'}
    unknown = {'status': 'claimed_unknown', 'confirmed_at': None}
    assert report.condition2([ok, ok, unknown], [], deadline)['status'] == 'failed'  # 2 of 3 claimed
    assert report.condition2([ok, late], [], deadline)['status'] == 'failed'  # confirmed after 24 h
    assert report.condition2([], [{'confirmed': True}], deadline)['status'] == 'passed'  # scripted only
    assert report.condition2([ok] * 9 + [unknown], [], deadline)['status'] == 'passed'  # exactly 90%
    assert report.condition2([], [], deadline)['detail'].startswith('no claimed or scripted calls')
    assert report.condition2([ok], [], deadline, 'aws')['status'] == 'unknown'


def test_condition3_full_page_and_aws_not_applicable():
    d = date(2026, 11, 20)
    p = [datetime(2026, 11, 20, 9, tzinfo=MYT), datetime(2026, 11, 20, 10, tzinfo=MYT)]
    assert report.condition3('cloudflare', d, ticks_for(p))['status'] == 'passed'
    assert report.condition3('cloudflare', d, ticks_for(p, truncated=p[:1]))['status'] == 'failed'
    assert report.condition3('cloudflare', date(2026, 11, 21), ticks_for(p))['status'] == 'unknown'
    assert report.condition3('aws', d, ticks_for(p))['status'] == 'not_applicable'


def test_pending_until_24h_after_day_end():
    passed = {'status': 'passed', 'detail': ''}
    d = date(2026, 11, 20)
    assert report.decide(passed, passed, passed, d, datetime(2026, 11, 21, 23, 59, tzinfo=MYT))[0] == 'pending'
    assert report.decide(passed, passed, passed, d, datetime(2026, 11, 22, 0, 0, tzinfo=MYT))[0] == 'evaluable'


# --- end to end -------------------------------------------------------------------------------------------

def test_scenarios_matched_lower_repeat_and_not_run(setup):
    result, _ = produce(setup)
    s3 = scenario(result, 'S3')
    assert s3['outcome'] == 'evaluable' and s3['expected_vs_observed'][0]['result'] == 'matched'
    aws = next(a for a in s3['attempts'][0]['accounts'] if a['provider'] == 'aws')
    assert aws['tier'] == 'Medium' and aws['finding']['latency_minutes'] == 20.0
    assert aws['autoencoder']['status'] == 'scored' and len(aws['autoencoder']['top_features']) == 3
    assert aws['side_by_side'] == 'both'
    assert s3['carry_over'][0]['next_evaluable_day'] == '2026-11-16'
    s1 = scenario(result, 'S1')
    assert s1['expected_vs_observed'][0]['result'] == 'lower' and s1['group']['score'] is not None
    s2 = scenario(result, 'S2')
    first, second = s2['attempts']
    assert first['status'] == 'not evaluable' and not first['counted']
    assert second['counted'] and 'repeat' in second['note'] and 'condition 1' in second['note']
    assert scenario(result, 'S4')['outcome'] == 'not run'


def test_coverage_scripted_only_day_with_unclaimed_plan_is_evaluable(setup):
    result, out = produce(setup)
    row = next(c for c in result['coverage'] if c['day'] == '2026-11-14' and c['persona'] == 'persona-04')
    assert row['status'] == 'evaluable' and row['condition_2']['detail'].startswith('1 of 1')
    assert any('reserved runner' in x and 'refused' in x for x in result['executors_by_day']['2026-11-14'])
    assert any('ops persona runner' in x for x in result['executors_by_day']['2026-11-16'])
    assert all(c['status'] == 'pending' for c in result['coverage'] if c['day'] == '2026-11-17')
    assert (out / 'coverage.csv').read_text().count('\n2026-11-') == len(result['coverage'])


def test_normal_comparison_learning_and_excluding_12_nov(setup):
    result, _ = produce(setup)
    n = result['normal_comparison']
    cf = n['cloudflare']
    assert cf['learning_L'] == 2 and cf['tiered_denominator'] == cf['evaluable_N'] - 2
    a = n['aws']['autoencoder']
    assert a['all_days']['flagged_primary'] - a['excluding_12_nov']['flagged_primary'] == 3  # three AWS personas on 12 Nov
    assert n['all']['evaluable_N'] == n['aws']['evaluable_N'] + n['cloudflare']['evaluable_N']
    assert result['reported_separately']['infrastructure']['account_days'] > 0
    assert result['reported_separately']['github_bot']['not_evaluable'] > 0  # no GitHub ledger supplied: unknown


def test_outputs_have_no_12_digit_numbers_and_refuse_overwrite(setup):
    _, out = produce(setup)
    for name in ('results.json', 'results.md', 'coverage.csv'):
        text = (out / name).read_text()
        assert ACCOUNT not in text and not re.search(r'\d{12}', re.sub(r'[0-9a-f]{64}', '', text))
        assert report.L7_METHOD_SHA256 in text
    with pytest.raises(SystemExit, match='overwrite'):
        produce(setup)


def test_refuses_on_method_or_manifest_mismatch(setup, monkeypatch):
    monkeypatch.setattr(report, 'L7_METHOD_SHA256', '0' * 64)
    with pytest.raises(SystemExit, match='method binding'):
        produce(setup, 'm')
    monkeypatch.undo()
    with pytest.raises(SystemExit, match='manifest'):  # the fixture bundle is not the L7a manifest
        produce(setup, 'n')
    assert not (setup[1] / 'm').exists() and not (setup[1] / 'n').exists()


# --- mixed pilot + ops tick history ---------------------------------------------------------------------------

def _write_ticks(folder, day, points, provider_lines=None, pilot=False):
    folder.mkdir(parents=True, exist_ok=True)
    lines = []
    for p in points:
        at = p.astimezone(timezone.utc).isoformat()
        if pilot:
            ph = {'aws': {'ok': True, 'exit_code': 0, 'received': 0}, 'cloudflare': {'ok': True, 'exit_code': 0, 'received': 3}}
            lines.append({'at_utc': at, 'date_local': day, 'ok': True, 'phases': ph})
        else:
            lines.append({'at_utc': at, 'ok': True, 'phases': {'aws': {'ok': True, 'state': 'ran'},
                                                                'cloudflare': {'ok': True, 'state': 'not_due'}}})
            lines.append({'at_utc': at, 'provider': 'cloudflare', 'ok': True, 'received': 5, 'inserted': 1,
                          'possibly_truncated': p in (provider_lines or ()), 'error_kind': None})
    (folder / f'{day}-ticks.jsonl').write_text('\n'.join(json.dumps(x) for x in lines) + '\n')


def test_mixed_pilot_and_ops_ticks_have_no_false_gap_at_cutover(tmp_path):
    day = '2026-11-17'
    start = datetime(2026, 11, 17, 7, tzinfo=MYT)
    pilot = [start + timedelta(minutes=5 * k) for k in range(0, 61)]            # 07:00-12:00
    ops = [start + timedelta(minutes=300 + 5 * k) for k in range(1, 97)]       # 12:05-20:00
    ops += [start + timedelta(minutes=5 * k) for k in range(97 + 60, 193)]
    _write_ticks(tmp_path / 'pilot', day, pilot, pilot=True)
    _write_ticks(tmp_path / 'ops', day, ops, provider_lines=[ops[3]])
    t = report.read_ticks([tmp_path / 'pilot', tmp_path / 'ops'])
    d = date(2026, 11, 17)
    assert report.condition1('aws', d, t)['status'] == 'passed'
    assert report.condition1('cloudflare', d, t)['status'] == 'passed'
    assert report.condition3('cloudflare', d, t)['status'] == 'failed'  # the one full-page ops fetch counts


def test_ops_only_day_is_judged_from_ops_ticks(tmp_path):
    day = '2026-11-19'
    start = datetime(2026, 11, 19, 7, tzinfo=MYT)
    pts = [start + timedelta(minutes=5 * k) for k in range(193)]
    _write_ticks(tmp_path / 'ops', day, pts)
    t = report.read_ticks([tmp_path / 'ops'])
    d = date(2026, 11, 19)
    assert report.condition1('aws', d, t)['status'] == 'passed'
    assert report.condition3('cloudflare', d, t)['status'] == 'passed'
    holed = [p for p in pts if not (12 <= p.hour < 13)]
    _write_ticks(tmp_path / 'ops2', day, holed)
    assert report.condition1('aws', d, report.read_ticks([tmp_path / 'ops2']))['status'] == 'failed'
    assert report.condition1('aws', date(2026, 11, 20), t)['status'] == 'unknown'
