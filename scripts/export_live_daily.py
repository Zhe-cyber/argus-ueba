"""Export only audited closed ordinary MY account-days; never trains a model."""
from collections import defaultdict
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import live_history_readiness as readiness
from scripts.aws_lab_daily_features import CONTRACT, extract
from scripts.simulation_lab import buckets

SOURCES = ('scripts/export_live_daily.py', 'scripts/aws_lab_daily_features.py',
           'scripts/live_history_readiness.py', 'scripts/persona_history_plan.py', 'scripts/simulation_lab.py')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def export(ledger, database, account, stack, output, now=None):
    output = Path(output).resolve()
    inputs = [Path(ledger).resolve(), Path(database).resolve()]
    if output.exists() or any(output == p or output in p.parents for p in inputs):
        raise ValueError('Use a fresh dedicated output directory separate from source stores')
    if output == (ROOT / 'ml/models').resolve() or (ROOT / 'ml/models').resolve() in output.parents:
        raise ValueError('Never export into active model directory')
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    before = hashes()
    report, evidence = readiness.evaluate(ledger, database, account, stack, now, with_evidence=True)
    resources = dict(zip(buckets(account, stack), CONTRACT['resource_domain']))
    grouped = defaultdict(list)
    for event in evidence:
        grouped[(event['day'], event['persona'], event['partition'])].append(event)
    coverage = {(r['day'], r['persona']): r for r in report['days']}
    rows = []
    for (day, role, partition), events in sorted(grouped.items()):
        events.sort(key=lambda e: (e['timestamp'], e['event_id']))
        counts = extract(events, resources)
        selected = coverage[(day, role)]
        if counts['features']['event_count'] != selected['verified']:
            raise ValueError('Audited evidence count differs from coverage')
        rows.append({'persona': role, 'date_local': day, 'partition': partition, 'complete_day': True,
                     **counts, 'coverage': {k: selected[k] for k in ('planned', 'verified', 'missing', 'missed',
                                                 'unresolved', 'verified_fraction_of_planned')},
                     'evidence_sha256': digest(events)})
    if hashes() != before:
        raise ValueError('Exporter source changed during snapshot')
    last_day = readiness.WINDOWS['normal_calibration'][1]
    windows_closed = now.astimezone(readiness.MALAYSIA).date().isoformat() > last_day
    status = 'empty_dataset' if not rows else 'normal_windows_complete' if windows_closed else 'partial_dataset'
    dataset = {'schema': 'argus_live_daily_dataset_v1', 'dataset_kind': 'audited_aws_daily_workloads',
               'status': status, 'profile': CONTRACT['profile'], 'feature_contract_sha256': digest(CONTRACT),
               'rows': rows, 'readiness': report,
               'provenance': {'exported_at_utc': now.isoformat(), 'profile_sha256': readiness.PROFILE_SHA,
                              'source_sha256': before, 'native_evidence_sha256': digest(sorted(evidence, key=lambda e: e['action_id'])),
                              'scope_sha256': digest([account, stack]), 'included_native_events': len(evidence)},
               'trained': False, 'activated': False,
               'limitations': ['Controlled AWS machine workloads, not independently observed human normality.',
                               'Normal windows complete denotes closed dates, not complete coverage or model qualification.',
                               'Count features alone may hide resource substitution; categorical context is preserved separately.',
                               'No training, validation-score inspection, calibration or held-out case data used.']}
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.with_name(output.name + '.' + uuid4().hex + '.staging')
    stage.mkdir()
    try:
        (stage / 'feature_contract.json').write_bytes(canonical(CONTRACT))
        data_bytes = canonical(dataset) + b'\n'
        (stage / 'dataset.json').write_bytes(data_bytes)
        manifest = {'schema': 'argus_live_daily_export_manifest_v1', 'status': status,
                    'dataset_sha256': hashlib.sha256(data_bytes).hexdigest(),
                    'feature_contract_sha256': digest(CONTRACT), 'source_sha256': before,
                    'partition_rows': {part: sum(r['partition'] == part for r in rows) for part in readiness.WINDOWS},
                    'included_native_events': len(evidence), 'history_gates_pass': report['history_gates_pass'],
                    'trained': False, 'activated': False}
        (stage / 'manifest.json').write_bytes(canonical(manifest) + b'\n')
        stage.rename(output)  # Fresh version only; never replaces an existing nonempty dataset.
    finally:
        if stage.exists():
            if stage.is_symlink() or stage.resolve().parent != output.parent:
                raise ValueError('Unexpected staging cleanup path; refusing recursive removal')
            shutil.rmtree(stage)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot-config', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        cfg = json.loads(args.pilot_config.read_text())
        result = export(Path(cfg['ledger_dir']) / 'ledger.db', Path(cfg['connected_dir']) / 'events.db',
                        cfg['account_id'], cfg['stack'], args.out)
        print(json.dumps(result))
        return 0
    except Exception:
        print('Daily export refused; check frozen plans, receipt evidence and a fresh output directory. No raw events displayed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
