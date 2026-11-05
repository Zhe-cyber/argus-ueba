"""Re-extract the shared core from the existing inspected prefix only."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.export_clue_dataset import Prefix
from scripts.shared_core_features import PROFILE, FEATURES, K, Day, History, project_clue, instant


def export(events, population):
    history, windows, rows = History(), {}, []
    current = None
    def finish():
        for account, window in sorted(windows.items()):
            snapshot = history.snapshot(window)
            rows.append({'account': account, 'day': window.key[3], **snapshot})
            history.commit_original(window)
    for row in events:
        day = instant(row['time']).date().isoformat()
        if day >= '2017-08-10':
            continue
        if day < '2017-07-07' or row.get('uidType') != 'name':
            continue
        event = project_clue(row)
        if event.account not in population:
            continue
        if current is not None and day < current:
            raise ValueError('Cross-day reversal')
        if current is not None and day != current:
            finish(); windows = {}
        current = day
        windows.setdefault(event.account, Day()).add(event)
    finish()
    summary = {}
    for name, start, end in [('fit', '2017-07-13', '2017-07-26'), ('validation', '2017-07-27', '2017-07-31'),
                              ('calibration', '2017-08-01', '2017-08-04'), ('development', '2017-08-05', '2017-08-09')]:
        selected = [row for row in rows if start <= row['day'] <= end]
        issues = Counter()
        for row in selected:
            issues.update(row['issues'])
        summary[name] = {'observed_days': len(selected), 'eligible_days': sum(row['eligible'] for row in selected),
                         'cold_start_days': sum(row['cold_start'] for row in selected),
                         'resource_or_action_issue_events': dict(issues)}
    return {'profile': PROFILE, 'features': FEATURES, 'k': K, 'status': 'development_only_not_frozen',
            'population': sorted(population), 'rows': rows, 'summary': summary,
            'history_policy': 'prior_observed_days_original_events_only', 'reserved_access': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', required=True); parser.add_argument('--manifest', required=True); parser.add_argument('--out', required=True)
    args = parser.parse_args(); out = Path(args.out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'data'):
        parser.error('New private output below checkout data required')
    prefix = Prefix(args.prefix)
    if prefix.sha256 != '1d4b00276dd73fb67e67e0d50d5af64cf4ab82edc765a6d7b6b902ba1127636f':
        parser.error('Require the inspected prefix')
    raw = Path(args.manifest).read_bytes()
    if hashlib.sha256(raw).hexdigest() != '0d620d90b85746021113a86f4656ec56e572eac8d89df149ee5c39d1b2e5fa8d':
        parser.error('Require the frozen fitting-population manifest')
    population = set(json.loads(raw)['fitting_population'])
    if len(population) != 55:
        parser.error('Require the 55 fitting-selected identities')
    result = export(prefix.events(), population)
    result['bindings'] = {'prefix_sha256': prefix.sha256, 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
                          'sources': {name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes()).hexdigest()
                                      for name in ['shared_core_features.py', 'export_shared_core_development.py', 'clue_features.py', 'export_clue_dataset.py']}}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    print(json.dumps({'profile': PROFILE, 'summary': result['summary'], 'reserved_access': False}))


if __name__ == '__main__':
    main()
