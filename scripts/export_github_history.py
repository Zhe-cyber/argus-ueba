"""Read-only, pseudonymised export of stored GitHub projections, not raw audit logs."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3

MY = timezone(timedelta(hours=8))
FEATURES = ['event_count', 'push_label_count', 'pull_request_label_count',
            'issue_label_count', 'issue_comment_label_count', 'ref_change_label_count',
            'unique_repositories', 'off_hours_events']
CONTRACT = {
    'profile': 'github_projection_daily_v2', 'features': FEATURES,
    'timezone': 'Asia/Kuala_Lumpur', 'window': 'closed observed account/day',
    'action_basis': 'inferred from stored normalized display labels, not native event types',
    'identity': 'source + source_account_id + native actor_id; labelled login fallback',
    'coverage': 'bounded_sample_completeness_unknown',
    'off_hours': 'outside Mon-Fri 08:00 inclusive to 20:00 exclusive MY',
    'raw_payload_available': False, 'scoring_eligible': False,
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def stamp(value):
    if not isinstance(value, str):
        raise ValueError('invalid timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('timezone required')
    return result


def category(action):
    if action == 'Code push' or re.fullmatch(r'Code push \([0-9]+ commits?\)', action):
        return 'push'
    if action == 'Pull request' or (action.startswith('PR ') and action != 'PR review'):
        return 'pull_request'
    if action == 'Issue activity' or action.startswith('Issue '):
        return 'issue_comment' if action == 'Issue comment' else 'issue'
    if action in ('Branch/tag created', 'Branch/tag deleted'):
        return 'ref_change'
    return 'unclassified'


def build(records, key, now):
    if len(key) < 32 or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('32-byte private alias key and zoned time required')
    def alias(kind, value):
        return kind + '-' + hmac.new(key, canonical([kind, value]), hashlib.sha256).hexdigest()
    groups, excluded, seen = defaultdict(list), Counter(), {}
    partial, accepted = 0, []
    today = now.astimezone(MY).date()
    for record in records:
        row = dict(record)
        try:
            meta = json.loads(row['metadata'])
            if not isinstance(meta, dict):
                raise ValueError('invalid metadata')
            namespace, native = row['source_account_id'], row['event_id']
            if (row['source'] != 'github_events' or not isinstance(namespace, str) or not namespace.strip()
                    or not isinstance(native, str) or not native.strip()
                    or not isinstance(row['payload_digest'], str)
                    or not re.fullmatch('[0-9a-f]{64}', row['payload_digest'])):
                raise ValueError('missing native evidence')
            actor = meta.get('actor_id')
            if type(actor) is int and actor > 0:
                identity, basis = ['actor_id', actor], 'native_actor_id'
            elif isinstance(row['user'], str) and row['user'].strip():
                identity, basis = ['login', row['user']], 'login_fallback_unverified'
            else:
                raise ValueError('missing actor')
            local = stamp(row['timestamp']).astimezone(MY)
            if local > now:
                raise ValueError('future timestamp')
            if (not isinstance(row['action'], str) or not isinstance(row['resource'], str)
                    or not isinstance(row['user'], str)):
                raise ValueError('invalid projection')
        except (ValueError, TypeError, KeyError):
            excluded['invalid_projection_or_native_reference'] += 1
            continue
        native_key = (namespace, native)
        projection_sha = digest(row)
        if native_key in seen:
            if seen[native_key] != projection_sha:
                raise ValueError('Conflicting native key; refusing export')
            excluded['duplicate_native_key'] += 1
            continue
        seen[native_key] = projection_sha
        accepted.append(projection_sha)
        if local.date() == today:
            partial += 1
            continue
        principal = [namespace, identity]
        groups[(alias('account', principal), local.date().isoformat(), basis)].append(
            (row, meta, local, alias('repo', [namespace, row['resource']]) if row['resource'].strip() else None,
             alias('evidence', [namespace, native, row['payload_digest'], projection_sha])))
    rows = []
    for (account, day, basis), events in sorted(groups.items()):
        cats = Counter(category(r['action']) for r, _, _, _, _ in events)
        hours = Counter(f'{local.hour:02d}' for _, _, local, _, _ in events)
        repos = Counter(repo for _, _, _, repo, _ in events if repo)
        off_hours = sum(local.weekday() >= 5 or not 8 <= local.hour < 20 for _, _, local, _, _ in events)
        known = [meta['commits'] for r, meta, _, _, _ in events
                 if category(r['action']) == 'push' and type(meta.get('commits')) is int and meta['commits'] >= 0]
        hints = Counter('bot_suffix_hint' if r['user'].endswith('[bot]') else 'unknown'
                        for r, _, _, _, _ in events)
        commit_info = {'known_pushes': len(known), 'unknown_pushes': cats['push'] - len(known),
                       'known_commit_sum': sum(known), 'basis': 'stored metadata only; never action-label count'}
        if cats['push'] and len(known) == cats['push']:
            commit_info['all_push_commit_sum'] = sum(known)
        rows.append({'account': account, 'day': day, 'identity_basis': basis,
                     'features': dict(zip(FEATURES, [len(events), cats['push'], cats['pull_request'],
                         cats['issue'], cats['issue_comment'], cats['ref_change'], len(repos), off_hours])),
                     'action_category_counts': dict(sorted(cats.items())), 'repository_counts': dict(sorted(repos.items())),
                     'local_hour_counts': dict(sorted(hours.items())), 'commit_observability': commit_info,
                     'missing_repository_events': sum(repo is None for _, _, _, repo, _ in events),
                     'provenance_hints': dict(sorted(hints.items())), 'provenance': 'unverified',
                     'first_timestamp_utc': min(t for _, _, t, _, _ in events).astimezone(timezone.utc).isoformat(),
                     'last_timestamp_utc': max(t for _, _, t, _, _ in events).astimezone(timezone.utc).isoformat(),
                     'evidence_refs': sorted(ref for _, _, _, _, ref in events),
                     'coverage': 'bounded_sample_completeness_unknown', 'scoring_eligible': False})
    return {'contract': CONTRACT, 'rows': rows, 'summary': {
        'closed_account_days': len(rows), 'closed_events': sum(r['features']['event_count'] for r in rows),
        'partial_day_events_excluded': partial, 'exclusions': dict(excluded),
        'snapshot_projection_sha256': digest(sorted(accepted)), 'raw_verification_available': False,
        'poll_history_coverage': 'not_assessed', 'trained': False, 'activated': False}}


def export(database, output, key_file):
    database, output, key_file = (Path(p).resolve() for p in (database, output, key_file))
    if output.exists() or output == database or output in database.parents or output == key_file or output in key_file.parents:
        raise ValueError('Fresh output directory separate from database and key required')
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    key = key_file.read_bytes()
    now = datetime.now(timezone.utc)
    columns = 'source, source_account_id, event_id, payload_digest, timestamp, "user", action, resource, metadata'
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        records = db.execute('SELECT ' + columns + ' FROM events WHERE source=? ORDER BY id LIMIT 100001',
                             ('github_events',)).fetchall()
        if len(records) > 100000:
            raise ValueError('Export bound exceeded; no truncated dataset written')
        result = build(records, key, now)
    encoded = canonical(result) + b'\n'
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != code_hash:
        raise ValueError('Exporter changed during snapshot')
    manifest = {'schema': 'github_projection_export_v1', 'created_at_utc': now.isoformat(),
                'dataset_sha256': hashlib.sha256(encoded).hexdigest(), 'contract_sha256': digest(CONTRACT),
                'exporter_sha256': code_hash,
                'storage_access': 'sqlite_mode_ro_query_only_snapshot', 'summary': result['summary']}
    # Output uses a fresh directory; partial writes have no complete manifest.
    output.mkdir(parents=True, exist_ok=False)
    (output / 'dataset.json').write_bytes(encoded)
    (output / 'manifest.json').write_bytes(canonical(manifest) + b'\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--alias-key-file', required=True)
    args = parser.parse_args()
    result = export(args.database, args.output, args.alias_key_file)
    print(json.dumps(result['summary'], sort_keys=True))


if __name__ == '__main__':
    main()
