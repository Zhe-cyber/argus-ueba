"""Results generator for the pre-registered live evaluation (specs/L7-live-evaluation-rules.md, the comparator
addendum specs/L7a-autoencoder-comparator-addendum.md and the coverage clarification specs/L7b-coverage-clarification.md).
OWNER-RUN, once, after the last scenario. Read-only on every input; writes only into a fresh --out folder.

    python scripts/live_eval_report.py --db <events DB copy> --runs <data/live/demo-scenario> \
        --ticks <pilot state dir> --ticks <ops status dir> --groups <workload-groups.json> \
        --bundle <pinned v2 bundle> --ledger aws=<ledger.db> --ledger cloudflare=<machine-ledger.db> \
        --ledger github=<machine-ledger.db> [--ledger aws=<ops ledger.db> --ledger cloudflare=<ops cloudflare-ledger.db>] \
        --out <new folder> [--window-end 2026-11-22] [--now <ISO time>]

Every evaluation number is recomputed here in 'backfill' mode from the stored events with the frozen method
(backend.baseline_scorer.score_day, backend.live_ae._score); stored ingest rows and findings are reported beside them
for alert timing only. Refuses when the method binding or the comparator manifest differs from L7 / L7a.
Guide: docs/LIVE_EVAL_REPORT.md.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend import baseline_scorer as bs, live_ae  # noqa: E402
from scripts.demo_scenario_live import SCENARIOS  # noqa: E402  the L7 section 2 table, single source
from workspace_next import system_accounts  # noqa: E402
from workspace_next.workload_groups import combine  # noqa: E402  the S1 group-score rule

# L7 section 8 was left "(filled at commit)": the binding file's sha256 at the L7 pre-registration commit 0959fc0
# (file unchanged since a34a8ec). L7a section 3: the model manifest sha256.
L7_METHOD_SHA256 = '4a44bb1602cb5297ce1ecfd2ca0d3651ad0c12b94cfb2d43777e58abd27eb3f2'
L7A_MANIFEST_SHA256 = 'd41e86a92cc24e6db706b161caef780a10d54f5f7c82592bcd7da6f2d7a2ffc0'
MYT = bs.MYT
WINDOW_START, SCENARIO_START, CALIBRATION_DAY = date(2026, 11, 12), date(2026, 11, 14), date(2026, 11, 12)
RESERVED_DAYS = ('2026-11-14', '2026-11-15')  # the closed V3 reserved runner's days (L7b)
GAP_LIMIT, ACTIVE_HOURS, PAGE, DECIDE_AFTER = timedelta(minutes=30), (7, 23), 100, timedelta(hours=24)
PROVIDERS, BOUNDED = ('aws', 'cloudflare', 'github'), ('cloudflare', 'github')
PROVIDER_OF = {'aws_cloudtrail': 'aws', 'cloudflare_access': 'cloudflare', 'github_events': 'github'}
BOT = re.compile(r'argus-workload-lab-.*\[bot\]')
TIERS = {'Low': 0, 'Medium': 1, 'High': 2}
SPECS = ('specs/L7-live-evaluation-rules.md', 'specs/L7a-autoencoder-comparator-addendum.md',
         'specs/L7b-coverage-clarification.md')
AMBIGUITIES = [
    'L7 section 8 records no method sha256 ("filled at commit"); the expected value is the sha256 of '
    'config/baseline_method_v1_2.json at the L7 pre-registration commit 0959fc0 (the file is unchanged since a34a8ec).',
    'Condition 1 (collector gap): a provider is "running" at each tick/status record whose provider entry is ok '
    '(a fresh successful fetch, or not-due after a successful one); gaps are measured between such points with 07:00 '
    'and 23:00 MYT as boundaries. A provider-day with no tick/status record at all is "unknown" (not evaluable).',
    'Condition 2: planned calls = executor-ledger rows (L7b) incl. rows recorded as "missed" (counted, not confirmed) '
    'plus scenario run-record calls. Confirmed = ledger status provider_verified with its verification time, or a '
    'matching stored event (AWS requestID / Cloudflare ray ID, same account) ingested, both no later than 24 h after '
    'the day ends. A persona or GitHub-bot day with no ledger of its provider supplied is "unknown". A day with zero '
    'planned or scripted calls passes condition 2 vacuously (listed as such).',
    'Condition 3: AWS (SQS queue, no page) is not applicable; for GitHub/Cloudflare a provider-day with no recorded '
    'fetch is "unknown". The fetch is attributed to the MYT day it ran on.',
    'Scenario account-days are the accounts the scenario is designed to touch (S1: AWS role and Cloudflare token of '
    'persona-02; S2-S4: the AWS role), for every attempt, whether or not the calls succeeded; they are excluded from '
    'the normal comparison. The Cloudflare account of S2-S4 personas is reported beside the scenario but is a normal day.',
    'Repeat rule: an attempt is evaluable only if all its scenario account-days are; attempt 2 is a permitted repeat '
    'only if attempt 1 (in the window) was not evaluable; any other repeat is reported and not counted.',
    'Expected vs observed compares the AWS account-day tier (every scenario acts on its AWS role); for S1 the '
    'Cloudflare account and the group score are compared too, as additional rows.',
    'Latency is measured from the first provider-confirmed scenario event of the attempt (any account) to the '
    "finding's first_raised_at; a finding first raised before the run started is reported as pre-existing.",
    "The comparator counts are withheld (reported as not evaluated) unless the deployment's loaded-manifest record "
    '(live-ae-loaded.json) shows the pinned manifest (L7a section 2.3).',
]


class Refusal(Exception):
    """An input does not meet the pre-registered rules; nothing is written."""


# --- small helpers ----------------------------------------------------------------------------------------

def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stamp(value):
    """Aware datetime or None."""
    try:
        t = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else None


def myt(t):
    return t.astimezone(MYT).date()


def day_end(d):
    return datetime.combine(d + timedelta(days=1), time(0), MYT)


def days_between(lo, hi):
    return [lo + timedelta(days=i) for i in range((hi - lo).days + 1)]


def ro(path):
    con = sqlite3.connect(f'file:{Path(path).resolve(strict=True).as_posix()}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


def columns(con, table):
    return {r['name'] for r in con.execute(f'PRAGMA table_info({table})')}


def rounded(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):  # '_'-prefixed keys are internal (account keys) and never written
        return {k: rounded(v) for k, v in value.items() if not str(k).startswith('_')}
    if isinstance(value, (list, tuple)):
        return [rounded(v) for v in value]
    return value


_HEX64 = re.compile(r'[0-9a-f]{64}')
_EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
_IPV4 = re.compile(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])')


def scrub(text):
    """No 12-digit numbers, e-mail addresses or IPv4 addresses (sha256 hex tokens are left intact)."""
    def clean(part):
        return _IPV4.sub('<ip>', _EMAIL.sub('<email>', re.sub(r'\d{12,}', '<number>', part)))
    parts, hexes = _HEX64.split(text), _HEX64.findall(text)
    return ''.join(clean(p) + (hexes[i] if i < len(hexes) else '') for i, p in enumerate(parts))


# --- frozen method and comparator -------------------------------------------------------------------------

def verify_method():
    actual = sha_file(bs.METHOD_FILE)
    if actual != L7_METHOD_SHA256 or bs.METHOD_SHA256 != L7_METHOD_SHA256:
        raise Refusal(f'method binding sha256 {actual} differs from the L7 pre-registered {L7_METHOD_SHA256}; '
                      'the evaluation must be scored with method v1.2 as frozen')
    if not bs.STATUS['scoring_ready']:
        raise Refusal(f"method binding does not match the running scorer: {bs.STATUS['reason']}")
    return {'method_sha256': actual, 'version': bs.VERSION, 'status': bs.STATUS['reason']}


def verify_comparator(bundle_dir, loaded_path):
    manifest = Path(bundle_dir) / 'manifest.json'
    if not manifest.is_file():
        raise Refusal('comparator bundle has no manifest.json')
    actual = sha_file(manifest)
    if actual != L7A_MANIFEST_SHA256 or live_ae.EXPECTED_MANIFEST_SHA256 != L7A_MANIFEST_SHA256:
        raise Refusal(f'comparator manifest sha256 {actual} (pin {live_ae.EXPECTED_MANIFEST_SHA256}) differs from the '
                      f'L7a pre-registered {L7A_MANIFEST_SHA256}')
    try:
        bundle = live_ae.load(bundle_dir)
    except live_ae.Refusal as error:
        raise Refusal(f'comparator bundle refused: {error}') from error
    try:
        loaded = json.loads(Path(loaded_path).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        loaded = {}
    ok = loaded.get('comparator') == 'loaded' and loaded.get('loaded_manifest_sha256') == L7A_MANIFEST_SHA256
    state = {'manifest_sha256': actual, 'primary_threshold': bundle['threshold'],
             'secondary_threshold': bundle['secondary_threshold'],
             'deployment_loaded_manifest_sha256': loaded.get('loaded_manifest_sha256'),
             'deployment_loaded_at_utc': loaded.get('at_utc'), 'status': 'evaluated' if ok else 'not_evaluated',
             'reason': None if ok else ('no loaded-manifest record' if not loaded else
                                        'the deployment loaded-manifest record is not the pinned manifest')}
    return bundle, state


# --- inputs -----------------------------------------------------------------------------------------------

EVENT_COLUMNS = ('account_key', 'account_label', 'account_kind', 'timestamp', 'source', 'action', 'resource',
                 'metadata', 'source_account_id', 'ingested_at', 'event_id')


def read_db(db):
    con = ro(db)
    try:
        missing = [c for c in EVENT_COLUMNS if c not in columns(con, 'events')]
        if missing:
            raise Refusal('events table lacks columns: ' + ', '.join(missing))
        accounts = defaultdict(list)
        for r in con.execute(f"SELECT {','.join(EVENT_COLUMNS)} FROM events WHERE account_key IS NOT NULL ORDER BY id"):
            accounts[r['account_key']].append(dict(r))
        stored = {'alerts': {}, 'baseline': {}, 'ml': {}}
        if {'user_id', 'alert_type', 'day', 'details'} <= columns(con, 'alerts'):
            for r in con.execute("SELECT user_id,day,severity,status,details FROM alerts WHERE alert_type='baseline_risk'"):
                stored['alerts'][(r['user_id'], r['day'])] = dict(r)
        if {'account_key', 'day', 'scored_mode'} <= columns(con, 'baseline_scores'):
            for r in con.execute('SELECT account_key,day,score,tier,scored_mode,method_sha256 FROM baseline_scores'):
                stored['baseline'][(r['account_key'], r['day'])] = dict(r)
        if {'account_key', 'day', 'model_version'} <= columns(con, 'ml_scores'):
            for r in con.execute("SELECT * FROM ml_scores WHERE model_version='v2'"):
                stored['ml'][(r['account_key'], r['day'])] = dict(r)
    finally:
        con.close()
    return accounts, stored


def classify(accounts, declared):
    out = {}
    for key, events in accounts.items():
        first = events[0]
        label, kind, source = first['account_label'], first['account_kind'], first['source']
        found = live_ae.scope(events)
        if found:
            cls, provider, persona = 'persona', found[0], found[1]
        else:
            provider, persona = PROVIDER_OF.get(source, source), None
            if source == 'github_events' and BOT.fullmatch(label or ''):
                cls = 'github_bot'
            elif system_accounts.is_infrastructure(label, kind, source, declared):
                cls = 'infrastructure'
            else:
                cls = 'other'
        out[key] = {'key': key, 'label': label or key[:13], 'source': source, 'provider': provider,
                    'persona': persona, 'class': cls, 'scope': found}
    return out


def read_ticks(folders):
    """Collector health points, days with any record, fetch outcomes, and the reserved runner's actor phases."""
    t = {'health': defaultdict(set), 'seen': defaultdict(set), 'fetches': defaultdict(dict),
         'reserved': defaultdict(list), 'files': []}
    for folder in folders:
        for path in sorted(Path(folder).glob('*.jsonl')) + sorted(Path(folder).glob('ops-status*.json')):
            text = path.read_text(encoding='utf-8-sig')
            docs = []
            for line in (text.splitlines() if path.suffix == '.jsonl' else [text]):
                try:
                    docs.append(json.loads(line))
                except ValueError:
                    continue
            used = False
            for doc in docs:
                at = stamp(doc.get('at_utc')) if isinstance(doc, dict) else None
                if at is None:
                    continue
                if doc.get('provider') in PROVIDERS and 'phases' not in doc:  # ops per-provider fetch line
                    used = True
                    _ops_fetch(t, doc, at)
                elif isinstance(doc.get('phases'), dict):
                    used = True
                    _pilot_tick(t, doc, at)
                elif doc.get('schema') == 'argus_ops_status_v1' and isinstance(doc.get('providers'), dict):
                    used = True
                    _ops_status(t, doc, at)
            if used:
                t['files'].append(path)
    return t


def _fetch(t, provider, when, truncated):
    t['fetches'][provider][when] = t['fetches'][provider].get(when, False) or truncated
    t['seen'][provider].add(myt(when))


def _ops_fetch(t, doc, at):
    p = doc['provider']
    _fetch(t, p, at, p in BOUNDED and (doc.get('possibly_truncated') is True or int(doc.get('received') or 0) >= PAGE))


def _pilot_tick(t, doc, at):
    phases = doc['phases']
    for p in PROVIDERS:
        ph = phases.get(p)
        if not isinstance(ph, dict):
            continue
        t['seen'][p].add(myt(at))
        if ph.get('ok') is True:
            t['health'][p].add(at)
        if 'exit_code' in ph and not str(ph.get('status', '')).startswith('not_due'):
            _fetch(t, p, at, p in BOUNDED and int(ph.get('received') or 0) >= PAGE)
    if doc.get('date_local') in RESERVED_DAYS and isinstance(phases.get('actors'), dict):
        t['reserved'][doc['date_local']].append(phases['actors'].get('ok') is True)


def _ops_status(t, doc, at):
    for p, e in doc['providers'].items():
        if p not in PROVIDERS or not isinstance(e, dict) or e.get('state') in ('disabled', 'not_started'):
            continue
        t['seen'][p].add(myt(at))
        run, last_ok = stamp(e.get('last_run_utc')), stamp(e.get('last_ok_utc'))
        if e.get('ok') is True:
            t['health'][p].add(run if e.get('state') == 'ran' and run else at)
        if last_ok:
            t['health'][p].add(last_ok)
            t['seen'][p].add(myt(last_ok))
        if run:
            _fetch(t, p, run, p in BOUNDED and bool(e.get('possibly_truncated')))


LEDGER_COLUMNS = {'aws': ('persona', 'observed_at'), 'cloudflare': ('persona', 'verified_at'),
                  'github': ('profile', 'verified_at')}


def read_ledgers(specs):
    """[(kind, path)] -> claims [{kind, executor, day, who, status, confirmed_at}]."""
    claims = []
    for kind, path in specs:
        who, when = LEDGER_COLUMNS[kind]
        con = ro(path)
        try:
            if not {'day', who, 'status', when} <= columns(con, 'actions'):
                raise Refusal(f'{kind} ledger {Path(path).name} lacks the expected actions columns')
            executor = ('ops persona runner' if (Path(path).parent / 'ops-ledger.json').is_file() else 'pilot actor') + f' ({kind})'
            for r in con.execute(f'SELECT day,{who} AS who,status,{when} AS confirmed_at FROM actions'):
                claims.append({'kind': kind, 'executor': executor, **dict(r)})
        finally:
            con.close()
    return claims


def read_runs(folder):
    runs = []
    for path in sorted(Path(folder).glob('run-*.json')):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
            started = stamp(record['started_utc'])
        except (OSError, ValueError, KeyError, TypeError):
            raise Refusal(f'unreadable scenario run record {path.name}')
        if started is None or record.get('scenario') not in SCENARIOS:
            raise Refusal(f'scenario run record {path.name} has no valid scenario or start time')
        runs.append({**record, 'file': path.name, 'started': started, 'day': myt(started)})
    return sorted(runs, key=lambda r: r['started'])


# --- coverage (L7 section 3, L7b) -------------------------------------------------------------------------

def condition1(provider, d, ticks):
    if d not in ticks['seen'][provider]:
        return {'status': 'unknown', 'detail': f'no collector tick/status record for {provider} that day'}
    start, end = (datetime.combine(d, time(h), MYT) for h in ACTIVE_HOURS)
    points = [start, *sorted(x for x in ticks['health'][provider] if start < x < end), end]
    gap = max(b - a for a, b in zip(points, points[1:]))
    return {'status': 'passed' if gap <= GAP_LIMIT else 'failed',
            'detail': f'longest gap 07:00-23:00 MYT: {gap.total_seconds() / 60:.0f} min'}


def condition3(provider, d, ticks):
    if provider == 'aws':
        return {'status': 'not_applicable', 'detail': 'AWS is read from a queue (no bounded page)'}
    if provider not in BOUNDED:
        return {'status': 'unknown', 'detail': f'no fetch records for {provider}'}
    fetched = [tr for when, tr in ticks['fetches'][provider].items() if myt(when) == d]
    if not fetched:
        return {'status': 'unknown', 'detail': f'no recorded {provider} fetch that day'}
    full = sum(fetched)
    return {'status': 'failed' if full else 'passed',
            'detail': f'{full} of {len(fetched)} fetches returned a full page of {PAGE}'}


def claim_confirmed(claim, deadline):
    when = stamp(claim.get('confirmed_at'))
    return claim.get('status') == 'provider_verified' and when is not None and when <= deadline


def condition2(claims, scripted, deadline, ledger_missing=None):
    if ledger_missing:
        return {'status': 'unknown', 'detail': f'no {ledger_missing} executor ledger supplied', 'planned': None,
                'confirmed': None}
    planned = len(claims) + len(scripted)
    confirmed = sum(claim_confirmed(c, deadline) for c in claims) + sum(bool(s['confirmed']) for s in scripted)
    if not planned:
        return {'status': 'passed', 'detail': 'no claimed or scripted calls (vacuous)', 'planned': 0, 'confirmed': 0}
    return {'status': 'passed' if confirmed * 10 >= planned * 9 else 'failed',
            'detail': f'{confirmed} of {planned} planned or scripted calls provider-confirmed within 24 h',
            'planned': planned, 'confirmed': confirmed}


def decide(c1, c2, c3, d, now):
    if now < day_end(d) + DECIDE_AFTER:
        return 'pending', []
    failed = [f'condition {n}: {c["status"]} ({c["detail"]})' for n, c in ((1, c1), (2, c2), (3, c3))
              if c['status'] not in ('passed', 'not_applicable')]
    return ('not evaluable' if failed else 'evaluable'), failed


def native_index(accounts):
    aws, cf = defaultdict(list), defaultdict(list)
    for key, events in accounts.items():
        for e in events:
            if e['source'] == 'aws_cloudtrail':
                rid = live_ae._meta(e).get('requestID')
                if rid:
                    aws[str(rid)].append((key, e))
            elif e['source'] == 'cloudflare_access' and e['event_id']:
                cf[str(e['event_id']).lower()].append((key, e))
    return {'aws': aws, 'cloudflare': cf}


def scripted_calls(run, provider, keys, index):
    """The run record's calls for one provider, each matched to a stored event of the attacked account."""
    deadline = day_end(run['day']) + DECIDE_AFTER
    out = []
    for c in run.get('calls' if provider == 'aws' else 'cloudflare_calls') or []:
        rid = str(c.get('request_id') or '')
        rid = rid.lower() if provider == 'cloudflare' else rid
        matches = [e for k, e in index[provider].get(rid, []) if k in keys] if rid else []
        ok = [e for e in matches if (s := stamp(e['ingested_at'])) is not None and s <= deadline]
        out.append({'time_utc': c.get('time_utc'), 'operation': c.get('operation'),
                    'target': c.get('bucket') or c.get('path'), 'status': c.get('status'),
                    'error_code': c.get('error_code'), 'confirmed': bool(ok),
                    'event_time': min((stamp(e['timestamp']) for e in ok), default=None)})
    return out


# --- scoring (backfill, frozen method) --------------------------------------------------------------------

def backfill(accounts, info, bundle, lo, hi):
    """{(key, day): {'baseline': score_day result, 'ae': live_ae result or None}} for days with events in [lo, hi]."""
    out = {}
    for key, events in accounts.items():
        days = bs.group_days([(e['timestamp'], e['source'], e['action'], e['resource']) for e in events])
        for d in sorted(x for x in days if lo <= x <= hi):
            ae = live_ae._score(bundle, key, info[key]['scope'], days, d) if info[key]['class'] == 'persona' else None
            out[(key, d)] = {'baseline': bs.score_day(days, d), 'ae': ae}
    return out


def ae_view(ae, comparator):
    if ae is None:
        return None
    if comparator['status'] != 'evaluated':
        return {'status': 'not_evaluated', 'reason': comparator['reason']}
    if ae['status'] != 'scored':
        return {'status': ae['status'], 'reason': ae.get('reason')}
    top = sorted(ae['shares'].items(), key=lambda kv: -kv[1])[:3]
    return {'status': 'scored', 'score': ae['score'], 'flagged_primary': ae['flagged'],
            'flagged_secondary': ae['flagged_secondary'],
            'top_features': [{'feature': f, 'label': live_ae.LABELS[f], 'share': s} for f, s in top]}


def compare(expected, tier):
    if tier not in TIERS:
        return f'not comparable ({tier})'
    allowed = [TIERS[x] for x in expected.split(' or ')]
    value = TIERS[tier]
    return 'matched' if value in allowed else 'higher' if value > max(allowed) else 'lower'


def side_by_side(tier, ae):
    if tier not in TIERS:
        return f'baseline {tier}'
    if not ae or ae.get('status') != 'scored':
        return 'autoencoder not scored' if ae else 'autoencoder not applicable'
    alert = tier in ('Medium', 'High')
    return {(True, True): 'both', (True, False): 'baseline only', (False, True): 'autoencoder only',
            (False, False): 'neither'}[(alert, bool(ae['flagged_primary']))]


# --- the report -------------------------------------------------------------------------------------------

def build(args, now):
    method = verify_method()
    bundle, comparator = verify_comparator(args.bundle, args.loaded)
    accounts, stored = read_db(args.db)
    info = classify(accounts, system_accounts.declared(args.db))
    ticks = read_ticks(args.ticks)
    claims = read_ledgers(args.ledger)
    runs = read_runs(args.runs)
    groups = json.loads(Path(args.groups).read_text(encoding='utf-8'))
    index = native_index(accounts)
    lo, hi = WINDOW_START, args.window_end
    scores = backfill(accounts, info, bundle, lo, hi)
    by_persona = defaultdict(list)
    for key, a in info.items():
        if a['class'] == 'persona':
            by_persona[(a['provider'], a['persona'])].append(key)
    bots = [k for k, a in info.items() if a['class'] == 'github_bot']
    kinds = {k for k, _ in args.ledger}

    # scripted calls and scenario account-days
    scripted = defaultdict(list)          # (key, day) -> calls
    designed = set()                      # scenario account-days (key, day)
    for run in runs:
        plan = SCENARIOS[run['scenario']]
        for provider in ('aws', 'cloudflare'):
            keys = by_persona.get((provider, run['persona']), [])
            calls = scripted_calls(run, provider, keys, index)
            run.setdefault('scripted', {})[provider] = calls
            if provider == 'aws' or plan['cloudflare']:
                for key in keys:
                    designed.add((key, run['day']))
                    scripted[(key, run['day'])] += calls

    planned = defaultdict(list)           # (key, day) -> ledger claims
    for c in claims:
        targets = bots if c['kind'] == 'github' else by_persona.get((c['kind'], c['who']), [])
        for key in targets:
            planned[(key, date.fromisoformat(str(c['day'])[:10]))].append(c)

    cells = {k for k in scores} | {k for k in designed | set(planned) if lo <= k[1] <= hi}
    coverage = {}
    for key, d in sorted(cells, key=lambda kd: (kd[1], info[kd[0]]['label'])):
        a = info[key]
        missing = None
        if a['class'] == 'persona' and a['provider'] not in kinds:
            missing = a['provider']
        elif a['class'] == 'github_bot' and 'github' not in kinds:
            missing = 'github'
        c1, c3 = condition1(a['provider'], d, ticks), condition3(a['provider'], d, ticks)
        c2 = condition2(planned[(key, d)], scripted[(key, d)], day_end(d) + DECIDE_AFTER, missing)
        status, failed = decide(c1, c2, c3, d, now)
        coverage[(key, d)] = {'day': d.isoformat(), 'account': a['label'], 'class': a['class'],
                              'provider': a['provider'], 'persona': a['persona'], 'has_events': (key, d) in scores,
                              'scenario_account_day': (key, d) in designed, 'status': status, 'failed': failed,
                              'condition_1': c1, 'condition_2': c2, 'condition_3': c3}

    scenarios = scenario_section(runs, by_persona, groups, info, scores, coverage, stored, comparator, hi)
    normal = normal_section(coverage, scores, info, comparator, designed, scenarios)
    executors = executor_section(claims, ticks, runs, lo, hi)
    files = [('db', args.db), ('groups', args.groups), ('bundle manifest', Path(args.bundle) / 'manifest.json')]
    files += [('loaded-manifest record', args.loaded)] if Path(args.loaded).is_file() else []
    files += [('system accounts', Path(args.db).resolve().parent / system_accounts.FILE)] \
        if (Path(args.db).resolve().parent / system_accounts.FILE).is_file() else []
    files += [(f'{k} ledger', p) for k, p in args.ledger] + [('run record', Path(args.runs) / r['file']) for r in runs]
    files += [('tick/status record', p) for p in ticks['files']] + [('rules', ROOT / s) for s in SPECS]
    meta = {'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'now_used': now.isoformat(),
            'window': [lo.isoformat(), hi.isoformat()], 'method_sha256': method['method_sha256'],
            'method_version': method['version'], 'manifest_sha256': comparator['manifest_sha256'],
            'comparator_status': comparator['status'], 'mode': 'backfill (recomputed from stored events)',
            'script_git_commit': git_commit(), 'script_sha256': sha_file(__file__),
            'rules': list(SPECS),
            'input_files': [{'role': role, 'name': Path(p).name, 'sha256': sha_file(p)} for role, p in files]}
    return {'meta': meta, 'method': method, 'comparator': comparator, 'ambiguities_resolved': AMBIGUITIES,
            'executors_by_day': executors, 'coverage': list(coverage.values()), 'scenarios': scenarios,
            'normal_comparison': normal['persona'], 'reported_separately': normal['separate']}


def account_result(key, d, info, scores, coverage, stored, comparator, run, first_event):
    cell = scores.get((key, d))
    base = cell['baseline'] if cell else {'score': None, 'tier': 'No activity', 'signals': {}, 'facts': []}
    cov = coverage.get((key, d), {})
    alert = stored['alerts'].get((key, d.isoformat()))
    finding = None
    if alert:
        details = json.loads(alert['details'] or '{}')
        raised = stamp(details.get('first_raised_at'))
        pre = raised is not None and raised < run['started']
        finding = {'first_raised_at': details.get('first_raised_at'), 'first_tier': details.get('first_tier'),
                   'current_tier': alert['severity'], 'status': alert['status'],
                   'auto_resolved': details.get('auto_resolved'), 'existed_before_scenario': pre,
                   'latency_minutes': None if pre or raised is None or first_event is None
                   else round((raised - first_event).total_seconds() / 60, 1)}
    live = stored['baseline'].get((key, d.isoformat()))
    return {'_key': key, 'account': info[key]['label'], 'provider': info[key]['provider'], 'day': d.isoformat(),
            'scenario_account_day': cov.get('scenario_account_day', False), 'coverage': cov.get('status', 'no account-day'),
            'failed_conditions': cov.get('failed', []), 'score': base['score'], 'tier': base['tier'],
            'signals': base.get('signals', {}), 'facts': base.get('facts', []), 'finding': finding,
            'stored_live_row': None if not live else {k: live[k] for k in ('score', 'tier', 'scored_mode')},
            'autoencoder': ae_view(cell['ae'] if cell else ({'status': 'not_scored', 'reason': 'No activity on this day.'}
                                                             if info[key]['class'] == 'persona' else None), comparator)}


def scenario_section(runs, by_persona, groups, info, scores, coverage, stored, comparator, hi):
    out = []
    for name, plan in SCENARIOS.items():
        attempts = [r for r in runs if r['scenario'] == name]
        rows, eligible = [], []
        for n, run in enumerate(attempts, 1):
            calls = run['scripted']['aws'] + run['scripted']['cloudflare']
            first = min((c['event_time'] for c in calls if c['event_time']), default=None)
            accounts = [account_result(k, run['day'], info, scores, coverage, stored, comparator, run, first)
                        for p in ('aws', 'cloudflare') for k in by_persona.get((p, run['persona']), [])]
            states = [a['coverage'] for a in accounts if a['scenario_account_day']] or ['not evaluable']
            status = 'pending' if 'pending' in states else 'evaluable' if all(s == 'evaluable' for s in states) else 'not evaluable'
            row = {'scenario': name, 'attempt': n, 'run_record': run['file'], 'persona': run['persona'],
                   'day': run['day'].isoformat(), 'started_utc': run['started'].isoformat(), 'aborted': run.get('aborted'),
                   'cloudflare_part': run.get('cloudflare'), 'scripted_calls': len(calls),
                   'scripted_calls_confirmed': sum(c['confirmed'] for c in calls),
                   'first_confirmed_event_utc': first.astimezone(timezone.utc).isoformat() if first else None,
                   'status': status, 'counted': False, 'note': None, 'accounts': accounts}
            if run['persona'] != plan['persona']:
                row['note'] = f"persona differs from L7 section 2 ({plan['persona']}); not counted"
            elif not SCENARIO_START <= run['day'] <= hi:
                row['note'] = 'outside the evaluation window; not counted'
            else:
                eligible.append(row)
            rows.append(row)
        counted = None
        if eligible:
            counted = eligible[0]
            if len(eligible) > 1:
                second = eligible[1]
                if counted['status'] == 'not evaluable':
                    second['note'] = 'repeat (L7 section 2): attempt %d was not evaluable: %s' % (
                        counted['attempt'], '; '.join(f for a in counted['accounts'] if a['scenario_account_day']
                                                      for f in a['failed_conditions']) or 'no scenario account found')
                    counted = second
                else:
                    second['note'] = 'repeat not permitted (earlier attempt was %s); not counted' % counted['status']
                for extra in eligible[2:]:
                    extra['note'] = 'beyond the one repeat L7 section 2 allows; not counted'
            counted['counted'] = True
            for a in counted['accounts']:
                a['side_by_side'] = side_by_side(a['tier'], a['autoencoder'])
        result = {'scenario': name, 'persona': plan['persona'], 'expected': plan['expected'], 'attempts': rows,
                  'outcome': 'not run' if counted is None else counted['status']}
        if counted:
            aws = [a for a in counted['accounts'] if a['provider'] == 'aws']
            result['expected_vs_observed'] = [{'account': a['account'], 'basis': 'AWS account-day (primary)',
                                               'observed': a['tier'], 'result': compare(plan['expected'], a['tier'])}
                                              for a in aws] or [{'basis': 'AWS account-day', 'observed': None,
                                                                 'result': 'no AWS account found'}]
            if name == 'S1':
                result['expected_vs_observed'] += [{'account': a['account'], 'basis': 'Cloudflare account-day',
                                                    'observed': a['tier'], 'result': compare(plan['expected'], a['tier'])}
                                                   for a in counted['accounts'] if a['provider'] == 'cloudflare']
                result['group'] = group_score(groups, plan['persona'], date.fromisoformat(counted['day']), info, scores)
                if result['group']['tier'] in TIERS:
                    result['expected_vs_observed'].append({'basis': 'cross-cloud group score',
                                                           'observed': result['group']['tier'],
                                                           'result': compare(plan['expected'], result['group']['tier'])})
            result['carry_over'] = carry_over(counted, coverage, scores, info)
        out.append(result)
    return out


def group_score(groups, persona, d, info, scores):
    group = next((g for g in groups if g.get('group') == persona), None)
    if group is None:
        return {'score': None, 'tier': 'unknown', 'reason': f'no {persona} group in workload-groups.json'}
    members = [(info[k]['source'], (scores.get((k, d)) or {}).get('baseline', {}).get('score'))
               for k in group['members'] if k in info]
    score = combine(members)
    return {'score': score, 'tier': bs.tier(score) if score is not None else 'no scored member',
            'members': [{'source': s, 'score': v} for s, v in members]}


def carry_over(counted, coverage, scores, info):
    out = []
    for a in counted['accounts']:
        if not a['scenario_account_day']:
            continue
        key = a['_key']
        later = sorted(d for (k, d), c in coverage.items() if k == key and d > date.fromisoformat(counted['day'])
                       and c['status'] == 'evaluable' and c['has_events'])
        if not later:
            out.append({'account': a['account'], 'next_evaluable_day': None})
            continue
        b = scores[(key, later[0])]['baseline']
        out.append({'account': a['account'], 'next_evaluable_day': later[0].isoformat(), 'follows_scenario': True,
                    'score': b['score'], 'tier': b['tier'], 'facts': b['facts']})
    return out


def summarise(rows, scores, comparator=None):
    """Counts over account-days with events: evaluable N, Learning L, tiered = N - L."""
    evaluable = [r for r in rows if r['status'] == 'evaluable']
    tiers = Counter(scores[r['_k']]['baseline']['tier'] for r in evaluable)
    out = {'account_days': len(rows), 'evaluable_N': len(evaluable), 'learning_L': tiers['Learning'],
           'tiered_denominator': len(evaluable) - tiers['Learning'], 'low': tiers['Low'], 'medium': tiers['Medium'],
           'high': tiers['High'], 'pending': sum(r['status'] == 'pending' for r in rows),
           'not_evaluable': sum(r['status'] == 'not evaluable' for r in rows),
           'not_evaluable_by_condition': dict(Counter(f.split(':')[0] for r in rows for f in r['failed']))}
    out['alerting_days'] = [{'day': r['day'], 'account': r['account'], 'score': scores[r['_k']]['baseline']['score'],
                             'tier': scores[r['_k']]['baseline']['tier'], 'facts': scores[r['_k']]['baseline']['facts'],
                             'follows_scenario': r.get('_follows', False)}
                            for r in evaluable if scores[r['_k']]['baseline']['tier'] in ('Medium', 'High')]
    if comparator is not None:
        out['autoencoder'] = ae_counts(evaluable, scores, comparator)
    return out


def ae_counts(evaluable, scores, comparator):
    if comparator['status'] != 'evaluated':
        return {'status': 'not_evaluated', 'reason': comparator['reason']}
    def count(rows):
        scored = [scores[r['_k']]['ae'] for r in rows if scores[r['_k']]['ae']['status'] == 'scored']
        return {'scored': len(scored), 'flagged_primary': sum(a['flagged'] for a in scored),
                'flagged_secondary': sum(a['flagged_secondary'] for a in scored)}
    return {'status': 'evaluated', 'all_days': count(evaluable),
            'excluding_12_nov': count([r for r in evaluable if r['day'] != CALIBRATION_DAY.isoformat()]),
            'calibration_day_note': '12 Nov 2026 is a calibration day of the comparator and inside the secondary 104 days',
            'not_scored': [{'day': r['day'], 'account': r['account'], 'reason': scores[r['_k']]['ae'].get('reason')}
                           for r in evaluable if scores[r['_k']]['ae']['status'] != 'scored']}


def normal_section(coverage, scores, info, comparator, designed, scenarios):
    follows = {(c['account'], c['next_evaluable_day']) for s in scenarios for c in s.get('carry_over', [])}
    rows = defaultdict(list)
    for (key, d), c in coverage.items():
        if not c['has_events']:
            continue
        r = {**c, '_k': (key, d), '_follows': (c['account'], c['day']) in follows}
        if info[key]['class'] == 'persona':
            if (key, d) not in designed:
                rows[('persona', info[key]['provider'])].append(r)
        else:
            rows[(info[key]['class'], None)].append(r)
    persona_all = rows[('persona', 'aws')] + rows[('persona', 'cloudflare')]
    persona = {'definition': 'evaluable persona account-days (AWS role, Cloudflare token of persona-01..06), '
                             '12 Nov to the window end, excluding scenario account-days of that account',
               'all': summarise(persona_all, scores, comparator),
               'aws': summarise(rows[('persona', 'aws')], scores, comparator),
               'cloudflare': summarise(rows[('persona', 'cloudflare')], scores, comparator)}
    separate = {cls: summarise(rows[(cls, None)], scores) for cls in ('infrastructure', 'github_bot', 'other')}
    return {'persona': persona, 'separate': separate}


def executor_section(claims, ticks, runs, lo, hi):
    out = {}
    for d in days_between(lo, hi):
        day = d.isoformat()
        items = [f'{ex}: {n} claimed' for ex, n in sorted(Counter(c['executor'] for c in claims
                                                                   if str(c['day'])[:10] == day).items())]
        if day in ticks['reserved']:
            oks = ticks['reserved'][day]
            items.append('reserved runner (closed V3 study): ' + ('refused' if not any(oks) else 'ran')
                         + f' ({len(oks)} actor ticks, {sum(oks)} ok)')
        items += [f"scenario script: {r['scenario']} ({len(r.get('calls') or []) + len(r.get('cloudflare_calls') or [])} calls)"
                  for r in runs if r['day'] == d]
        out[day] = items or ['no executor recorded']
    return out


def git_commit():
    try:
        head = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              timeout=30).stdout.strip()
        dirty = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--', 'scripts/live_eval_report.py'],
                               capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 'unknown'
    return (head or 'unknown') + (' (script differs from that commit)' if dirty else '')


# --- output -----------------------------------------------------------------------------------------------

def table(headers, rows):
    def cell(v):
        return '' if v is None else str(v).replace('|', '/').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '|' + '---|' * len(headers)]
                     + ['| ' + ' | '.join(cell(v) for v in r) + ' |' for r in rows]) + '\n'


def provenance(meta):
    files = '\n'.join(f"- {f['role']}: {f['name']} sha256 {f['sha256']}" for f in meta['input_files'])
    return (f"- Method v1.2 binding sha256: {meta['method_sha256']}\n- Comparator manifest sha256: {meta['manifest_sha256']}"
            f" ({meta['comparator_status']})\n- Generated (UTC): {meta['generated_at_utc']}; 'now' used for the 24 h "
            f"decision: {meta['now_used']}\n- Window: {meta['window'][0]} to {meta['window'][1]} MYT; mode: {meta['mode']}\n"
            f"- Script commit: {meta['script_git_commit']}; script sha256 {meta['script_sha256']}\n"
            f"- Rules: {', '.join(meta['rules'])}\n- Input files:\n{files}\n")


def render_md(r):
    m = r['meta']
    md = ['# Live evaluation results (L7 v1.2, L7a, L7b)\n', provenance(m),
          '\nCounts with denominators only; no accuracy, recall or false-positive percentages (L7 section 5).\n',
          '\n## Rules resolved conservatively by the generator\n', ''.join(f'- {a}\n' for a in r['ambiguities_resolved'])]
    md.append('\n## Executors by day (L7b)\n')
    md.append(table(['Day (MYT)', 'Executors'], [(d, '; '.join(x)) for d, x in r['executors_by_day'].items()]))
    md.append('\n## Scenarios (L7 section 5.1, 5.2, 5.4; L7a section 2)\n')
    rows = []
    for s in r['scenarios']:
        if not s['attempts']:
            rows.append((s['scenario'], '-', '-', 'not run', '', '', '', '', '', '', '', ''))
        for a in s['attempts']:
            for acc in a['accounts'] or [{}]:
                ae, f = acc.get('autoencoder') or {}, acc.get('finding') or {}
                rows.append((s['scenario'], a['attempt'], a['day'], f"{a['status']}{' (counted)' if a['counted'] else ''}"
                             + (f"; {a['note']}" if a['note'] else ''), acc.get('provider'), acc.get('coverage'),
                             f"{acc.get('tier')} {acc.get('score') if acc.get('score') is not None else ''}".strip(),
                             f"{f.get('first_tier')} at {f.get('first_raised_at')}" if f else 'none',
                             'pre-existing' if f.get('existed_before_scenario') else f.get('latency_minutes'),
                             ae.get('score') if ae.get('status') == 'scored' else ae.get('status'),
                             f"{ae.get('flagged_primary')}/{ae.get('flagged_secondary')}" if ae.get('status') == 'scored' else '',
                             acc.get('side_by_side', '')))
    md.append(table(['Scenario', 'Attempt', 'Day', 'Status', 'Account', 'Coverage', 'Tier score', 'First finding',
                     'Latency min', 'AE score', 'AE flag primary/secondary', 'Baseline vs AE'], rows))
    md.append('\n### Expected vs observed (misses reported with the same prominence as hits)\n')
    md.append(table(['Scenario', 'Expected', 'Basis', 'Observed', 'Result'],
                    [(s['scenario'], s['expected'], e.get('basis'), e.get('observed'), e.get('result'))
                     for s in r['scenarios'] for e in s.get('expected_vs_observed', [])]
                    + [(s['scenario'], s['expected'], '-', '-', 'not run') for s in r['scenarios'] if s['outcome'] == 'not run']))
    md.append('\n### Signals, facts and autoencoder features of counted attempts\n')
    for s in r['scenarios']:
        for a in s['attempts']:
            if not a['counted']:
                continue
            for acc in a['accounts']:
                ae = acc.get('autoencoder') or {}
                top = ', '.join('%s %.2f' % (t['label'], t['share']) for t in ae.get('top_features', []))
                md.append(f"- **{s['scenario']} {acc['provider']} {acc['day']}**: signals {json.dumps(acc['signals'])}; "
                          f"facts: {'; '.join(acc['facts']) or 'none'}; AE top features: {top or ae.get('status')}\n")
            if s.get('group'):
                md.append(f"- **{s['scenario']} group score**: {s['group'].get('score')} ({s['group']['tier']})\n")
    md.append('\n### Carry-over (L7 section 5.5)\n')
    md.append(table(['Scenario', 'Account', 'Next evaluable day', 'Tier', 'Score'],
                    [(s['scenario'], c['account'], c['next_evaluable_day'], c.get('tier'), c.get('score'))
                     for s in r['scenarios'] for c in s.get('carry_over', [])]))
    md.append('\n## Normal comparison (L7 section 4, 5.3; L7a section 2.2)\n')
    n = r['normal_comparison']
    md.append(n['definition'] + '\n\n')
    md.append(table(['Accounts', 'Account-days', 'Evaluable N', 'Learning L', 'Tiered (N-L)', 'Low', 'Medium', 'High',
                     'Not evaluable', 'Pending'],
                    [(k, x['account_days'], x['evaluable_N'], x['learning_L'], x['tiered_denominator'], x['low'],
                      x['medium'], x['high'], x['not_evaluable'], x['pending']) for k, x in
                     [('persona (all)', n['all']), ('AWS roles', n['aws']), ('Cloudflare tokens', n['cloudflare'])]]))
    ae_rows = []
    for k, x in [('persona (all)', n['all']), ('AWS roles', n['aws']), ('Cloudflare tokens', n['cloudflare'])]:
        a = x['autoencoder']
        if a['status'] != 'evaluated':
            ae_rows.append((k, 'not evaluated', a['reason'], '', ''))
            continue
        for label, c in (('all days', a['all_days']), ('excluding 12 Nov', a['excluding_12_nov'])):
            ae_rows.append((k, label, c['scored'], f"{c['flagged_primary']} of {c['scored']}",
                            f"{c['flagged_secondary']} of {c['scored']}"))
    md.append('\nAutoencoder (comparator; never alerts). 12 Nov is a calibration day of the model.\n\n')
    md.append(table(['Accounts', 'Days', 'Scored', 'Flagged (primary)', 'Flagged (secondary)'], ae_rows))
    md.append('\nAlerting normal account-days:\n\n')
    md.append(table(['Day', 'Account', 'Tier', 'Score', 'Follows scenario', 'Facts'],
                    [(x['day'], x['account'], x['tier'], x['score'], x['follows_scenario'], '; '.join(x['facts']))
                     for x in n['all']['alerting_days']]))
    md.append('\n## Reported separately (not in the comparison)\n')
    md.append(table(['Class', 'Account-days', 'Evaluable N', 'Learning L', 'Tiered', 'Low', 'Medium', 'High',
                     'Not evaluable', 'Pending'],
                    [(k, x['account_days'], x['evaluable_N'], x['learning_L'], x['tiered_denominator'], x['low'],
                      x['medium'], x['high'], x['not_evaluable'], x['pending']) for k, x in r['reported_separately'].items()]))
    md.append('\n## Coverage (L7 section 3)\n\nEvery account-day with its three conditions is in coverage.csv.\n\n')
    md.append(table(['Day', 'Account', 'Class', 'Status', 'Failed conditions'],
                    [(c['day'], c['account'], c['class'], c['status'], '; '.join(c['failed']))
                     for c in r['coverage'] if c['status'] != 'evaluable']))
    return ''.join(md)


def render_csv(r):
    buf = io.StringIO()
    for line in provenance(r['meta']).splitlines():
        buf.write(f'# {line}\n')
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(['day', 'account', 'class', 'provider', 'persona', 'has_events', 'scenario_account_day', 'status',
                'condition_1', 'condition_1_detail', 'condition_2', 'condition_2_detail', 'condition_3',
                'condition_3_detail'])
    for c in r['coverage']:
        w.writerow([c['day'], c['account'], c['class'], c['provider'], c['persona'], c['has_events'],
                    c['scenario_account_day'], c['status']]
                   + [v for n in (1, 2, 3) for v in (c[f'condition_{n}']['status'], c[f'condition_{n}']['detail'])])
    return buf.getvalue()


def default_json(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', required=True, type=Path, help='events DB (workspace copy or operational SQLite), read-only')
    ap.add_argument('--runs', required=True, type=Path, help='folder of scenario run records (run-*.json)')
    ap.add_argument('--ticks', required=True, type=Path, action='append', help='folder with *-ticks.jsonl / ops-status')
    ap.add_argument('--groups', required=True, type=Path, help='workload-groups.json')
    ap.add_argument('--bundle', type=Path, default=os.getenv('ARGUS_LIVE_AE_BUNDLE'), help='the pinned v2 bundle')
    ap.add_argument('--loaded', type=Path, help='live-ae-loaded.json (default: next to --db)')
    ap.add_argument('--ledger', action='append', default=[], metavar='KIND=PATH',
                    help='executor ledger; KIND aws (ledger.db), cloudflare (machine-ledger.db / cloudflare-ledger.db), github')
    ap.add_argument('--window-end', type=date.fromisoformat, default=date(2026, 11, 22))
    ap.add_argument('--now', type=stamp, help='ISO time with offset (default: the current time)')
    ap.add_argument('--out', required=True, type=Path, help='new folder for results.json, results.md, coverage.csv')
    args = ap.parse_args(argv)
    try:
        if args.out.exists():
            raise Refusal(f'output folder {args.out.name} already exists; refusing to overwrite')
        if args.bundle is None:
            raise Refusal('--bundle (or ARGUS_LIVE_AE_BUNDLE) is required')
        for path in (args.db, args.groups, args.runs, *args.ticks):
            if not path.exists():
                raise Refusal(f'input not found: {path.name}')
        ledgers = []
        for spec in args.ledger:
            kind, _, path = spec.partition('=')
            if kind not in LEDGER_COLUMNS or not Path(path).is_file():
                raise Refusal(f'--ledger must be KIND=PATH with KIND in aws/cloudflare/github and an existing file: {kind}')
            ledgers.append((kind, Path(path)))
        args.ledger = ledgers
        args.loaded = args.loaded or args.db.resolve().parent / live_ae.LOADED_FILE
        now = args.now or datetime.now(timezone.utc)
        result = rounded(build(args, now))
    except Refusal as error:
        raise SystemExit(f'live_eval_report refused: {error}')
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'results.json').write_text(scrub(json.dumps(result, indent=2, default=default_json)), encoding='utf-8')
    (args.out / 'results.md').write_text(scrub(render_md(result)), encoding='utf-8')
    (args.out / 'coverage.csv').write_text(scrub(render_csv(result)), encoding='utf-8')
    days = {c['day'] for c in result['coverage']}
    print(f"wrote {args.out.name}: {len(result['coverage'])} account-days over {len(days)} days; "
          f"comparator {result['comparator']['status']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
