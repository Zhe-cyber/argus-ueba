"""Read-only shared-core input compatibility. No model inference or cloud I/O."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.shared_core_features import PROFILE, Day, History, instant, canonical, HOURS
from zoneinfo import ZoneInfo
from scripts.shared_core_live_guard import project_live


def audit(records, at):
    if at.tzinfo is None:
        raise ValueError('Zoned cutoff required')
    days, issues, rejected_days = {}, defaultdict(Counter), Counter()
    for row in records:
        source = row['source']
        try:
            event = project_live(row)
        except (ValueError, TypeError, KeyError):
            issues[source]['projection_rejected'] += 1
            try:
                day = instant(row['timestamp']).astimezone(ZoneInfo(HOURS[source][0])).date().isoformat()
                if row.get('account_key'):
                    rejected_days[source, row.get('source_account_id'), row['account_key'], day] += 1
            except (ValueError, TypeError, KeyError):
                pass
            continue
        if event.timestamp > at:
            issues[source]['future_event_excluded'] += 1; continue
        if event.day >= at.astimezone(ZoneInfo(HOURS[source][0])).date().isoformat():
            issues[source]['current_day_event_excluded'] += 1; continue
        key = event.source, event.scope, event.account, event.day
        days.setdefault(key, Day()).add(event)
    history, snapshots = History(), defaultdict(list)
    for key, day in sorted(days.items(), key=lambda item: (item[0][3], item[0][:3])):
        if rejected_days[key]:
            day.issues['invalid_projection'] += rejected_days[key]
        result = history.snapshot(day)
        snapshots[key[0]].append({'account': key[2], **result})
        history.commit_original(day)
    result = {}
    for source in sorted(set(issues) | set(snapshots)):
        rows = snapshots[source]
        feature_rows = [row['features'] for row in rows if row['eligible']]
        gaps = Counter()
        for row in rows:
            gaps.update(row['issues'])
        result[source] = {'observed_closed_account_days': len(rows),
                          'observed_accounts': len({row['account'] for row in rows}),
                          'eligible_input_days': len(feature_rows),
                          'cold_start_days': sum(row['cold_start'] for row in rows),
                          'feature_issue_events': dict(gaps), 'exclusions': dict(issues[source]),
                          'projection_failure_account_days': sum(1 for key in rejected_days if key[0] == source),
                          'status': 'input_available_not_model_validated' if feature_rows else 'no_eligible_input_yet'}
    return {'profile': PROFILE, 'status': 'compatibility_only_no_inference', 'cutoff_utc': at.isoformat(),
            'sources': result, 'model_loaded': False, 'live_activation': False,
            'normality': 'Observed activity, not verified normal', 'coverage': 'Completeness unknown'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True); parser.add_argument('--out', required=True)
    args = parser.parse_args(); db, out = Path(args.db).resolve(), Path(args.out).resolve()
    if not db.is_file() or out.exists() or not out.is_relative_to(ROOT / 'data'):
        parser.error('Require existing SQLite file and new private output')
    at = datetime.now(timezone.utc)
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        records = [dict(row) for row in con.execute('''SELECT source,source_account_id,account_key,event_id,payload_digest,
            timestamp,action,resource,metadata,ingested_at FROM events WHERE ingested_at<=? ORDER BY id LIMIT 100001''', (at.isoformat(),))]
    if len(records) > 100000:
        parser.error('Snapshot cap exceeded; no silent truncation')
    result = audit(records, at)
    result['bindings'] = {'snapshot_rows': len(records), 'snapshot_sha256': hashlib.sha256(canonical(records)).hexdigest(),
                          'feature_code_sha256': hashlib.sha256((ROOT / 'scripts/shared_core_features.py').read_bytes()).hexdigest(),
                          'live_guard_sha256': hashlib.sha256((ROOT / 'scripts/shared_core_live_guard.py').read_bytes()).hexdigest(),
                          'audit_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
