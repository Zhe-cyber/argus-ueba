"""Baseline risk score v1.1: per (account, MYT day), compared with the account's own previous 28 days.

One scoring path. The ingest service (backend/main.py::_process_ingest) calls on_event() for every accepted
event that has an account_key; it recomputes that account-day (and any later stored day of the same account
inside the 28-day window, for late-arriving events) and stores the result in `baseline_scores`. Medium/High
account-days raise one `alerts` row with alert_type='baseline_risk' and day=<MYT day>, unique on
(alert_type, user_id, day). The workspace only reads these tables.

Heuristic and fixed-weight. Not trained, not validated, independent of the AE and of rarity_scorer's
off-hours rule. Behaviour is pinned by backend/tests/data/baseline_reference_v1_1.json (L7 section 1).
Method note: docs/LIVE_BASELINE_SCORE_V1.md.

    python -m backend.baseline_scorer --backfill [--db <sqlite copy>]   # recompute every stored account-day
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import fnmatch
import hashlib
import json
import logging
import math
from pathlib import Path
import re
import statistics

from backend.rarity_scorer import SENSITIVE_PATTERNS

_log = logging.getLogger(__name__)
VERSION = 'baseline-risk-score-v1.2'
MYT = timezone(timedelta(hours=8))
WINDOW_DAYS, MIN_HISTORY = 28, 5
WEIGHTS = {'new_action': 0.25, 'new_resource': 0.25, 'unusual_hours': 0.20, 'volume': 0.15, 'sensitive_new': 0.15}
TIER_HIGH, TIER_MEDIUM = 60, 30
COUNT_SIGNAL = (0.0, 0.6, 1.0)                  # 0 new items, 1, 2 or more
NOVELTY_FROM_DAY, NOVELTY_MIN_DAYS, NOVELTY_FACT_RHO = 4, 2, 0.25
USUAL_CORE_SHARE, USUAL_WIDEN_HOURS, UNUSUAL_FULL_SHARE = 0.05, 1, 0.5
VOLUME_FULL_LOG2 = 3                            # 8x the median day -> 1
# v1.2 sensitive first-access floor: sensitive_new (after the novelty discount) >= 0.5 lifts the score to at
# least 30 (tier >= Medium). None disables it (the v1.1 variant, kept for the v1.1 reference vectors).
SENSITIVE_FLOOR_SIGNAL, SENSITIVE_FLOOR_SCORE = 0.5, 30
ALERT_TYPE = 'baseline_risk'
ROOT = Path(__file__).resolve().parent.parent
SENSITIVE_FILE = ROOT / 'config' / 'sensitive_resources.json'
METHOD_FILE = ROOT / 'config' / 'baseline_method_v1_2.json'
REFERENCE_FILE = ROOT / 'backend' / 'tests' / 'data' / 'baseline_reference_v1_2.json'


def load_sensitive_list(path=SENSITIVE_FILE):
    """{provider: [glob]} from the deployment file (simple '*' wildcards, case-insensitive, whole resource name).
    Missing or malformed: {} (built-in patterns only) and a warning."""
    try:
        doc = json.loads(Path(path).read_text(encoding='utf-8'))
        if doc.get('version') != 1 or not isinstance(doc.get('providers'), dict):
            raise ValueError('unexpected shape')
        out = {}
        for provider, globs in doc['providers'].items():
            if not isinstance(globs, list) or not all(isinstance(g, str) and g.strip() for g in globs):
                raise ValueError('provider list must hold non-empty strings')
            out[provider] = list(globs)
        return out
    except (OSError, ValueError, TypeError, AttributeError) as error:
        _log.warning('Sensitive-resource list unusable (%s); built-in patterns only', type(error).__name__)
        return {}


def _compile(deployment):
    """Built-in regexes (any provider) plus (provider, regex) for each deployment glob."""
    return ([re.compile(p, re.IGNORECASE) for p in SENSITIVE_PATTERNS]
            + [(provider, re.compile(fnmatch.translate(g), re.IGNORECASE)) for provider, globs in deployment.items() for g in globs])


SENSITIVE_LIST = load_sensitive_list()  # read once at start
_SENSITIVE = _compile(SENSITIVE_LIST)


def _sensitive(resource, sources):
    """True when a built-in pattern finds the name, or a deployment glob of one of `sources` matches all of it."""
    for p in _SENSITIVE:
        if isinstance(p, tuple):
            if p[0] in sources and p[1].match(resource):
                return True
        elif p.search(resource):
            return True
    return False


def _sha256(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def method():
    """The scorer's running parameters, in the shape of config/baseline_method_v1_1.json."""
    return {'version': VERSION, 'weights': WEIGHTS, 'tiers': {'high': TIER_HIGH, 'medium': TIER_MEDIUM},
            'history_window_days': WINDOW_DAYS, 'learning_min_active_days': MIN_HISTORY,
            'count_signal': list(COUNT_SIGNAL),
            'novelty': {'evaluated_from_history_day': NOVELTY_FROM_DAY, 'min_evaluable_days': NOVELTY_MIN_DAYS,
                        'fact_shown_at_rho': NOVELTY_FACT_RHO, 'discount': 'signal x (1 - rho)'},
            'usual_hours': {'core_hour_min_share': USUAL_CORE_SHARE, 'widen_hours': USUAL_WIDEN_HOURS,
                            'circular': True, 'full_signal_outside_share': UNUSUAL_FULL_SHARE, 'clock': 'MYT'},
            'volume': {'full_signal_log2_ratio': VOLUME_FULL_LOG2},
            'sensitive_floor': {'min_signal_after_discount': SENSITIVE_FLOOR_SIGNAL, 'min_score': SENSITIVE_FLOOR_SCORE},
            'day': 'Asia/Kuala_Lumpur calendar day (UTC+08:00)',
            'builtin_sensitive_patterns_sha256': hashlib.sha256(json.dumps(SENSITIVE_PATTERNS).encode()).hexdigest(),
            'sensitive_resources_sha256': _sha256(SENSITIVE_FILE),
            'reference_vectors_sha256': _sha256(REFERENCE_FILE)}


METHOD_SHA256 = _sha256(METHOD_FILE)  # stored with every baseline_scores row
if METHOD_SHA256 is None:
    _log.warning('Method binding file missing; scores are stored as unbound')


# --- pure scoring (no database access) -------------------------------------------------------------

def tier(score):
    return 'High' if score >= TIER_HIGH else 'Medium' if score >= TIER_MEDIUM else 'Low'


def _stamp(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp without timezone')
    return parsed.astimezone(MYT)


def myt_day(value):
    """MYT calendar day of a timestamp, or None when it is unparseable or has no timezone."""
    try:
        return _stamp(value).date()
    except (ValueError, TypeError):
        return None


def group_days(rows):
    """rows: (timestamp, source, action, resource) in id order -> {MYT date: [(hour, source, action, resource)]}."""
    days = defaultdict(list)
    for ts, source, action, resource in rows:
        try:
            when = _stamp(ts)
        except (ValueError, TypeError):
            continue  # unparseable timestamps are skipped, never guessed
        days[when.date()].append((when.hour, source, action, resource or ''))
    return days


def _count_signal(k):
    return COUNT_SIGNAL[min(k, 2)]


def _name(value):
    """Display-safe name: request-parameter blobs show their first key only; 12-digit runs masked; max 60 chars."""
    value = str(value)
    if value.startswith('{'):
        m = re.match(r'''\{\s*['"]?([^'":,\s}]+)''', value)
        value = m.group(1) if m else '{...}'
    return re.sub(r'\d{12}', '<account>', value)[:60]


def _short(items, n=3):
    names = sorted({_name(x) for x in items})
    return ', '.join(names[:n]) + (f', +{len(names) - n} more' if len(names) > n else '')


def _rho(sets):
    """Share of evaluable days (4th onward) that introduced >=1 item absent from all earlier days; 0 if < 2 evaluable."""
    seen, hits, n = set(), 0, 0
    for i, s in enumerate(sets):
        if i >= NOVELTY_FROM_DAY - 1:
            n += 1
            hits += bool(s - seen)
        seen |= s
    return (hits / n if n >= NOVELTY_MIN_DAYS else 0.0), hits, n


def prior_days(days, day):
    """The account's earlier active days inside the WINDOW_DAYS calendar days before `day`, oldest first."""
    return sorted(d for d in days if day - timedelta(days=WINDOW_DAYS) <= d < day)


def usual_hours(hist):
    """The account's usual MYT hours from its history events (hour first): every hour within +-1 h, circular, of
    an hour holding >= 5% of the history events. No business-hours setting is read here."""
    hours = Counter(e[0] for e in hist)
    core = {h for h, c in hours.items() if c >= USUAL_CORE_SHARE * len(hist)}
    return {(h + k) % 24 for h in core for k in range(-USUAL_WIDEN_HOURS, USUAL_WIDEN_HOURS + 1)}


def score_day(days, day):
    """days: {date: events}. Returns the result dict for `day` (a date with events)."""
    today = days[day]
    prior = prior_days(days, day)
    out = {'day': day.isoformat(), 'history_days': len(prior), 'events_today': len(today),
           'partial': day == datetime.now(MYT).date()}
    if len(prior) < MIN_HISTORY:
        return {**out, 'score': None, 'tier': 'Learning', 'signals': {},
                'facts': [f'{len(prior)} of {MIN_HISTORY} days of history']}
    hist = [e for d in prior for e in days[d]]
    facts, sig = [], {}
    hist_actions = {(e[1], e[2]) for e in hist}
    new_actions = {(e[1], e[2]) for e in today} - hist_actions
    # v1.1 novelty discount: an account that routinely shows new things earns less from newness.
    rho_a, hits_a, n_a = _rho([{(e[1], e[2]) for e in days[d]} for d in prior])
    rho_r, hits_r, n_r = _rho([{e[3] for e in days[d] if e[3]} for d in prior])

    def discount(label, rho, hits, n):
        facts.append(f'This account showed new {label} on {hits} of {n} recent active days, so novelty is discounted.')
    sig['new_action'] = _count_signal(len(new_actions)) * (1 - rho_a)
    if new_actions:
        facts.append(f'{len(new_actions)} action kind(s) never seen in the last {WINDOW_DAYS} days: '
                     + _short([a for _, a in new_actions]))
        if rho_a >= NOVELTY_FACT_RHO: discount('actions', rho_a, hits_a, n_a)
    t_res = {e[3] for e in today if e[3]}
    new_res = set()
    if t_res:
        new_res = t_res - {e[3] for e in hist if e[3]}
        sig['new_resource'] = _count_signal(len(new_res)) * (1 - rho_r)
        if new_res:
            facts.append(f'{len(new_res)} resource(s) never seen in the last {WINDOW_DAYS} days: ' + _short(new_res))
            if rho_r >= NOVELTY_FACT_RHO: discount('resources', rho_r, hits_r, n_r)
    else:
        sig['new_resource'] = None  # unavailable: weights renormalise
    usual = usual_hours(hist)  # v1.1: +-1 h, circular; the account's OWN usual hours
    share = sum(e[0] not in usual for e in today) / len(today)
    sig['unusual_hours'] = min(1.0, share / UNUSUAL_FULL_SHARE)
    if share:
        facts.append(f'{round(share * 100)}% of today\'s events fall outside this account\'s usual hours (MYT)')
    median = statistics.median(len(days[d]) for d in prior)
    ratio = len(today) / median
    sig['volume'] = min(1.0, max(0.0, math.log2(ratio) / VOLUME_FULL_LOG2))
    if sig['volume']:
        facts.append(f'{len(today)} events today; median active day is {median:g} ({ratio:.1f}x)')
    seen = {e[3] for e in hist}
    sources = defaultdict(set)
    for e in today:
        sources[e[3]].add(e[1])
    sens = {r for r in t_res if r not in seen and _sensitive(r, sources[r])}
    sig['sensitive_new'] = (1.0 if sens else 0.0) * (1 - rho_r)
    if sens:
        facts.append(f'{len(sens)} sensitive resource(s) not seen before: ' + _short(sens))
    avail = {k: v for k, v in sig.items() if v is not None}
    score = round(100 * sum(WEIGHTS[k] * v for k, v in avail.items()) / sum(WEIGHTS[k] for k in avail))
    if SENSITIVE_FLOOR_SCORE is not None and sig['sensitive_new'] >= SENSITIVE_FLOOR_SIGNAL and score < SENSITIVE_FLOOR_SCORE:
        score = SENSITIVE_FLOOR_SCORE  # v1.2: a first sensitive access is never Low
        facts.append(f'First access to a sensitive resource in the last {WINDOW_DAYS} days: {_short(sens)} (minimum tier Medium)')
    return {**out, 'score': score, 'tier': tier(score), 'signals': {k: (None if v is None else round(v, 3)) for k, v in sig.items()},
            'rho_action': round(rho_a, 3), 'rho_resource': round(rho_r, 3), 'facts': facts}


# --- storage (event_store connection: SQLite or PostgreSQL) -----------------------------------------

def _store():
    from backend import event_store
    return event_store


def ensure_schema():
    """baseline_scores plus the alerts table with its `day` column and unique guard (idempotent)."""
    from backend import alert_store
    store = _store()
    with store._db() as con:
        store._cursor(con).execute(store._DDL_BASELINE_SCORES)
    alert_store.init_alerts_db()


def _account_rows(cur, key, lo=None, hi=None):
    """The account's events in id order; with lo/hi (dates) a text prefilter keeps ISO stamps in [lo, hi) plus
    every stamp that does not start with an ISO date (rare; group_days decides about those exactly)."""
    ph = _store()._PH
    sql, args = f'SELECT timestamp,source,action,resource FROM events WHERE account_key={ph}', [key]
    if lo is not None:
        sql += f" AND (timestamp >= {ph} AND timestamp < {ph} OR timestamp NOT LIKE '____-__-__%')"
        args += [lo.isoformat(), hi.isoformat()]
    cur.execute(sql + ' ORDER BY id', args)
    return [(r['timestamp'], r['source'], r['action'], r['resource']) for r in _store()._rows(cur)]


def _identity(cur, key):
    """(label, source) of the account's first stored event: the same label the workspace shows."""
    ph = _store()._PH
    cur.execute(f'SELECT account_label,source FROM events WHERE account_key={ph} ORDER BY id LIMIT 1', (key,))
    row = cur.fetchone()
    return (dict(row)['account_label'], dict(row)['source']) if row else (None, None)


def _created(day, now):
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=MYT) - timedelta(seconds=1)
    return min(end, now).astimezone(timezone.utc).isoformat()


def _upsert_score(cur, key, r, now, mode):
    ph = _store()._PH
    cur.execute(f'''INSERT INTO baseline_scores (account_key,day,score,tier,signals_json,facts_json,history_days,
        events_today,partial,rho_action,rho_resource,computed_at,scored_mode,method_sha256) VALUES ({','.join([ph] * 14)})
        ON CONFLICT (account_key,day) DO UPDATE SET score=excluded.score,tier=excluded.tier,
        signals_json=excluded.signals_json,facts_json=excluded.facts_json,history_days=excluded.history_days,
        events_today=excluded.events_today,partial=excluded.partial,rho_action=excluded.rho_action,
        rho_resource=excluded.rho_resource,computed_at=excluded.computed_at,scored_mode=excluded.scored_mode,
        method_sha256=excluded.method_sha256''',
                (key, r['day'], r['score'], r['tier'], json.dumps(r['signals']), json.dumps(r['facts']),
                 r['history_days'], r['events_today'], int(r['partial']), r.get('rho_action'), r.get('rho_resource'),
                 now.isoformat(), mode, METHOD_SHA256))


def _finding(cur, key, day):
    ph = _store()._PH
    cur.execute(f'SELECT id,status,resolved_at,details FROM alerts WHERE alert_type={ph} AND user_id={ph} AND day={ph}',
                (ALERT_TYPE, key, day))
    row = cur.fetchone()
    return dict(row) if row else None


def _sync_finding(cur, key, label, source, r, now):
    """L2 rules: one finding per Medium/High account-day; a re-score updates score, tier and facts and never an
    analyst's status. Only automatic change: an untouched Open finding whose day fell below Medium is Resolved,
    and it reopens if the day rises to Medium again."""
    ph = _store()._PH
    row = _finding(cur, key, r['day'])
    if r['tier'] not in ('Medium', 'High'):
        if row is not None:
            _retire(cur, row, now)
        return
    details = {k: r[k] for k in ('day', 'score', 'tier', 'signals', 'facts', 'history_days', 'events_today', 'partial')}
    details['source'] = source
    title = f"Baseline risk {r['tier']} ({r['score']}): {label or key}"
    if row is None:
        # first-seen facts of the finding; later upgrades/downgrades never overwrite them
        details.update(first_raised_at=now.isoformat(), first_tier=r['tier'])
        cur.execute(f'''INSERT INTO alerts (user_id,alert_type,severity,title,details,status,created_at,day)
            VALUES ({ph},{ph},{ph},{ph},{ph},'Open',{ph},{ph}) ON CONFLICT (alert_type,user_id,day) DO NOTHING''',
                    (key, ALERT_TYPE, r['tier'], title, json.dumps(details),
                     _created(date.fromisoformat(r['day']), now), r['day']))
        return
    old = json.loads(row['details'] or '{}')
    for kept in ('analyst_touched', 'first_raised_at', 'first_tier'):
        if kept in old:
            details[kept] = old[kept]
    status, resolved = row['status'], row['resolved_at']
    if old.get('auto_resolved'):
        if status == 'Resolved':  # Medium+ again: undo only our own auto-resolve
            status, resolved = 'Open', None
        else:
            details['auto_resolved'] = old['auto_resolved']
    cur.execute(f'UPDATE alerts SET severity={ph},title={ph},details={ph},status={ph},resolved_at={ph} WHERE id={ph}',
                (r['tier'], title, json.dumps(details), status, resolved, row['id']))


def _retire(cur, row, now):
    """The account-day is below Medium (or gone): auto-resolve an Open finding no analyst touched."""
    old = json.loads(row['details'] or '{}')
    if row['status'] != 'Open' or old.get('analyst_touched'):
        return
    old['auto_resolved'] = 'score fell below Medium'
    ph = _store()._PH
    cur.execute(f"UPDATE alerts SET status='Resolved',resolved_at={ph},details={ph} WHERE id={ph}",
                (now.isoformat(), json.dumps(old), row['id']))


def _rescore(cur, key, days, targets, now, mode):
    label, source = _identity(cur, key)
    results = [score_day(days, day) for day in (sorted(days) if targets is None else targets)]
    for r in results:
        _upsert_score(cur, key, r, now, mode)
        _sync_finding(cur, key, label, source, r, now)
    return results


def on_event(account_key, timestamp, now=None):
    """Ingest hook: recompute the event's account-day plus any later stored day of this account whose 28-day
    history now includes it (late arrival). Returns the event day's result, or None (no key / bad timestamp)."""
    day = myt_day(timestamp)
    if not account_key or day is None:
        return None
    now = now or datetime.now(timezone.utc)
    store = _store()
    with store._db() as con:
        cur = store._cursor(con)
        cur.execute(f'SELECT day FROM baseline_scores WHERE account_key={store._PH} AND day>{store._PH} AND day<={store._PH}',
                    (account_key, day.isoformat(), (day + timedelta(days=WINDOW_DAYS)).isoformat()))
        later = sorted(date.fromisoformat(r['day']) for r in store._rows(cur))
        last = later[-1] if later else day
        days = group_days(_account_rows(cur, account_key, day - timedelta(days=WINDOW_DAYS + 2), last + timedelta(days=2)))
        results = _rescore(cur, account_key, days, [d for d in [day, *later] if d in days], now, 'ingest')
    return results[0] if results and results[0]['day'] == day.isoformat() else None


def backfill(now=None):
    """Recompute every stored account-day; drop score rows whose day has no events left and auto-resolve their
    untouched Open findings. Returns counts by tier."""
    now = now or datetime.now(timezone.utc)
    store = _store()
    counts = Counter()
    with store._db() as con:
        cur = store._cursor(con)
        cur.execute('SELECT DISTINCT account_key FROM events WHERE account_key IS NOT NULL')
        keys = sorted(r['account_key'] for r in store._rows(cur))
        live = set()
        for key in keys:
            for r in _rescore(cur, key, group_days(_account_rows(cur, key)), None, now, 'backfill'):
                live.add((key, r['day']))
                counts[r['tier']] += 1
        cur.execute('SELECT account_key,day FROM baseline_scores')
        stale = [(r['account_key'], r['day']) for r in store._rows(cur) if (r['account_key'], r['day']) not in live]
        for key, day in stale:
            cur.execute(f'DELETE FROM baseline_scores WHERE account_key={store._PH} AND day={store._PH}', (key, day))
        cur.execute(f'SELECT id,user_id,day,status,details FROM alerts WHERE alert_type={store._PH}', (ALERT_TYPE,))
        for row in store._rows(cur):
            if (row['user_id'], row['day']) not in live:
                _retire(cur, row, now)
    return dict(counts)


def latest_by_account():
    """{account_key: {'day','score','tier'}} for each account's most recent scored day (backend user risk)."""
    store = _store()
    with store._db() as con:
        cur = store._cursor(con)
        cur.execute('''SELECT b.account_key,b.day,b.score,b.tier FROM baseline_scores b JOIN
            (SELECT account_key, MAX(day) AS day FROM baseline_scores GROUP BY account_key) m
            ON b.account_key=m.account_key AND b.day=m.day''')
        return {r['account_key']: {'day': r['day'], 'score': r['score'], 'tier': r['tier']} for r in store._rows(cur)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--backfill', action='store_true', required=True)
    ap.add_argument('--db', help='SQLite file to backfill instead of the configured event store (e.g. a workspace copy)')
    args = ap.parse_args(argv)
    from pathlib import Path
    from backend import alert_store, event_store
    if args.db:
        if event_store._PG:
            raise SystemExit('--db is for SQLite copies; unset DATABASE_URL (use sqlite-local)')
        event_store.DB_PATH = Path(args.db).resolve(strict=True)
    event_store.init_db()
    alert_store.init_alerts_db()
    counts = backfill()
    print(f'method binding sha256: {METHOD_SHA256 or "UNBOUND (config/baseline_method_v1_1.json missing)"}')
    print('backfill done; account-days by tier:', ', '.join(f'{t}={counts.get(t, 0)}' for t in ('High', 'Medium', 'Low', 'Learning')))


if __name__ == '__main__':
    main()
