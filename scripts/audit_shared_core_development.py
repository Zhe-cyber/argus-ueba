"""Development-only CLUE namespace/active-day coverage audit; no scoring."""
import argparse
from collections import Counter, defaultdict
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


def audit(events, population):
    population = set(population)
    days, paths, roots, depth = defaultdict(set), set(), set(), Counter()
    per_day_roots, per_day_paths = defaultdict(set), defaultdict(set)
    counts = Counter()
    for row in events:
        day = instant(row['time']).date().isoformat()
        # The supplied reader validates records, but no later record contributes.
        if not '2017-07-07' <= day <= '2017-08-09' or row['uidType'] != 'name':
            continue
        user = hashlib.sha256(('clue-7119953:' + row['uid']).encode()).hexdigest()
        if user not in population:
            continue
        days[user].add(day)
        # Namespace semantics only from fitting, not validation/calibration.
        if not '2017-07-13' <= day <= '2017-07-26':
            continue
        counts['fitting_events'] += 1
        params = row.get('params', {})
        path = params.get('path') if isinstance(params, dict) else None
        if not isinstance(path, str) or not path:
            counts['events_without_path'] += 1
            continue
        parts = [part for part in path.split('/') if part]
        if not parts:
            counts['empty_namespace_paths'] += 1
            continue
        counts['path_events'] += 1
        counts['first_component_equals_actor_uid'] += parts[0] == row['uid']
        depth[len(parts)] += 1
        paths.add(path)
        roots.add(parts[0])
        per_day_paths[user, day].add(path)
        per_day_roots[user, day].add(parts[0])
    windows = {'fit': ('2017-07-13', '2017-07-26'),
               'validation': ('2017-07-27', '2017-07-31'),
               'calibration': ('2017-08-01', '2017-08-04'),
               'development': ('2017-08-05', '2017-08-09')}
    coverage = {}
    for name, (start, end) in windows.items():
        eligible = {str(k): 0 for k in (3, 5, 7)}
        total = 0
        for observed in days.values():
            for day in sorted(observed):
                if start <= day <= end:
                    total += 1
                    prior = sum(d < day for d in observed)
                    for k in (3, 5, 7):
                        eligible[str(k)] += prior >= k
        coverage[name] = {'observed_account_days': total, 'eligible_by_k': eligible}
    def summary(values):
        values = list(values)
        return None if not values else {'min': min(values), 'median': statistics.median(values), 'max': max(values)}
    return {'status': 'development_only_not_frozen', 'scoring_performed': False,
            'population': len(population), 'coverage': coverage,
            'fitting_namespace': {'counts': dict(counts), 'distinct_paths': len(paths),
                'distinct_top_level_namespaces': len(roots), 'path_depth_counts': dict(depth),
                'distinct_paths_per_path_bearing_day': summary(map(len, per_day_paths.values())),
                'distinct_namespaces_per_path_bearing_day': summary(map(len, per_day_roots.values()))},
            'limitations': ['No ownership/container semantics established by lexical matches.',
                            'Eligibility counts are active-day history coverage, not complete feature validity.',
                            'No attack scenarios, model scores or reserved dates contribute.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    if not out.is_relative_to((ROOT / 'data').resolve()) or out.exists():
        parser.error('Use a new private file below this checkout data directory')
    prefix = Prefix(args.prefix)
    if prefix.sha256 != '1d4b00276dd73fb67e67e0d50d5af64cf4ab82edc765a6d7b6b902ba1127636f':
        parser.error('Require the existing inspected prefix')
    manifest_bytes = Path(args.manifest).read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != '0d620d90b85746021113a86f4656ec56e572eac8d89df149ee5c39d1b2e5fa8d':
        parser.error('Require the frozen fitting-population manifest')
    population = json.loads(manifest_bytes)['fitting_population']
    if len(population) != 55 or len(set(population)) != 55:
        parser.error('Require the frozen fitting-selected population')
    result = audit(prefix.events(), population)
    result['bindings'] = {'prefix_sha256': prefix.sha256,
                          'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
                          'audit_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
