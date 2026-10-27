"""Match private actor receipts to real locally collected CloudTrail evidence.

Reads only local gitignored SQLite state. It does not invent logs, change events,
train a model or send the scenario manifest into the detector.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.run_simulation import make_plan
from scripts.simulation_lab import PERSONAS


def verify(manifest_path, state_dir):
    manifest_path, state_dir = Path(manifest_path).resolve(), Path(state_dir).resolve()
    if (not manifest_path.is_relative_to((ROOT / 'data/live/experiments').resolve())
            or manifest_path.name != 'manifest.json'
            or not state_dir.is_relative_to((ROOT / 'data/live').resolve())):
        raise ValueError('Use only the private experiment and local live-state directories')
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if manifest.get('mode') != 'executed' or manifest.get('status') != 'completed':
        raise ValueError('Only a completed real execution can be audited')
    if (set(manifest.get('principals', {})) != set(PERSONAS)
            or len(set(manifest['principals'].values())) != len(PERSONAS)):
        raise ValueError('Six distinct lab principals are required')
    plan = make_plan(manifest['account_id'], manifest['stack'], manifest['seed'],
                     manifest['phase'], manifest['max_requests'])
    if manifest.get('actions') != plan['actions'] or len(manifest.get('results', [])) != len(plan['actions']):
        raise ValueError('Manifest plan/result mismatch')
    database = (state_dir / 'events.db').resolve()
    if not database.is_relative_to((ROOT / 'data/live').resolve()) or not database.is_file():
        raise ValueError('Local event database is unavailable')
    request_ids = [row.get('request_id') for row in manifest['results']]
    if not all(isinstance(value, str) and value for value in request_ids):
        raise ValueError('Native API request IDs are missing')
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT event_id, action, resource, metadata, timestamp FROM events "
            "WHERE source='aws_cloudtrail' AND source_account_id=? AND event_id IS NOT NULL "
            "AND json_extract(metadata, '$.requestID') IN (" + ','.join('?' for _ in request_ids) + ')',
            (manifest['account_id'], *request_ids),
        ).fetchall()
    evidence = [(dict(row), json.loads(row['metadata'])) for row in rows]
    native_ids, timestamps = [], []
    for expected, receipt in zip(plan['actions'], manifest['results']):
        if receipt.get('status') != 'ok' or any(receipt.get(k) != v for k, v in expected.items()):
            raise ValueError('Receipt does not match the approved operation')
        candidates = [row for row, metadata in evidence
                      if metadata.get('requestID') == receipt['request_id']
                      and metadata.get('userIdentity', {}).get('principalId') == manifest['principals'].get(expected['persona'])
                      and row['action'] == expected['operation'] and row['resource'] == expected['bucket']
                      and not metadata.get('errorCode')]
        if len(candidates) == 1:
            native_ids.append(candidates[0]['event_id'])
            timestamps.append(candidates[0]['timestamp'])
    complete = len(native_ids) == len(plan['actions']) and len(set(native_ids)) == len(native_ids)
    report = {'schema_version': 1, 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
              'status': 'complete' if complete else 'pending', 'expected_actions': len(plan['actions']),
              'matched_actions': len(native_ids), 'native_event_ids': native_ids,
              'provider_time_min': min(timestamps) if timestamps else None,
              'provider_time_max': max(timestamps) if timestamps else None,
              'verified_at': datetime.now(timezone.utc).isoformat()}
    output = manifest_path.parent / 'audit.json'
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report, output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--state-dir', default=str(ROOT / 'data/live/connected'))
    args = parser.parse_args()
    try:
        report, path = verify(args.manifest, args.state_dir)
        print(json.dumps({k: report[k] for k in ('status', 'expected_actions', 'matched_actions')} | {'audit_file': str(path)}))
        return 0 if report['status'] == 'complete' else 2
    except Exception:
        print('Audit stopped. Check the private completed manifest and local event database. No raw records displayed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
