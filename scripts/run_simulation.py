"""Plan first; --execute runs only bounded read-only actions on synthetic fixtures.

This is a scripted actor harness, not an unrestricted LLM agent. No native cloud
event is fabricated, no provider time is rewritten, and no detector is trained.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.simulation_lab import FIXTURE, FIXTURE_KEY, PERSONAS, REGION, buckets, role_arn, validate_scope

METHODS = {'GetObject': 'get_object', 'HeadObject': 'head_object', 'GetBucketLocation': 'get_bucket_location'}


def make_plan(account, stack, seed=42, phase='baseline', max_requests=48):
    validate_scope(account, stack)
    if phase not in ('baseline', 'holdout', 'transition') or not 1 <= max_requests <= 64:
        raise ValueError('Invalid phase or request budget')
    targets = buckets(account, stack)
    randomizer = random.Random(seed)
    actions = []
    for index, persona in enumerate(PERSONAS):
        own = targets[index]
        operations = [('HeadObject', own), ('GetObject', own)]
        if index == 2:  # A legitimate archive reader, not an attack-only resource token.
            operations.append(('GetObject', targets[-1]))
        if index == 4:  # Benign high-volume control; volume alone should not decide.
            operations.extend([('GetObject', own)] * (14 if phase == 'holdout' else 5))
        if phase == 'transition' and index == 5:
            operations = [(action, target) for target in targets
                          for action in ('GetBucketLocation', 'HeadObject', 'GetObject')]
        elif randomizer.choice([False, True]):
            operations.append(('GetObject', own))
        for operation, target in operations:
            actions.append({'persona': persona, 'operation': operation, 'bucket': target, 'key': FIXTURE_KEY})
    # One bootstrap STS identity check, two audit reads, and one AssumeRole per role.
    request_total = len(actions) + 3 + len(PERSONAS)
    if request_total > max_requests:
        raise ValueError('Plan exceeds request budget; increase explicitly up to 64 or choose another seed')
    return {'schema_version': 1, 'mode': 'dry_run', 'account_id': account, 'stack': stack,
            'region': REGION, 'seed': seed, 'phase': phase, 'max_requests': max_requests,
            'planned_requests': request_total, 'personas': list(PERSONAS), 'actions': actions}


def audit_coverage(selectors, expected_buckets):
    expected = {f'arn:aws:s3:::{bucket}/' for bucket in expected_buckets}
    observed = set()
    for selector in selectors.get('EventSelectors', []):
        if selector.get('ReadWriteType') not in ('ReadOnly', 'All'):
            continue
        for resource in selector.get('DataResources', []):
            if resource.get('Type') == 'AWS::S3::Object':
                observed.update(resource.get('Values', []))
    return observed == expected  # Refuse accidentally account-wide S3 data logging.


def check_baseline(path, audit_path, plan):
    raw = Path(path).read_bytes()
    manifest, audit = json.loads(raw), json.loads(Path(audit_path).read_text())
    if (manifest.get('schema_version') != 1 or manifest.get('mode') != 'executed'
            or manifest.get('status') != 'completed' or manifest.get('phase') != 'baseline'
            or any(manifest.get(k) != plan[k] for k in ('account_id', 'stack', 'region'))
            or set(manifest.get('principals', {})) != set(PERSONAS)
            or not manifest.get('results') or any(r.get('status') != 'ok' for r in manifest['results'])
            or audit.get('manifest_sha256') != hashlib.sha256(raw).hexdigest()
            or audit.get('status') != 'complete' or audit.get('matched_actions') != len(manifest['results'])):
        raise ValueError('Require a matching completed baseline and provider-log audit')
    expected = make_plan(manifest['account_id'], manifest['stack'], manifest['seed'],
                         'baseline', manifest['max_requests'])
    performed = [{key: row.get(key) for key in ('persona', 'operation', 'bucket', 'key')}
                 for row in manifest['results']]
    if (manifest.get('actions') != expected['actions'] or performed != expected['actions']
            or len(set(manifest['principals'].values())) != len(PERSONAS)
            or any(not row.get('request_id') for row in manifest['results'])):
        raise ValueError('Baseline does not cover the fixed six-persona normal plan')


def check_frozen_model(path):
    from backend.cloud_feature_extractor import CLOUD_FEATURES, CLOUD_INPUT_DIM
    model = json.loads(Path(path).read_text())
    if (model.get('frozen') is not True or model.get('normal_calibration_only') is not True
            or model.get('input_dim') != CLOUD_INPUT_DIM or model.get('features') != CLOUD_FEATURES
            or not isinstance(model.get('training_data_sha256'), str)
            or not re.fullmatch(r'[a-f0-9]{64}', model['training_data_sha256'])):
        raise ValueError('Frozen normal-only model provenance is incomplete')
    model_root = (ROOT / 'ml/models').resolve()
    for filename, digest in [('model_path', 'model_sha256'), ('scaler_path', 'scaler_sha256')]:
        artifact = (model_root / model.get(filename, '')).resolve()
        if not artifact.is_relative_to(model_root) or not artifact.is_file():
            raise ValueError('Frozen artifact must be inside the local model directory')
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != model.get(digest):
            raise ValueError('Frozen model/scaler digest mismatch')


def execute(plan, profile, trail_name, baseline=None, baseline_audit=None, frozen_model=None, progress=None):
    import boto3
    from botocore.config import Config
    # Rebuild the allow-list; never execute arbitrary methods/targets from a file.
    expected = make_plan(plan['account_id'], plan['stack'], plan['seed'], plan['phase'], plan['max_requests'])
    if plan != expected:
        raise ValueError('Execution plan differs from the bounded generated plan')
    if not trail_name.startswith('argus-'):
        raise ValueError('Only a named Argus trail is allowed')
    if plan['phase'] != 'baseline':
        if not baseline or not baseline_audit:
            raise ValueError('A verified baseline is required before held-out activity')
        check_baseline(baseline, baseline_audit, plan)
        # A new training pipeline must emit this manifest; the old benchmark is not silently adopted.
        if not frozen_model:
            raise ValueError('Freeze a trained/calibrated cloud model before held-out execution')
        check_frozen_model(frozen_model)
    config = Config(retries={'total_max_attempts': 1, 'mode': 'standard'}, connect_timeout=5, read_timeout=10)
    session = boto3.Session(profile_name=profile, region_name=REGION)
    sts = session.client('sts', config=config)
    caller = sts.get_caller_identity()
    account, stack = plan['account_id'], plan['stack']
    expected_user = f'arn:aws:iam::{account}:user/argus-lab/{stack}-runner'
    if caller.get('Account') != account or caller.get('Arn') != expected_user:
        raise ValueError('Require the separate, non-root lab runner identity in the expected account')
    trail = session.client('cloudtrail', config=config)
    if not trail.get_trail_status(Name=trail_name).get('IsLogging'):
        raise ValueError('Audit trail is not logging')
    if not audit_coverage(trail.get_event_selectors(TrailName=trail_name), buckets(account, stack)):
        raise ValueError('Scoped read data-event coverage is missing or too broad; no persona actions executed')
    result = {**plan, 'mode': 'executed', 'status': 'running', 'run_id': uuid4().hex,
              'started_at': datetime.now(timezone.utc).isoformat(), 'principals': {}, 'results': []}
    emit = progress or (lambda *_: None)
    emit(result)
    for persona in PERSONAS:
        assumed = sts.assume_role(RoleArn=role_arn(account, stack, persona),
                                  RoleSessionName='argus-' + persona, DurationSeconds=900)
        expected_prefix = f'arn:aws:sts::{account}:assumed-role/{stack}-{persona}/argus-{persona}'
        identity = assumed['AssumedRoleUser']
        if identity['Arn'] != expected_prefix:
            raise ValueError('Unexpected assumed-role identity')
        result['principals'][persona] = identity['AssumedRoleId']
        emit(result)
        credentials = assumed['Credentials']
        s3 = boto3.client('s3', region_name=REGION, config=config,
                          aws_access_key_id=credentials['AccessKeyId'],
                          aws_secret_access_key=credentials['SecretAccessKey'],
                          aws_session_token=credentials['SessionToken'])
        try:
            for action in [a for a in plan['actions'] if a['persona'] == persona]:
                kwargs = {'Bucket': action['bucket']}
                if action['operation'] != 'GetBucketLocation':
                    kwargs['Key'] = FIXTURE_KEY
                entry = {**action, 'status': 'attempting', 'request_id': None}
                result['results'].append(entry)
                emit(result)
                response = getattr(s3, METHODS[action['operation']])(**kwargs)
                entry['request_id'] = response.get('ResponseMetadata', {}).get('RequestId')
                entry['status'] = 'returned'
                emit(result)
                body = response.get('Body')
                try:
                    if action['operation'] != 'GetBucketLocation':
                        if (response.get('Metadata', {}).get('argus-lab') != stack
                                or response.get('ContentLength', 4097) > 4096):
                            raise ValueError('Resource is not the expected small synthetic fixture')
                        if body is not None and body.read(4097) != FIXTURE:
                            raise ValueError('Fixture content mismatch')
                    if not response.get('ResponseMetadata', {}).get('RequestId'):
                        raise ValueError('Provider request ID missing')
                    entry['status'] = 'ok'
                    emit(result)
                finally:
                    if body is not None:
                        body.close()
        finally:
            s3.close()
    result['status'] = 'completed'
    result['completed_at'] = datetime.now(timezone.utc).isoformat()
    emit(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-id', required=True)
    parser.add_argument('--stack', default='argus-ueba-actors')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--phase', choices=['baseline', 'holdout', 'transition'], default='baseline')
    parser.add_argument('--max-requests', type=int, default=48)
    parser.add_argument('--profile', default='argus-simulator')
    parser.add_argument('--trail', default='argus-ueba-live-trail')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--baseline-manifest')
    parser.add_argument('--baseline-audit')
    parser.add_argument('--frozen-model-manifest')
    args = parser.parse_args()
    path = None
    try:
        plan = make_plan(args.account_id, args.stack, args.seed, args.phase, args.max_requests)
        if not args.execute:
            print(json.dumps(plan, indent=2))
            return 0
        run_id = uuid4().hex
        directory = ROOT / 'data/live/experiments' / run_id
        directory.mkdir(parents=True, exist_ok=False)
        path = directory / 'manifest.json'
        def save(value):
            value['run_id'] = run_id
            temporary = directory / 'manifest.tmp'
            temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
            temporary.replace(path)
        save({**plan, 'mode': 'execution_requested', 'status': 'preflight', 'results': []})
        result = execute(plan, args.profile, args.trail, args.baseline_manifest,
                         args.baseline_audit, args.frozen_model_manifest, progress=save)
        print(json.dumps({'status': result['status'], 'personas': len(result['principals']),
                          'actions': len(result['results']), 'manifest': str(path),
                          'audit_logs': 'pending provider delivery; collect and verify separately'}))
        return 0
    except Exception:
        if path is not None and path.is_file():
            saved = json.loads(path.read_text())
            saved['status'] = 'failed'
            saved['stopped_at'] = datetime.now(timezone.utc).isoformat()
            path.write_text(json.dumps(saved, indent=2), encoding='utf-8')
        print('Simulation stopped. Check dry-run plan, lab identity, audit coverage and prerequisite manifests. No credentials or provider response bodies displayed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
