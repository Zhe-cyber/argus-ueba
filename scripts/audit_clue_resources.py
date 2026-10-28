"""Aggregate fitting-only resource audit; no scores, model load or cloud calls."""
import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.clue_features import instant
from scripts.export_clue_dataset import Prefix
from scripts.resource_observability import CONTRACT, resource

PREFIX_SHA = '1d4b00276dd73fb67e67e0d50d5af64cf4ab82edc765a6d7b6b902ba1127636f'
MANIFEST_SHA = '0d620d90b85746021113a86f4656ec56e572eac8d89df149ee5c39d1b2e5fa8d'


def audit(events, population, start, end):
    if (date.fromisoformat(start).isoformat() != start or
            date.fromisoformat(end).isoformat() != end or start > end):
        raise ValueError('Require ordered exact dates')
    population = frozenset(population)
    if not population:
        raise ValueError('Require a fitting-selected population')
    statuses, shapes = Counter(), Counter()
    owners, by_user, active = defaultdict(set), defaultdict(set), set()
    path_dates = defaultdict(set)
    events_with_shared_literal = Counter()
    for event in events:
        day = instant(event['time']).date().isoformat()
        if not start <= day <= end or event.get('uidType') != 'name':
            continue
        user = hashlib.sha256(('clue-7119953:' + event['uid']).encode()).hexdigest()
        if user not in population:
            continue
        active.add((user, day))
        item = resource('clue-7119953', event)
        statuses[item.status] += 1
        if item.object is None:
            continue
        path = event['params']['path']
        shapes['leading_slash' if path.startswith('/') else 'no_leading_slash'] += 1
        owners[item.object].add(user)
        by_user[user].add(item.object)
        path_dates[user].add(day)
        events_with_shared_literal[item.object] += 1
    sizes = [len(by_user.get(user, ())) for user in population]
    shared = {key for key, users in owners.items() if len(users) > 1}
    return {
        'contract': CONTRACT, 'status': 'fitting_coverage_only', 'activated': False,
        'window_utc': [start, end], 'frozen_population': len(population),
        'active_account_days': len(active), 'active_accounts': len({u for u, _ in active}),
        'events': sum(statuses.values()), 'resource_status_counts': dict(sorted(statuses.items())),
        'literal_path_shape_counts': dict(sorted(shapes.items())),
        'distinct_literal_path_tokens': len(owners),
        'tokens_seen_under_multiple_accounts': len(shared),
        'path_events_with_multi_account_literal_token': sum(events_with_shared_literal[t] for t in shared),
        'accounts_with_observed_paths': len(by_user),
        'account_days_with_observed_paths': sum(len(days) for days in path_dates.values()),
        'accounts_with_paths_on_at_least_five_dates': sum(len(days) >= 5 for days in path_dates.values()),
        'distinct_paths_per_frozen_account': {'min': min(sizes), 'median': statistics.median(sizes), 'max': max(sizes)},
        'limitations': ['Literal reuse does not establish shared object identity, ownership or access rights.',
                        'No validation, calibration, switch or development rows contribute to these aggregates.',
                        'Coverage counts do not demonstrate account separation or anomaly detection.'],
    }


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(prefix_path, manifest_path, output):
    output = Path(output).resolve()
    if output.exists() or not output.is_relative_to((ROOT / 'data/processed').resolve()) or not output.parent.is_dir():
        raise ValueError('Use a new file in an existing private data/processed directory')
    if sha(manifest_path) != MANIFEST_SHA:
        raise ValueError('Require the frozen manifest')
    manifest = json.loads(Path(manifest_path).read_text())
    prefix = Prefix(prefix_path)
    if prefix.sha256 != PREFIX_SHA:
        raise ValueError('Require the existing inspected prefix')
    population = manifest['fitting_population']
    if len(population) != 55 or len(set(population)) != 55:
        raise ValueError('Fitting population differs')
    result = audit(prefix.events(), population, '2017-07-13', '2017-07-26')
    if result['active_account_days'] != 605 or result['active_accounts'] != 55:
        raise ValueError('Fitting projection differs')
    if sha(prefix_path) != PREFIX_SHA or sha(manifest_path) != MANIFEST_SHA:
        raise ValueError('Frozen input changed during audit')
    result['bindings'] = {'prefix_sha256': PREFIX_SHA, 'manifest_sha256': MANIFEST_SHA,
                          'audit_source_sha256': sha(__file__),
                          'adapter_source_sha256': sha(ROOT / 'scripts/resource_observability.py')}
    with output.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.prefix, args.manifest, args.out), indent=2))
