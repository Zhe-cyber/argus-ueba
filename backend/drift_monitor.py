"""Drift monitor: tells the analyst when an account's normal has changed, and when a data source has gone quiet.

The baseline score compares each account-day with the previous 28 days, so a slow shift gets absorbed into the
baseline. This module compares the last 7 calendar days with the 21 before them instead. It only writes
OBSERVATIONS (alerts rows, alert_type 'behaviour_drift' / 'source_drift', severity 'Info', one per account or
provider per MYT day). It never touches baseline_scores, baseline findings or tiers. Thresholds:
config/drift_monitor.json (design choices, not validated). Method note: docs/DRIFT_MONITOR.md.

    python -m backend.drift_monitor --db <sqlite copy> [--day YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import statistics

from backend.baseline_scorer import MYT, _created, _stamp

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / 'config' / 'drift_monitor.json'
TYPES = ('behaviour_drift', 'source_drift')


def load_config(path=CONFIG_FILE):
    return json.loads(Path(path).read_text(encoding='utf-8'))


# --- pure measures ---------------------------------------------------------------------------------

def js_distance(a, b):
    """Jensen-Shannon distance (sqrt of the base-2 divergence, 0..1) between two count histograms."""
    ta, tb = sum(a.values()), sum(b.values())
    if not ta or not tb:
        return 0.0
    m = {k: (a.get(k, 0) / ta + b.get(k, 0) / tb) / 2 for k in set(a) | set(b)}

    def kl(p, tp):
        return sum(v / tp * math.log2(v / tp / m[k]) for k, v in p.items() if v)
    return math.sqrt(max(0.0, (kl(a, ta) + kl(b, tb)) / 2))


def _window(days, lo, hi):
    """Events of the calendar days lo..hi inclusive -> (event counts of the active days, action hist, resource hist)."""
    counts, actions, resources = [], Counter(), Counter()
    for i in range((hi - lo).days + 1):
        rows = days.get(lo + timedelta(days=i))
        if rows:
            counts.append(len(rows))
            for _, action, resource in rows:
                actions[action] += 1
                resources[resource] += 1
    return counts, actions, resources


def account_drift(days, day, cfg):
    """days: {MYT date: [(hour, action, resource)]} for one account. Returns None when not evaluable, else a dict
    with the measures, windows, which thresholds fired and plain-language facts."""
    c = cfg['account']
    r_lo, r_hi = day - timedelta(days=c['recent_days'] - 1), day
    f_lo, f_hi = r_lo - timedelta(days=c['reference_days']), r_lo - timedelta(days=1)
    active = sum(1 for d in days if f_lo <= d <= r_hi)
    rc, ra, rr = _window(days, r_lo, r_hi)
    fc, fa, fr = _window(days, f_lo, f_hi)
    if active < c['min_active_days'] or len(rc) < c['min_recent_active_days'] or not fc:
        return None
    med_r, med_f = statistics.median(rc), statistics.median(fc)
    recent_items = {('a', k) for k in ra} | {('r', k) for k in rr}
    new_items = recent_items - ({('a', k) for k in fa} | {('r', k) for k in fr})
    m = {'volume_shift_log2': round(abs(math.log2(med_r / med_f)), 3), 'median_recent': med_r, 'median_reference': med_f,
         'action_js': round(js_distance(ra, fa), 3), 'resource_js': round(js_distance(rr, fr), 3),
         'new_item_share': round(len(new_items) / len(recent_items), 3), 'new_items': len(new_items),
         'recent_items': len(recent_items)}
    fired = [k for k, hit in (('volume', m['volume_shift_log2'] >= c['volume_shift_log2']),
                              ('action_mix', m['action_js'] >= c['action_js_distance']),
                              ('resource_mix', m['resource_js'] >= c['resource_js_distance']),
                              ('new_items', m['new_item_share'] >= c['new_item_share'])) if hit]
    facts = []
    if 'volume' in fired:
        ratio = med_r / med_f
        facts.append(f"Median daily events {'rose' if ratio > 1 else 'fell'} from {med_f:g} to {med_r:g} "
                     f"({ratio:.1f}x) between the reference window and the last {c['recent_days']} days")
    if 'action_mix' in fired:
        facts.append(f"The mix of actions changed (distance {m['action_js']:.2f}, threshold {c['action_js_distance']:.2f})")
    if 'resource_mix' in fired:
        facts.append(f"The mix of resources changed (distance {m['resource_js']:.2f}, threshold {c['resource_js_distance']:.2f})")
    if 'new_items' in fired:
        facts.append(f"{m['new_items']} of {m['recent_items']} distinct actions and resources in the last "
                     f"{c['recent_days']} days were absent from the reference window ({m['new_item_share']:.0%})")
    return {'flagged': bool(fired), 'fired': fired, 'measures': m, 'facts': facts,
            'windows': {'recent': [r_lo.isoformat(), r_hi.isoformat()], 'reference': [f_lo.isoformat(), f_hi.isoformat()]},
            'active_days': active, 'recent_active_days': len(rc)}


def source_drift(stamps, day, now, cfg):
    """stamps: MYT datetimes of one provider's events. None when the provider has no history (median 0)."""
    c = cfg['source']
    per_day = Counter(e.date() for e in stamps)
    median = statistics.median(per_day.get(day - timedelta(days=i), 0) for i in range(1, c['median_days'] + 1))
    if median <= 0:
        return None
    today = [e for e in stamps if e.date() == day]
    now_myt = now.astimezone(MYT)
    fired, facts = [], []
    if (now_myt.date() > day or now_myt.hour >= c['low_check_from_hour_myt']) and len(today) < c['low_share_of_median'] * median:
        fired.append('low_volume')
        facts.append(f"{len(today)} events on {day.isoformat()} against a median of {median:g} per day over the previous {c['median_days']} days")
    lo_h, hi_h = c['gap_window_myt']
    midnight = datetime.combine(day, datetime.min.time(), tzinfo=MYT)
    start, end = midnight + timedelta(hours=lo_h), min(midnight + timedelta(hours=hi_h), now_myt)
    if end > start:
        marks = [start] + sorted(e for e in today if start <= e <= end) + [end]
        gap = max(b - a for a, b in zip(marks, marks[1:]))
        if gap >= timedelta(hours=c['gap_hours']):
            fired.append('silent_gap')
            facts.append(f"No events for {gap.total_seconds() / 3600:.1f} hours between {lo_h:02d}:00 and {hi_h:02d}:00 MYT")
    return {'flagged': bool(fired), 'fired': fired, 'facts': facts, 'events_today': len(today), 'median_previous': median}


# --- storage and run -------------------------------------------------------------------------------

def _write(cur, user_id, alert_type, title, details, day, now):
    """One observation per (type, subject, MYT day); a re-run the same day refreshes its details, never its status."""
    from backend import event_store
    ph = event_store._PH
    cur.execute(f'''INSERT INTO alerts (user_id,alert_type,severity,title,details,status,created_at,day)
        VALUES ({ph},{ph},'Info',{ph},{ph},'Open',{ph},{ph}) ON CONFLICT (alert_type,user_id,day)
        DO UPDATE SET title=excluded.title,details=excluded.details''',
                (user_id, alert_type, title, json.dumps(details), _created(day, now), day.isoformat()))


def run_once(day=None, now=None, cfg=None):
    """Evaluate every account and provider for MYT `day` (default today) and write observations. Returns counts."""
    from backend import alert_store, event_store as store
    from workspace_next import system_accounts
    now = now or datetime.now(timezone.utc)
    day = day or now.astimezone(MYT).date()
    cfg = cfg or load_config()
    c = cfg['account']
    lo = day - timedelta(days=max(c['recent_days'] + c['reference_days'], cfg['source']['median_days']))
    alert_store.init_alerts_db()
    with store._db() as con:
        cur = store._cursor(con)
        # text prefilter with a day of slack either side; exact MYT bucketing happens below
        cur.execute(f'''SELECT account_key,source,timestamp,action,resource FROM events WHERE account_key IS NOT NULL
            AND timestamp >= {store._PH} AND timestamp < {store._PH}''',
                    ((lo - timedelta(days=1)).isoformat(), (day + timedelta(days=2)).isoformat()))
        rows = store._rows(cur)
    directory = store.account_directory()
    declared = system_accounts.declared(store.DB_PATH)
    accounts, providers = defaultdict(lambda: defaultdict(list)), defaultdict(list)
    for r in rows:
        try:
            when = _stamp(r['timestamp'])
        except (ValueError, TypeError):
            continue  # unparseable timestamps are skipped, never guessed
        accounts[r['account_key']][when.date()].append((when.hour, r['action'], r['resource'] or ''))
        providers[r['source']].append(when)
    out = {'day': day.isoformat(), 'accounts_evaluated': 0, 'accounts_flagged': 0, 'infrastructure_flagged': 0,
           'accounts_not_evaluated': 0, 'sources_evaluated': 0, 'sources_flagged': 0}
    with store._db() as con:
        cur = store._cursor(con)
        for key, days in accounts.items():
            if not any(day - timedelta(days=c['recent_days'] - 1) <= d <= day for d in days):
                continue  # no activity in the recent window at all
            result = account_drift(days, day, cfg)
            if result is None:
                out['accounts_not_evaluated'] += 1
                continue
            out['accounts_evaluated'] += 1
            if not result['flagged']:
                continue
            info = directory.get(key, {})
            label = info.get('account_label') or key
            infra = system_accounts.is_infrastructure(label, info.get('account_kind'), info.get('source'), declared)
            details = {**result, 'observation': True, 'day': day.isoformat(), 'thresholds': c, 'source': info.get('source'),
                       'monitoring_infrastructure': infra, 'version': cfg['version']}
            _write(cur, key, 'behaviour_drift', f"Behaviour drift{' (monitoring infrastructure)' if infra else ''}: {label}", details, day, now)
            out['accounts_flagged'] += 1
            out['infrastructure_flagged'] += bool(infra)
        for provider, stamps in providers.items():
            result = source_drift(stamps, day, now, cfg)
            if result is None:
                continue
            out['sources_evaluated'] += 1
            if result['flagged']:
                details = {**result, 'observation': True, 'day': day.isoformat(), 'thresholds': cfg['source'],
                           'source': provider, 'version': cfg['version']}
                _write(cur, provider, 'source_drift', f'Source drift: {provider}', details, day, now)
                out['sources_flagged'] += 1
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', required=True, help='SQLite file (e.g. a workspace copy)')
    ap.add_argument('--day', help='MYT day the windows end on (default: today)')
    args = ap.parse_args(argv)
    from backend import event_store
    if event_store._PG:
        raise SystemExit('--db is for SQLite copies; unset DATABASE_URL (use sqlite-local)')
    event_store.DB_PATH = Path(args.db).resolve(strict=True)
    event_store.init_db()
    print(json.dumps(run_once(date.fromisoformat(args.day) if args.day else None), indent=2))


if __name__ == '__main__':
    main()
