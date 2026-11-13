"""Pinned fitting/normal-validation exploration, no detector or attack evaluation."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import context_feature_diagnostic as diagnostic
from scripts.clue_features import KNOWN_ACTIONS, REQUIRED_PATH, instant
from scripts.export_clue_dataset import Prefix
from scripts.personal_baseline import document_digest
from scripts.resource_observability import resource, token
from scripts.review_familiarity_diagnostics import REPORT_SHA, sha


def project(events, population):
    windows, first, last, memberships = {}, None, None, 0
    for event in events:
        day = instant(event['time']).date().isoformat()
        first, last = min(first, day) if first else day, max(last, day) if last else day
        if event['uidType'] != 'name' or not '2017-07-13' <= day <= '2017-07-31':
            continue
        user = hashlib.sha256(('clue-7119953:' + event['uid']).encode()).hexdigest()
        if user not in population:
            continue
        key = user, day
        if key not in windows:
            if len(windows) >= 200_000:
                raise ValueError('Account-day bound exceeded')
            windows[key] = {'user': user, 'date': day, 'event_count': 0, 'paths': {}, 'uid_signature_paths': set(),
                            'actions': Counter(), 'coverage': dict.fromkeys(
                                ('invalid_resource_events', 'missing_required_paths', 'unknown_action_events'), 0)}
        row = windows[key]
        action = event.get('type')
        if not isinstance(action, str) or not action or len(action) > 128:
            raise ValueError('Invalid action')
        row['event_count'] += 1
        row['actions'][token('clue-7119953', 'action', action)] += 1
        row['coverage']['unknown_action_events'] += action not in KNOWN_ACTIONS
        item = resource('clue-7119953', event)
        params = event.get('params', {})
        row['coverage']['invalid_resource_events'] += not isinstance(params, dict) or ('path' in params and item.object is None)
        row['coverage']['missing_required_paths'] += action in REQUIRED_PATH and item.object is None
        if item.object is not None and item.object not in row['paths']:
            path = params['path']
            row['paths'][item.object] = tuple(diagnostic.parent_category(path, depth) for depth in (1, 2))
            parents = [p for p in path.split('/') if p][:-1]
            if event['uid'] in parents[:2]:
                row['uid_signature_paths'].add(item.object)
            memberships += 1
            if memberships > 4_000_000:
                raise ValueError('Path membership bound exceeded')
    if first is None or first >= '2017-07-13' or last <= '2017-07-31':
        raise ValueError('Diagnostic window is not interior to native capture')
    rows = []
    for _, window in sorted(windows.items()):
        rows.append({'user': window['user'], 'date': window['date'], 'event_count': window['event_count'],
                     'distinct_paths': len(window['paths']), 'exact_uid_parent_match_paths': len(window['uid_signature_paths']),
                     'coverage': window['coverage'],
                     'views': {'action_mix': dict(window['actions']),
                               **{view: dict(Counter(pair[j] for pair in window['paths'].values()))
                                  for j, view in enumerate(('parent_depth1', 'parent_depth2'))}}})
    return rows


def write_new(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(data, handle, indent=2, allow_nan=False)
        handle.write('\n')


def run(original_directory, prefix_path, manifest_path, output):
    output, original_directory = Path(output).resolve(), Path(original_directory).resolve()
    if output.exists() or not output.is_relative_to((ROOT / 'data/processed').resolve()):
        raise ValueError('Use a new private output directory')
    report_path = original_directory / 'development_report.json'
    if sha(report_path) != REPORT_SHA:
        raise ValueError('Require the frozen W6 report')
    original = json.loads(report_path.read_text())
    bindings = {report_path: REPORT_SHA, Path(manifest_path): original['bindings']['manifest_sha256'],
                Path(prefix_path): original['bindings']['prefix_sha256']}
    if any(sha(path) != expected for path, expected in bindings.items()):
        raise ValueError('Frozen input differs')
    for name, expected in original['code_canonical_lf_sha256'].items():
        path = ROOT / 'scripts' / name
        if path.parent != ROOT / 'scripts' or hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() != expected:
            raise ValueError('Frozen original source differs')
    manifest = json.loads(Path(manifest_path).read_text())
    users = manifest['fitting_population']
    if len(users) != 55 or len(set(users)) != 55:
        raise ValueError('Frozen population differs')
    rows = project(Prefix(prefix_path).events(), set(users))
    fitting = diagnostic.checked([r for r in rows if r['date'] <= '2017-07-26'], '2017-07-13', '2017-07-26')
    validation = diagnostic.checked([r for r in rows if r['date'] > '2017-07-26'], '2017-07-27', '2017-07-31')
    if len(fitting) != 605 or len(validation) != 188 or sum(r['event_count'] for r in fitting) != 834907:
        raise ValueError('Frozen native counts differ')
    reference = diagnostic.fit(fitting, '2017-07-13', '2017-07-26')
    before = document_digest(reference.document())
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / 'reference.json', reference.document())
    if document_digest(json.loads((output / 'reference.json').read_text())) != before:
        raise ValueError('Persisted reference differs')
    results = diagnostic.compare(reference, validation, '2017-07-27', '2017-07-31')
    aliases = {u: f'cohort-{i + 1}' for i, u in enumerate(users)}
    result = {'method': diagnostic.METHOD, 'status': 'exploratory_normal_separation_only', 'activated': False,
              'computed_at_utc': datetime.now(timezone.utc).isoformat(), 'method_spec': 'specs/W8-context-feature-diagnostic.md; d418ed7',
              'original_w6_report_sha256': REPORT_SHA, 'prefix_sha256': bindings[Path(prefix_path)],
              'manifest_sha256': bindings[Path(manifest_path)], 'reference_sha256': sha(output / 'reference.json'),
              'source_canonical_lf_sha256': {name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                            for name in ('context_feature_diagnostic.py', 'run_context_feature_diagnostic.py')},
              'fitting_rows': len(fitting), 'normal_validation_rows': len(validation), 'frozen_population': len(users),
              'eligible_references': {view: len(reference.centres[view]) for view in diagnostic.VIEWS},
              'views': {view: diagnostic.summarize(records) for view, records in results.items()},
              'normal_validation_days': {view: [{**{k: v for k, v in row.items() if k != 'user'}, 'account': aliases[row['user']]}
                                                for row in records] for view, records in results.items()},
              'exact_uid_parent_component_proxy': {label: {'distinct_account_day_paths': sum(r['distinct_paths'] for r in subset),
                                                            'paths_with_uid_match_in_first_two_parent_components': sum(r['exact_uid_parent_match_paths'] for r in subset),
                                                            'account_days_with_any_uid_match': sum(r['exact_uid_parent_match_paths'] > 0 for r in subset)}
                                                     for label, subset in [('fitting', fitting), ('normal_validation', validation)]},
              'limitations': ['Exploratory comparison on inspected normal validation, not attack recall or a fresh test.',
                             'Own-reference closeness is not a calibrated anomaly rule, peer-group model or compromise probability.',
                             'Literal parent proxies may encode personal namespaces; dropping leaves does not prove generalisable behaviour.',
                             'No exact uid match cannot exclude encoded identity cues or shared namespaces with personal subfolders.',
                             'Days/accounts correlate and coverage differs across views; no statistical superiority or accuracy claim.',
                             'Single-service CLUE results do not validate source-context semantics on live AWS/Cloudflare/GitHub.']}
    if before != document_digest(reference.document()) or any(sha(path) != expected for path, expected in bindings.items()):
        raise ValueError('Reference or original inputs changed')
    result['checks'] = {'original_source_and_inputs_verified': True, '605_fit_and_188_validation_rows_match': True,
                        'reference_saved_and_unchanged': True, 'only_fitting_and_normal_validation_enter_analysis': True}
    write_new(output / 'diagnostic_report.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('original-directory', 'prefix', 'manifest', 'out'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        result = run(args.original_directory, args.prefix, args.manifest, args.out)
        print(json.dumps({k: result[k] for k in ('status', 'eligible_references', 'views', 'exact_uid_parent_component_proxy', 'checks')}))
    except Exception as error:
        print(f'Feature diagnostic stopped: {type(error).__name__}; no raw records displayed.', file=sys.stderr)
        sys.exit(1)
