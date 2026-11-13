"""Normal-only development rejection gate. No switch scoring or fresh data."""
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
from scripts import equal_history_novelty as novelty
from scripts.clue_familiarity_projection import project
from scripts.export_clue_dataset import Prefix
from scripts.personal_baseline import document_digest
from scripts.review_familiarity_diagnostics import REPORT_SHA, sha


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def run(original_directory, prefix_path, manifest_path, output):
    output, original_directory = Path(output).resolve(), Path(original_directory).resolve()
    if output.exists() or not output.is_relative_to((ROOT / 'data/processed').resolve()):
        raise ValueError('Use a new private output directory')
    original_report = original_directory / 'development_report.json'
    if sha(original_report) != REPORT_SHA:
        raise ValueError('Require the frozen W6 report')
    original = json.loads(original_report.read_text())
    bindings = {original_report: REPORT_SHA, Path(manifest_path): original['bindings']['manifest_sha256'],
                Path(prefix_path): original['bindings']['prefix_sha256']}
    if any(sha(path) != expected for path, expected in bindings.items()):
        raise ValueError('Original inputs differ')
    for name, expected in original['code_canonical_lf_sha256'].items():
        path = ROOT / 'scripts' / name
        if path.parent != ROOT / 'scripts' or hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() != expected:
            raise ValueError('Frozen W6 source differs')
    manifest = json.loads(Path(manifest_path).read_text())
    users = manifest['fitting_population']
    if len(users) != 55 or len(set(users)) != 55:
        raise ValueError('Require the original population')
    rows = project(Prefix(prefix_path).events())
    fitting = [r for r in rows if r['user'] in users and '2017-07-13' <= r['date'] <= '2017-07-26']
    cal_rows = novelty.checked([r for r in rows if r['user'] in users and '2017-08-01' <= r['date'] <= '2017-08-04'],
                              '2017-08-01', '2017-08-04')
    if len(fitting) != 605 or len(cal_rows) != 169:
        raise ValueError('Frozen fitting/calibration projection differs')
    reference = novelty.fit(fitting, '2017-07-13', '2017-07-26')
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / 'reference.json', reference.document())
    restored = novelty.load_reference(json.loads((output / 'reference.json').read_text()))
    if document_digest(restored.document()) != document_digest(reference.document()):
        raise ValueError('Persisted reference differs')
    reference = restored
    calibration = novelty.calibrate(reference, cal_rows, '2017-08-01', '2017-08-04')
    write_new(output / 'normal_calibration.json', calibration)
    scored = [novelty.score(reference, r) for r in cal_rows]
    aliases = {u: f'cohort-{i + 1}' for i, u in enumerate(users)}
    if any(sha(path) != expected for path, expected in bindings.items()):
        raise ValueError('Original inputs changed')
    result = {'method': novelty.METHOD, 'status': 'development_calibration_gate_only', 'activated': False,
              'computed_at_utc': datetime.now(timezone.utc).isoformat(),
              'method_spec': 'specs/W7-equal-history-calibration-gate.md; fixed in 7eab957',
              'original_w6_report_sha256': REPORT_SHA, 'native_prefix_sha256': bindings[Path(prefix_path)],
              'manifest_sha256': bindings[Path(manifest_path)],
              'source_canonical_lf_sha256': {name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                            for name in ('equal_history_novelty.py', 'check_equal_history_calibration.py')},
              'reference_sha256': sha(output / 'reference.json'), 'calibration_sha256': sha(output / 'normal_calibration.json'),
              'frozen_population': len(users), 'eligible_accounts': len(reference.personal),
              'reference_resource_dates_per_eligible_account': novelty.K,
              'calibration': calibration, 'availability_status_counts': dict(sorted(Counter(s['status'] for s in scored).items())),
              'calibration_days': [{'account': aliases[r['user']], 'date': r['date'], **s} for r, s in zip(cal_rows, scored)],
              'switch_evaluation_status': 'not_run_saturation_gate' if calibration['gate'] == 'saturated_no_go' else 'not_run_pending_separate_comparison',
              'fresh_data_read': False, 'checks': {'original_source_and_inputs_verified': True, 'fitting_and_calibration_counts_match': True,
                                                 'reference_saved_and_reloaded_before_calibration': True, 'no_existing_artifacts_overwritten': True},
              'limitations': ['Inspected CLUE normal calibration only; no attack/case recall measured.',
                             'Fixed five fitting dates remove history-length ceiling disparity but may discard useful older history.',
                             'Literal paths are not proof of global object identity, ownership, permissions or intent.',
                             'A bounded score at threshold1 cannot exceed the strict rule; zero alerts would not demonstrate good detection.',
                             'No v1/AE inference was rerun by this gate, and no live detector was validated.']}
    write_new(output / 'calibration_gate_report.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('original-directory', 'prefix', 'manifest', 'out'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        result = run(args.original_directory, args.prefix, args.manifest, args.out)
        print(json.dumps({k: result[k] for k in ('status', 'eligible_accounts', 'calibration',
                                                'availability_status_counts', 'switch_evaluation_status', 'checks')}))
    except Exception as error:
        print(f'Calibration gate stopped: {type(error).__name__}; no raw records displayed.', file=sys.stderr)
        sys.exit(1)
