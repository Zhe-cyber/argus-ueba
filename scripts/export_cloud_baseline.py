"""Export audited AWS lab baseline features; never export raw cloud logs to Colab."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.cloud_feature_extractor import CLOUD_FEATURES, aggregate_window
from scripts.audit_simulation import verify


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export(manifests, state_dir, output, now=None):
    """Only baseline SDK actions with matching native evidence enter the export.

    Lab-only user-day vectors describe audited actions, not all activity of a
    production user. They are deliberately separate from the connected database.
    """
    now = now or datetime.now(timezone.utc)
    output = Path(output)
    if output.exists():
        raise ValueError('Export output already exists; use a new versioned path')
    selected, evidence, scope = set(), [], None
    for path in manifests:
        path = Path(path).resolve()
        manifest = json.loads(path.read_text())
        current = (manifest['account_id'], manifest['stack'])
        if manifest.get('phase') != 'baseline' or (scope is not None and scope != current):
            raise ValueError('Only baseline runs from one lab scope may be combined')
        scope = current
        report, _ = verify(path, state_dir)
        if report['status'] != 'complete':
            raise ValueError('Native audit is incomplete')
        ids = set(report['native_event_ids'])
        if selected & ids:
            raise ValueError('Repeated/overlapping native events in input runs')
        selected.update(ids)
        evidence.append({'manifest_sha256': sha(path),
                         'matched_actions': report['matched_actions']})
    if not selected:
        raise ValueError('At least one completed audited baseline run is required')
    database = (Path(state_dir) / 'events.db').resolve()
    by_user = defaultdict(list)
    # Read only the already-verified native IDs, never adopt setup/root activity.
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        con.execute('BEGIN')
        source_count = con.execute('SELECT count(*) FROM events').fetchone()[0]
        for event_id in sorted(selected):
            records = con.execute("SELECT * FROM events WHERE source='aws_cloudtrail' "
                                  'AND source_account_id=? AND event_id=?', (scope[0], event_id)).fetchall()
            if len(records) != 1:
                raise ValueError('Verified native event is unavailable or ambiguous')
            event = dict(records[0])
            timestamp = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            if timestamp.tzinfo is None or timestamp > now:
                raise ValueError('Native timestamp is invalid or in the future')
            event['timestamp'] = timestamp.astimezone(timezone.utc).isoformat()
            identity = (event['source'], event['source_account_id'], event['user'])
            by_user[identity].append(event)
    rows = []
    for identity, events in sorted(by_user.items()):
        user = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        days = defaultdict(list)
        for event in sorted(events, key=lambda e: (e['timestamp'], e['event_id'])):
            days[event['timestamp'][:10]].append(event)
        history = []
        for day, window in sorted(days.items()):
            rows.append({'user': user, 'date': day, 'complete_day': day < now.date().isoformat(),
                         **aggregate_window(window, history=history)})
            history.extend(window)
    document = {'schema_version': 1, 'dataset_kind': 'audited_aws_lab_normal',
                'features': CLOUD_FEATURES, 'rows': rows,
                'provenance': {'runs': evidence, 'native_events': len(selected),
                               'excluded_database_events': source_count - len(selected),
                               'feature_code_sha256': sha(ROOT / 'backend/cloud_feature_extractor.py'),
                               'export_code_sha256': sha(Path(__file__)),
                               'exported_at': now.isoformat(),
                               'limitations': 'Controlled AWS machine activity only; not independently verified human normality. '
                               'Features use audited actions only; setup and unaudited actions are excluded.'}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2, allow_nan=False)
    return {'rows': len(rows), 'identities': len(by_user), 'days': len({r['date'] for r in rows}),
            'included_events': len(selected), 'excluded_events': source_count - len(selected),
            'closed_day_rows': sum(r['complete_day'] for r in rows), 'dataset_sha256': sha(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', action='append', required=True, help='Repeat for disjoint audited baseline runs')
    parser.add_argument('--state-dir', default=str(ROOT / 'data/live/connected'))
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(export(args.manifest, args.state_dir, args.out)))
        return 0
    except Exception:
        print('Export refused. Check completed baseline audits, unique inputs and a new output path. No raw events displayed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
