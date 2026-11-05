"""Frozen reserved plans and local release binding; no provider calls on import."""
from copy import deepcopy
from datetime import datetime, date, timezone
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.persona_history_plan import make_plan, MALAYSIA
from scripts.simulation_lab import buckets, validate_scope

PROFILE_SHA = '150529b73fa71ac75eab06b162ad4bc913d7d0a19e3ff52c009d60ef3ba3899c'
from scripts import aws_study_v3 as protocol
CASES = protocol.CASES
TARGETS = ('persona-01', 'persona-02')
CUTOFF = protocol.RECEIPT_CUTOFF
EVALUATE_FROM = protocol.EVALUATE_FROM
SOURCE_FILES = ('scripts/aws_study_v3.py', 'scripts/reserved_study.py', 'scripts/run_reserved_study.py',
                'scripts/evaluate_reserved_study.py', 'scripts/run_persona_history.py',
                'scripts/local_pilot.py', 'scripts/persona_history_plan.py',
                'scripts/persona_profiles_v2.json', 'scripts/run_simulation.py', 'scripts/simulation_lab.py',
                'scripts/aws_lab_daily_features.py', 'scripts/live_history_readiness.py',
                'scripts/export_live_daily.py', 'scripts/train_live_daily.py', 'scripts/live_daily_method.py',
                'docs/LIVE_METHOD_ANNEX_V1.md', 'docs/LIVE_EVALUATION_PROTOCOL_V3.md',
                'specs/W34-aws-study-v3.md')
BUNDLE_FILES = ('manifest.json', 'weights.pt', 'scaler.json', 'references.json', 'normal_report.json')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    return {name: sha(ROOT / name) for name in SOURCE_FILES}


def transform(base):
    """Only resource/purpose annotations change; no extra scheduled action."""
    plan = deepcopy(base)
    day = plan['date_local']
    if day not in CASES or plan['profile_sha256'] != PROFILE_SHA:
        raise ValueError('Reserved date/profile required')
    target_bucket = buckets(plan['account_id'], plan['stack'])[5]
    availability = []
    for role in TARGETS:
        rows = [r for r in plan['actions'] if r['persona'] == role and r['operation'] == 'GetObject']
        if not rows:
            availability.append({'persona': role, 'status': 'unavailable_no_planned_target_read', 'action_id': None})
            continue
        selected = min(rows, key=lambda r: (r['planned_utc'], r['ordinal']))
        if selected['bucket'] == target_bucket:
            raise ValueError('Target resource already ordinary; protocol differs')
        availability.append({'persona': role, 'status': 'available', 'action_id': selected['action_id']})
        selected.update({'bucket': target_bucket, 'symbolic_bucket': 'p06',
                         'purpose': 'reserved_resource_change', 'case_slot': day + '/' + role})
    plan['case_availability'] = availability
    plan['study_protocol'] = protocol.PROTOCOL
    plan['purpose'] = 'reserved_resource_change_day'
    plan['analyst_context'] = CASES[day]
    return plan


def plan_for_date(account, stack, day, created_at=None):
    validate_scope(account, stack)
    raw = (ROOT / 'scripts/persona_profiles_v2.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROFILE_SHA:
        raise ValueError('Frozen profile changed')
    base = make_plan(json.loads(raw), date.fromisoformat(day))
    resources = dict(zip(['p01', 'p02', 'p03', 'p04', 'p05', 'p06', 'confidential'], buckets(account, stack)))
    actions = [{**r, 'action_id': digest_id(PROFILE_SHA, day, r),
                'bucket': resources[r['symbolic_bucket']]} for r in base['actions']]
    return transform({**base, 'profile_sha256': PROFILE_SHA, 'account_id': account, 'stack': stack,
                      'actions': actions, 'created_at_utc': (created_at or datetime.now(timezone.utc)).isoformat(),
                      'purpose': 'controlled_lab_history'})


def case_availability(account, stack):
    return {day: plan_for_date(account, stack, day)['case_availability'] for day in CASES}


def digest_id(profile, day, row):
    return hashlib.sha256(f"{profile}|{day}|{row['persona']}|{row['ordinal']}".encode()).hexdigest()


def check_calibration(bundle, references):
    from scripts import live_daily_method as method
    report = json.loads((Path(bundle) / 'normal_report.json').read_text())
    calibration = method.calibrate(report['normal_calibration'], references)
    if calibration != report['calibration']:
        raise ValueError('Frozen calibration differs on recomputation')
    if calibration['primary_gate'] != 'normal_calibration_only':
        raise ValueError('Primary calibration no-go; no substitute method')
    return calibration


def validate_release(path, account, stack, *, allow_synthetic=False):
    from scripts import train_live_daily as trainer
    value = json.loads(Path(path).read_text())
    protocol.require_binding(value)
    frozen_at = datetime.fromisoformat(value['frozen_at_utc'])
    if frozen_at.tzinfo is None or frozen_at.utcoffset() is None:
        raise ValueError('Zoned freeze timestamp required')
    if (value.get('schema') != protocol.RELEASE_SCHEMA or value.get('scope_sha256') != digest([account, stack])
            or value.get('profile_sha256') != PROFILE_SHA or value.get('cases') != CASES
            or value.get('case_availability') != case_availability(account, stack)
            or value.get('targets') != list(TARGETS) or value.get('source_sha256') != source_hashes()
            or value.get('receipt_cutoff_my') != CUTOFF.isoformat()
            or frozen_at.astimezone(MALAYSIA).date().isoformat() != protocol.FREEZE_DAY):
        raise ValueError('Reserved release scope/source/freeze differs')
    bundle = Path(value['bundle']).resolve()
    if {name: sha(bundle / name) for name in BUNDLE_FILES} != value.get('bundle_sha256'):
        raise ValueError('Frozen bundle changed')
    model, scaler, references, manifest = trainer.load_bundle(bundle, expected_scope_sha256=digest([account, stack]),
                                                             allow_synthetic=allow_synthetic)
    if (manifest['history_gates'].get('eligible_roles') != 6 or not manifest['history_gates'].get('history_gates_pass')
            or manifest['partition_rows'].get('fit', 0) < 30
            or manifest['partition_rows'].get('validation', 0) < 12
            or manifest['partition_rows'].get('normal_calibration', 0) < 12):
        raise ValueError('Frozen history gate failed')
    calibration = check_calibration(bundle, references)
    if calibration != value.get('calibration'):
        raise ValueError('Release thresholds differ')
    return value, model, scaler, references, calibration


def freeze(bundle, output, account, stack):
    """Only actual 13Nov operator release; no CLI clock or synthetic override."""
    now = datetime.now(timezone.utc)
    if now.astimezone(MALAYSIA).date().isoformat() != protocol.FREEZE_DAY:
        raise ValueError('Freeze only on 13 November MY')
    validate_scope(account, stack)
    from scripts import train_live_daily as trainer
    _, _, references, manifest = trainer.load_bundle(bundle, expected_scope_sha256=digest([account, stack]))
    calibration = check_calibration(bundle, references)
    if (not manifest.get('history_gates', {}).get('history_gates_pass')
            or manifest['history_gates'].get('eligible_roles') != 6):
        raise ValueError('All six history gates required')
    status = subprocess.run(['git', '-c', 'core.bare=false', 'status', '--porcelain', '--', *SOURCE_FILES],
                            cwd=ROOT, capture_output=True, text=True, timeout=15, check=True)
    if status.stdout.strip():
        raise ValueError('Commit all frozen source files before release')
    revision = subprocess.run(['git', '-c', 'core.bare=false', 'rev-parse', 'HEAD'], cwd=ROOT,
                              capture_output=True, text=True, timeout=15, check=True).stdout.strip()
    latest_source_commit = subprocess.run(['git', '-c', 'core.bare=false', 'log', '-1', '--format=%ct', '--', *SOURCE_FILES],
                                          cwd=ROOT, capture_output=True, text=True, timeout=15, check=True).stdout.strip()
    if datetime.fromtimestamp(int(latest_source_commit), timezone.utc) >= protocol.SOURCE_COMMIT_BEFORE:
        raise ValueError('Scenario source must be committed before calibration begins')
    output = Path(output)
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Fresh release path with existing private parent required')
    value = {'schema': protocol.RELEASE_SCHEMA, 'frozen_at_utc': now.isoformat(),
             'study': protocol.binding(), 'study_sha256': protocol.binding_sha256(),
             'case_availability': case_availability(account, stack),
             'scope_sha256': digest([account, stack]), 'profile_sha256': PROFILE_SHA,
             'source_sha256': source_hashes(), 'git_revision': revision, 'cases': CASES, 'targets': list(TARGETS),
             'bundle': str(Path(bundle).resolve()), 'bundle_sha256': {name: sha(Path(bundle) / name) for name in BUNDLE_FILES},
             'receipt_cutoff_my': CUTOFF.isoformat(), 'calibration': calibration, 'activated': False}
    if any(manifest['partition_rows'].get(name, 0) < minimum
           for name, minimum in [('fit', 30), ('validation', 12), ('normal_calibration', 12)]):
        raise ValueError('Insufficient frozen partition rows')
    with output.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
    validate_release(output, account, stack)
    return {'frozen': True, 'activated': False, 'release_sha256': sha(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--account-id', required=True)
    parser.add_argument('--stack', default='argus-ueba-actors')
    args = parser.parse_args()
    try:
        print(json.dumps(freeze(args.bundle, args.output, args.account_id, args.stack)))
        return 0
    except Exception:
        print('Reserved release refused; verify date, committed sources, real bundle and gates.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
