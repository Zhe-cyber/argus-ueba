"""Fixed JS normal-calibration gate; no switches, fresh data or live activation."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import context_score_calibration as scoring
from scripts import context_feature_diagnostic as context
from scripts.export_clue_dataset import Prefix
from scripts.personal_baseline import document_digest
from scripts.project_context_period import project

W8_REPORT_SHA = '3b5806c902c8c51802c352e4426426c84b5f451cda47785890b969c2cb3714ca'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(reference_directory, dataset_path, manifest_path, prefix_path, output):
    output, reference_directory = Path(output).resolve(), Path(reference_directory).resolve()
    if output.exists() or not output.is_relative_to((ROOT / 'data/processed').resolve()):
        raise ValueError('Use a new private output directory')
    report_path, reference_path = reference_directory / 'diagnostic_report.json', reference_directory / 'reference.json'
    if sha(report_path) != W8_REPORT_SHA:
        raise ValueError('Require the frozen W8 report')
    original = json.loads(report_path.read_text())
    bindings = {report_path: W8_REPORT_SHA, reference_path: original['reference_sha256'],
                Path(manifest_path): original['manifest_sha256'], Path(prefix_path): original['prefix_sha256']}
    if any(sha(path) != expected for path, expected in bindings.items()):
        raise ValueError('Frozen W8 input differs')
    for name, expected in original['source_canonical_lf_sha256'].items():
        path = ROOT / 'scripts' / name
        if path.parent != ROOT / 'scripts' or hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() != expected:
            raise ValueError('Frozen W8 source differs')
    manifest = json.loads(Path(manifest_path).read_text())
    if sha(dataset_path) != manifest['dataset_sha256']:
        raise ValueError('Frozen feature export differs')
    bindings[Path(dataset_path)] = manifest['dataset_sha256']
    dataset = json.loads(Path(dataset_path).read_text())
    users = manifest['fitting_population']
    reference = scoring.load_reference(json.loads(reference_path.read_text()))
    if (len(users) != 55 or len(set(users)) != 55 or set(reference.days['action_mix']) != set(users)
            or reference.start != '2017-07-13' or reference.end != '2017-07-26'):
        raise ValueError('Reference population/window differs')
    rows = context.checked(project(Prefix(prefix_path).events(), set(users), '2017-08-01', '2017-08-04'),
                           '2017-08-01', '2017-08-04')
    expected = {(r['user'], r['date']): r for r in dataset['rows']
                if r['user'] in users and '2017-08-01' <= r['date'] <= '2017-08-04'}
    if len(rows) != 169 or len(expected) != 169 or set(expected) != {(r['user'], r['date']) for r in rows}:
        raise ValueError('Calibration account-day projection differs')
    for row in rows:
        old = expected[row['user'], row['date']]
        if (row['event_count'] != old['features']['event_count']
                or row['distinct_paths'] != old['features']['unique_paths']
                or len(row['views']['action_mix']) != old['features']['unique_actions']
                or row['coverage']['missing_required_paths'] != old['coverage']['missing_required_paths']
                or row['coverage']['unknown_action_events'] != old['coverage']['unknown_action_events']):
            raise ValueError('Calibration native counts/coverage differ')
    before = document_digest(reference.document())
    calibration, scored = scoring.calibrate(reference, rows, '2017-08-01', '2017-08-04')
    output.mkdir(parents=True, exist_ok=False)
    def write(name, value):
        with (output / name).open('x', encoding='utf-8', newline='\n') as handle:
            json.dump(value, handle, indent=2, allow_nan=False)
            handle.write('\n')
    write('normal_calibration.json', calibration)
    aliases = {u: f'cohort-{i + 1}' for i, u in enumerate(users)}
    result = {'method': scoring.METHOD, 'status': 'normal_calibration_gate_only', 'activated': False,
              'computed_at_utc': datetime.now(timezone.utc).isoformat(),
              'method_spec': 'specs/W10-context-score-calibration.md; fixed in be0ba6f',
              'primary_candidate': 'joint_primary', 'primary_gate': calibration['joint_primary']['gate'],
              'calibration': calibration, 'normal_calibration_rows': len(rows),
              'frozen_population': len(users), 'eligible_fitting_references': {v: len(reference.centres[v]) for v in context.VIEWS},
              'calibration_days': [{'account': aliases[r['user']], 'date': r['date'], **s} for r, s in scored],
              'bindings': {'w8_report_sha256': W8_REPORT_SHA, 'reference_file_sha256': sha(reference_path),
                           'dataset_sha256': manifest['dataset_sha256'], 'manifest_sha256': sha(manifest_path), 'prefix_sha256': sha(prefix_path)},
              'source_canonical_lf_sha256': {name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                            for name in ('context_score_calibration.py', 'project_context_period.py', 'calibrate_context_score.py', 'personal_baseline.py')},
              'calibration_sha256': sha(output / 'normal_calibration.json'), 'switch_evaluation_status': 'not_run',
              'fresh_data_read': False,
              'limitations': ['Inspected CLUE normal calibration only, not fresh validation or measured attack recall.',
                             'Primary fixed before scores; passing controls do not replace a failed primary.',
                             'The near-ceiling gate does not modify strict decisions or reduce thresholds.',
                             'A passing gate permits only a development comparison, not live activation.',
                             'Literal context can encode dataset namespaces; no global ownership/ACL semantics or multi-cloud effectiveness proved.',
                             'Correlated normal days and small coverage do not guarantee a future 1% alert rate.']}
    if before != document_digest(reference.document()) or any(sha(path) != expected for path, expected in bindings.items()):
        raise ValueError('Reference or frozen inputs changed')
    result['checks'] = {'frozen_w8_source_and_inputs_verified': True, 'json_reference_roundtrip_identical': True,
                        'native_calibration_matches_169_frozen_rows': True, 'reference_and_inputs_unchanged': True,
                        'no_switch_fresh_or_live_scores': True}
    write('calibration_gate_report.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference-directory', 'dataset', 'manifest', 'prefix', 'out'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        result = run(args.reference_directory, args.dataset, args.manifest, args.prefix, args.out)
        print(json.dumps({k: result[k] for k in ('status', 'primary_candidate', 'primary_gate', 'calibration', 'checks')}))
    except Exception as error:
        print(f'Context calibration stopped: {type(error).__name__}; no native records displayed.', file=sys.stderr)
        sys.exit(1)
