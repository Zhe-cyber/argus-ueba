"""Isolated engineering replay from fitting aggregates. Never a qualifying release."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import live_development_checks as development, export_live_daily as exporter
from scripts import train_live_daily as trainer, reserved_study as reserved
from scripts import evaluate_reserved_study as evaluator, run_persona_history as history

DUMMY_ACCOUNT, STACK = '000000000000', 'argus-ueba-actors'
SIMULATED_FREEZE = datetime(2026, 11, 13, 12, tzinfo=reserved.MALAYSIA)


def derive_dataset(source, rows, output):
    """Repeat fitting aggregates into labelled synthetic val/cal rows; no unseen data."""
    fits = [deepcopy(r) for r in rows if r['partition'] == 'fit']
    derived = deepcopy(source)
    derived['dataset_kind'] = 'synthetic_rehearsal_from_fitting'
    derived['rows'] = fits
    for role in development.method.ROLES:
        own = sorted((r for r in fits if r['persona'] == role), key=lambda r: r['date_local'])
        for part, dates in [('validation', ['2026-11-08', '2026-11-09']),
                            ('normal_calibration', ['2026-11-10', '2026-11-11', '2026-11-12'])]:
            for original, day in zip(own[-len(dates):], dates):
                row = deepcopy(original)
                row.update({'partition': part, 'date_local': day,
                            'rehearsal_origin_date': original['date_local'], 'synthetic_relabelled_copy': True})
                weekday = datetime.fromisoformat(day).weekday()
                row['features']['off_hours_events'] = sum(n for hour, n in row['local_hour_counts'].items()
                                                         if weekday >= 5 or not 8 <= int(hour) < 20)
                row['evidence_sha256'] = reserved.digest(['REHEARSAL_ONLY', original['evidence_sha256'], day])
                derived['rows'].append(row)
    derived['readiness'] = {'days': [{'day': r['date_local'], 'persona': r['persona'], 'partition': r['partition'],
                                      'status': 'usable', **r['coverage']} for r in derived['rows']]}
    derived['provenance']['scope_sha256'] = reserved.digest([DUMMY_ACCOUNT, STACK])
    derived['provenance']['rehearsal_only'] = True
    derived['provenance']['derivation'] = 'Fitting copies; artificial validation/calibration dates. Not independent evidence.'
    output.mkdir()
    raw = exporter.canonical(derived) + b'\n'
    (output / 'dataset.json').write_bytes(raw)
    (output / 'feature_contract.json').write_bytes(exporter.canonical(exporter.CONTRACT))
    (output / 'manifest.json').write_bytes(exporter.canonical({
        'study': reserved.protocol.binding(), 'study_sha256': reserved.protocol.binding_sha256(),
        'dataset_sha256': trainer.sha(output / 'dataset.json'), 'feature_contract_sha256': trainer.CONTRACT_SHA,
        'source_sha256': exporter.hashes(), 'synthetic_rehearsal_only': True}))


def synthetic_receipts(output):
    """Dummy-account fixture evidence, never sent to any cloud or live ingest API."""
    state = output / 'synthetic-case-ledger'
    state.mkdir()
    ledger, events = state / 'ledger.db', output / 'synthetic-case-events.db'
    with history.ledger(ledger) as db, sqlite3.connect(events) as native:
        db.execute('INSERT INTO scope VALUES(1,?)', (json.dumps([DUMMY_ACCOUNT, STACK, reserved.PROFILE_SHA]),))
        native.execute('''CREATE TABLE events (event_id,source,source_account_id,timestamp,action,
            resource,ip_address,metadata,ingested_at)''')
        i = 0
        for day in reserved.CASES:
            for row in reserved.plan_for_date(DUMMY_ACCOUNT, STACK, day)['actions']:
                planned = datetime.fromisoformat(row['planned_utc'])
                native_id, request, principal = (f'REHEARSAL-{kind}-{i}' for kind in ('native', 'request', 'principal'))
                metadata = {'requestID': request, 'userIdentity': {'principalId': principal, 'type': 'AssumedRole',
                    'arn': f'arn:aws:sts::{DUMMY_ACCOUNT}:assumed-role/{STACK}-{row["persona"]}/argus-{row["persona"]}'}}
                db.execute('''INSERT INTO actions(action_id,day,persona,plan,status,attempted_at,request_id,
                    principal_id,completed_at,native_event_id) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                    (row['action_id'], day, row['persona'], json.dumps(row), 'provider_verified',
                     (planned + timedelta(seconds=1)).isoformat(), request, principal,
                     (planned + timedelta(seconds=2)).isoformat(), native_id))
                native.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',
                    (native_id, 'aws_cloudtrail', DUMMY_ACCOUNT, (planned + timedelta(seconds=30)).isoformat(),
                     row['operation'], row['bucket'], '192.0.2.1', json.dumps(metadata),
                     (planned + timedelta(seconds=35)).isoformat()))
                i += 1
        db.commit()
    return ledger, events


def rehearse(directory, output, now=None):
    now = now or datetime.now(timezone.utc)
    data, manifest, rows, excluded = development.read_development(directory, now)
    fits = [r for r in rows if r['partition'] == 'fit']
    if not development.fitting_ready(fits):
        raise ValueError('Real fitting history insufficient; no rehearsal result yet')
    output = Path(output).resolve()
    active_models = (ROOT / 'ml/models').resolve()
    if (output.exists() or output == active_models or active_models in output.parents
            or Path(directory).resolve() in output.parents):
        raise ValueError('Fresh private rehearsal output required')
    output.mkdir(parents=True)
    derived, bundle = output / 'derived-synthetic-data', output / 'synthetic-bundle'
    derive_dataset(data, fits, derived)
    trainer.train(derived, bundle, SIMULATED_FREEZE, synthetic=True)
    report = {'schema': 'argus_engineering_rehearsal_v1', 'rehearsal_only': True, 'activated': False,
              'computed_at_utc': now.isoformat(), 'real_source_dataset_sha256': manifest['dataset_sha256'],
              'fitting_rows_copied': len(fits), 'excluded': excluded,
              'ignored_validation_rows': sum(r['partition'] == 'validation' for r in rows),
              'limitations': ['Repeated fitting rows are NOT independent validation/calibration.',
                              'Dummy-account case receipts and release clock are synthetic.',
                              'No detection-performance conclusion, production release or guard change.']}
    references = json.loads((bundle / 'references.json').read_text())
    normal_report = json.loads((bundle / 'normal_report.json').read_text())
    recomputed = development.method.calibrate(normal_report['normal_calibration'], references)
    if recomputed != normal_report['calibration']:
        raise ValueError('Rehearsal calibration reload mismatch; engineering failure, not a method no-go')
    if recomputed['primary_gate'] != 'normal_calibration_only':
        report['status'] = 'rehearsal_normal_gate_no_go'
    else:
        reserved.check_calibration(bundle, references)
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return SIMULATED_FREEZE
        original_loader = trainer.load_bundle
        def synthetic_loader(path, **kwargs):
            if Path(path).resolve() != bundle.resolve():
                raise ValueError('Rehearsal loader restricted to its own dummy-scope bundle')
            return original_loader(path, **{**kwargs, 'allow_synthetic': True})
        release = output / 'SIMULATED-release.json'
        # Injection is scoped to this harness process and one synthetic bundle;
        # no source files or production guards are edited.
        with patch.object(reserved, 'datetime', Clock), patch.object(trainer, 'load_bundle', synthetic_loader):
            reserved.freeze(bundle, release, DUMMY_ACCOUNT, STACK)
        ledger, events = synthetic_receipts(output)
        case_report = evaluator.evaluate(release, ledger, events, DUMMY_ACCOUNT, STACK,
                                         reserved.EVALUATE_FROM + timedelta(minutes=1), allow_synthetic=True)
        (output / 'SYNTHETIC-case-report.json').write_bytes(exporter.canonical(case_report))
        report['status'] = 'engineering_replay_completed'
    try:
        trainer.load_bundle(bundle, expected_scope_sha256=reserved.digest([DUMMY_ACCOUNT, STACK]))
    except trainer.Refusal:
        report['default_production_loader_rejected_bundle'] = True
    else:
        raise ValueError('Synthetic bundle unexpectedly accepted by production loader')
    if trainer.sha(Path(directory) / 'dataset.json') != manifest['dataset_sha256']:
        raise ValueError('Source data changed during rehearsal')
    report['harness_sha256'] = trainer.sha(__file__)
    (output / 'REHEARSAL-ONLY.json').write_bytes(exporter.canonical(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(rehearse(args.data, args.out)))
        return 0
    except Exception:
        print('Engineering rehearsal refused or incomplete. No qualifying release was created; inspect private artifacts.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
