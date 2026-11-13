"""Supplement frozen W6 reporting; never fit, recalibrate or change decisions."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import account_familiarity as familiarity
from scripts.clue_features import instant
from scripts.clue_familiarity_projection import project
from scripts.export_clue_dataset import Prefix
from scripts.personal_baseline import document_digest, quantile_linear
from scripts.resource_observability import resource, token

REPORT_SHA = '966622ad25ce51b3081f4fc5778543d5ecb0195e6910907956b91462914b276c'
TIE_DISTANCE = 1e-12


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def near_threshold(values, threshold):
    if (not isinstance(threshold, (int, float)) or isinstance(threshold, bool)
            or not math.isfinite(threshold)):
        raise ValueError('Invalid threshold')
    present = [v for v in values if v is not None]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in present):
        raise ValueError('Invalid saved score')
    return {'scored_rows': len(present), 'unavailable_rows': len(values) - len(present),
            'strict_alerts': sum(v > threshold for v in present),
            'exact_ties': sum(v == threshold for v in present),
            'within_absolute_1e_minus12': sum(abs(v - threshold) <= TIE_DISTANCE for v in present),
            'near_above': sum(0 < v - threshold <= TIE_DISTANCE for v in present),
            'near_below': sum(0 < threshold - v <= TIE_DISTANCE for v in present)}


def unavailable_breakdown(rows):
    counts = Counter()
    for row in rows:
        if row['scores']['resource'] is not None:
            continue
        stats = row['dimensions']['resources']
        activity = ('no_resource_activity' if stats['distinct_tokens'] == 0 else
                    'only_globally_unseen' if stats['fitting_known_tokens'] == 0 else 'has_fitting_known_resources')
        counts[row['statuses']['resource'], activity] += 1
    return [{'original_status': status, 'resource_activity': activity, 'rows': count}
            for (status, activity), count in sorted(counts.items())]


def prefix_token(path):
    # Coarse string proxy only: no claim that the component is a username/home.
    component = next((part for part in path.split('/') if part), None)
    return token('clue-7119953', 'first_literal_component', component) if component is not None else None


def exclusivity(resources, recipient, donor, counts, prefixes, prefix_users):
    known = {t for t in resources if any(t in own for own in counts.values())}
    donor_only = {t for t in known if t in counts[donor]
                  and all(user == donor or t not in own for user, own in counts.items())}
    exclusive_prefix = {t for t in resources if prefixes[t] is not None
                        and prefix_users.get(prefixes[t], set()) == {donor}}
    return {'distinct_resources': len(resources), 'fitting_known_resources': len(known),
            'globally_unseen_resources': len(resources) - len(known),
            'fitting_known_absent_from_recipient': sum(t not in counts[recipient] for t in known),
            'literal_tokens_seen_only_under_donor_in_fitting': len(donor_only),
            'resources_with_first_component_seen_only_under_donor_in_fitting': len(exclusive_prefix),
            'fitting_known_resources_with_donor_exclusive_first_component': len(exclusive_prefix & known)}


def run(directory, prefix_path, manifest_path, output):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    if output.exists() or not output.parent.is_dir() or not output.is_relative_to((ROOT / 'data/processed').resolve()):
        raise ValueError('Use a new private supplementary output file')
    report_path = directory / 'development_report.json'
    if sha(report_path) != REPORT_SHA:
        raise ValueError('Require the unchanged W6 report')
    report = json.loads(report_path.read_text())
    bindings = {report_path: REPORT_SHA, directory / 'reference.json': report['reference_sha256'],
                directory / 'normal_calibration.json': report['calibration_sha256'],
                Path(manifest_path): report['bindings']['manifest_sha256'],
                Path(prefix_path): report['bindings']['prefix_sha256']}
    if any(sha(path) != expected for path, expected in bindings.items()):
        raise ValueError('Frozen input hash differs')
    for name, expected in report['code_canonical_lf_sha256'].items():
        path = ROOT / 'scripts' / name
        if path.parent != ROOT / 'scripts' or hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() != expected:
            raise ValueError('Original W6 code differs')
    manifest = json.loads(Path(manifest_path).read_text())
    reference = familiarity.load_reference(json.loads((directory / 'reference.json').read_text()))
    calibration = json.loads((directory / 'normal_calibration.json').read_text())
    aliases = {f'cohort-{i + 1}': u for i, u in enumerate(manifest['fitting_population'])}
    users = set(aliases.values())
    if users != set(reference.dimensions['resources'].days):
        raise ValueError('Reference population differs')
    switched = [row for case in report['cases'] for row in case['days']]
    positives = [r for r in switched if r['alerts']['resource'] is True]
    if len(positives) != 6:
        raise ValueError('Original six-positive result differs')
    hit_keys = {(aliases[r['operated_by']], r['date']) for r in positives}
    prefix_users, hit_paths = defaultdict(set), defaultdict(dict)

    def observe(events):
        for event in events:
            if event['uidType'] == 'name':
                actor = hashlib.sha256(('clue-7119953:' + event['uid']).encode()).hexdigest()
                day = instant(event['time']).date().isoformat()
                if actor in users and (reference.start <= day <= reference.end or (actor, day) in hit_keys):
                    item = resource('clue-7119953', event)
                    if item.object is not None:
                        prefix = prefix_token(event['params']['path'])
                        if reference.start <= day <= reference.end and prefix is not None:
                            prefix_users[prefix].add(actor)
                        if (actor, day) in hit_keys:
                            hit_paths[actor, day][item.object] = prefix
            yield event

    rows = project(observe(Prefix(prefix_path).events()))
    cal_start, cal_end = calibration['resource']['start'], calibration['resource']['end']
    cal_rows = familiarity.checked([r for r in rows if r['user'] in users and cal_start <= r['date'] <= cal_end], cal_start, cal_end)
    cal_values = [familiarity.score(reference, row) for row in cal_rows]
    for mode in ('resource', 'joint'):
        available = [s['scores'][mode] for s in cal_values if s['scores'][mode] is not None]
        if (document_digest(cal_rows) != calibration[mode]['rows_sha256']
                or quantile_linear(available) != calibration[mode]['threshold']
                or sum(v > calibration[mode]['threshold'] for v in available) != calibration[mode]['normal_calibration_alerts']):
            raise ValueError('Saved calibration inference does not reproduce')
    index = {(r['user'], r['date']): r for r in rows}
    hit_stats, unique_positive_resources = [], set()
    for saved in positives:
        donor, recipient = aliases[saved['operated_by']], aliases[saved['account']]
        paths = hit_paths[donor, saved['date']]
        if set(paths) != set(index[donor, saved['date']]['resources']):
            raise ValueError('Native positive-day resource projection differs')
        stats = exclusivity(set(paths), recipient, donor, reference.dimensions['resources'].counts, paths, prefix_users)
        original = saved['dimensions']['resources']
        if stats['distinct_resources'] != original['distinct_tokens'] or stats['fitting_known_resources'] != original['fitting_known_tokens']:
            raise ValueError('Positive-day resource coverage differs from report')
        unique_positive_resources.update(paths)
        hit_stats.append({'account': saved['account'], 'date': saved['date'], 'operated_by': saved['operated_by'], **stats})
    near = {mode: {'calibration': near_threshold([s['scores'][mode] for s in cal_values], calibration[mode]['threshold']),
                   'normal_development': near_threshold([r['scores'][mode] for r in report['development_normal_days']], calibration[mode]['threshold']),
                   'switched_development': near_threshold([r['scores'][mode] for r in switched], calibration[mode]['threshold'])}
            for mode in ('resource', 'joint')}
    tie_rows = [s for s in cal_values if s['scores']['resource'] is not None
                and abs(s['scores']['resource'] - calibration['resource']['threshold']) <= TIE_DISTANCE]
    result = {'status': 'reporting_supplement_only', 'activated': False,
              'computed_at_utc': datetime.now(timezone.utc).isoformat(), 'original_report_sha256': REPORT_SHA,
              'near_threshold': near, 'tie_distance_reporting_only': TIE_DISTANCE,
              'calibration_near_tie_resource_fitting_dates': dict(sorted(Counter(s['dimensions']['resources']['fitting_usable_dates'] for s in tie_rows).items())),
              'unavailable_breakdown': {'normal_development': unavailable_breakdown(report['development_normal_days']),
                                        'switched_development': unavailable_breakdown(switched)},
              'positive_day_literal_exclusivity': hit_stats,
              'distinct_resources_across_all_positive_days': len(unique_positive_resources),
              'diagnostic_source_canonical_lf_sha256': hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
              'checks': {'frozen_code_and_inputs_verified': True, 'calibration_row_digest_and_original_results_reproduced': True,
                         'native_positive_resource_counts_match': True, 'no_fit_recalibration_or_decision_changes': True},
              'limitations': ['Token exclusivity is descriptive in the selected fitting sample, not resource ownership or ACL evidence.',
                             'First nonempty slash component is a coarse namespace proxy, not proof of a personal home directory.',
                             'Supplement uses previously inspected development data; repeated paths/days do not constitute independent attacks.']}
    if any(sha(path) != expected for path, expected in bindings.items()):
        raise ValueError('Frozen inputs changed during supplement')
    with output.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('directory', 'prefix', 'manifest', 'out'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.directory, args.prefix, args.manifest, args.out), indent=2))
    except Exception as error:
        print(f'Report supplement stopped: {type(error).__name__}; no raw records displayed.', file=sys.stderr)
        sys.exit(1)
