"""One-time29Oct warm-up read-only commissioning. Never baseline/model data."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_persona_history as history
from scripts.simulation_lab import PERSONAS, FIXTURE, FIXTURE_KEY, REGION, buckets, role_arn
from scripts.persona_history_plan import MALAYSIA
from scripts.run_simulation import audit_coverage, METHODS

PURPOSE = 'commissioning_exclude_from_baseline'


def make_plan(account, stack, instant=None):
    now = history.utc_now()
    instant = instant or now
    if (instant.tzinfo is None or not timedelta(0) <= now - instant <= history.GRACE
            or now.astimezone(MALAYSIA).date().isoformat() != '2026-10-29'
            or instant.astimezone(MALAYSIA).date().isoformat() != '2026-10-29'):
        raise ValueError('Commissioning allowed only during29Oct warm-up with a fresh timestamp')
    base = history.plan_today(account, stack)
    rows = []
    for role, bucket in zip(PERSONAS, buckets(account, stack)):
        for ordinal, op in enumerate(('GetObject', 'HeadObject', 'GetBucketLocation')):
            identity = f"{base['profile_sha256']}|commission-six-v1|{account}|{stack}|{role}|{op}"
            rows.append({'persona': role, 'ordinal': ordinal, 'planned_local': instant.astimezone(MALAYSIA).isoformat(),
                         'planned_utc': instant.astimezone(timezone.utc).isoformat(), 'operation': op,
                         'symbolic_bucket': f'p{PERSONAS.index(role)+1:02d}', 'bucket': bucket, 'key': FIXTURE_KEY,
                         'status': 'planned_not_executed', 'purpose': PURPOSE,
                         'action_id': hashlib.sha256(identity.encode()).hexdigest()})
    return {**base, 'purpose': PURPOSE, 'created_at_utc': instant.isoformat(), 'actions': rows,
            'planned_actions': 18, 'planned_idle': [], 'commissioning_version': 'six_roles_v1'}


def execute(plan, state_dir):
    expected = make_plan(plan['account_id'], plan['stack'], datetime.fromisoformat(plan['created_at_utc']))
    if plan != expected:
        raise ValueError('Commissioning plan differs; no calls')
    with history.ledger(Path(state_dir) / 'ledger.db') as db:
        due, reserved = history.claim(db, expected)
        if not due:
            return {'status': 'already_claimed_no_retry', 'new_actions': 0, 'purpose': PURPOSE}
        if len(due) != 18 or reserved != 27:
            raise ValueError('Partial commissioning claim; inspect ledger before recovery')
        import boto3
        from botocore.config import Config
        config = Config(retries={'total_max_attempts': 1, 'mode': 'standard'},
                        s3={'addressing_style': 'virtual'}, connect_timeout=5, read_timeout=30)
        session = boto3.Session(profile_name='argus-simulator', region_name=REGION)
        used = sends = 0

        def before_send(**kwargs):
            nonlocal sends
            if sends >= reserved: raise ValueError('HTTP budget exhausted before send')
            sends += 1

        def client(service, **kwargs):
            c = session.client(service, config=config, **kwargs)
            c.meta.events.register('before-send.*.*', before_send)
            return c

        def call(fn, **kwargs):
            nonlocal used
            if used >= reserved: raise ValueError('SDK budget exhausted')
            used += 1
            return fn(**kwargs)

        account, stack = plan['account_id'], plan['stack']
        with closing(client('sts')) as sts, closing(client('cloudtrail')) as trail:
            identity = call(sts.get_caller_identity)
            if identity.get('Account') != account or identity.get('Arn') != f'arn:aws:iam::{account}:user/argus-lab/{stack}-runner':
                raise ValueError('Restricted lab runner required')
            if not call(trail.get_trail_status, Name='argus-ueba-live-trail').get('IsLogging'):
                raise ValueError('Trail not logging')
            if not audit_coverage(call(trail.get_event_selectors, TrailName='argus-ueba-live-trail'), buckets(account, stack)):
                raise ValueError('Missing scoped native evidence coverage')
            for role in PERSONAS:
                assumed = call(sts.assume_role, RoleArn=role_arn(account, stack, role), RoleSessionName='argus-' + role, DurationSeconds=900)
                principal = assumed['AssumedRoleUser']
                if principal['Arn'] != f'arn:aws:sts::{account}:assumed-role/{stack}-{role}/argus-{role}':
                    raise ValueError('Unexpected assumed role')
                cred = assumed['Credentials']
                with closing(client('s3', aws_access_key_id=cred['AccessKeyId'], aws_secret_access_key=cred['SecretAccessKey'],
                                    aws_session_token=cred['SessionToken'])) as s3:
                    for row in [r for r in due if r['persona'] == role]:
                        now = history.utc_now()
                        if now.astimezone(MALAYSIA).date().isoformat() != '2026-10-29' or now - datetime.fromisoformat(plan['created_at_utc']) > history.GRACE:
                            raise ValueError('Commissioning expired; no further actions')
                        db.execute('UPDATE actions SET principal_id=?,attempted_at=? WHERE action_id=?',
                                   (principal['AssumedRoleId'], history.utc_now().isoformat(), row['action_id']))
                        db.commit()
                        kwargs = {'Bucket': row['bucket'], 'ExpectedBucketOwner': account}
                        if row['operation'] != 'GetBucketLocation': kwargs['Key'] = FIXTURE_KEY
                        response = call(getattr(s3, METHODS[row['operation']]), **kwargs)
                        body = response.get('Body')
                        try:
                            if row['operation'] == 'GetObject' and body is None: raise ValueError('Fixture body missing')
                            if row['operation'] == 'GetBucketLocation' and response.get('LocationConstraint') not in (None, REGION):
                                raise ValueError('Unexpected bucket region')
                            if row['operation'] != 'GetBucketLocation':
                                if (response.get('Metadata', {}).get('argus-lab') != stack or response.get('ContentLength', 4097) > 4096
                                        or (body is not None and body.read(4097) != FIXTURE)):
                                    raise ValueError('Unexpected synthetic fixture')
                            request = response.get('ResponseMetadata', {}).get('RequestId')
                            if not request: raise ValueError('Native request receipt missing')
                            db.execute("UPDATE actions SET status='api_ok_audit_pending',request_id=?,completed_at=? WHERE action_id=?",
                                       (request, history.utc_now().isoformat(), row['action_id']))
                            db.commit()
                        finally:
                            if body is not None: body.close()
        return {'status': 'api_calls_completed_audit_pending', 'new_actions': 18, 'reserved_sdk_calls': reserved,
                'sdk_calls_used': used, 'http_sends': sends, 'purpose': PURPOSE, 'roles': 6, 'trained': False, 'activated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot-config', required=True, type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    try:
        from scripts import local_pilot
        cfg = local_pilot.validate(json.loads(args.pilot_config.read_text()))
        plan = make_plan(cfg['account_id'], cfg['stack'])
        if args.execute:
            with local_pilot.lock(Path(cfg['state_dir']) / 'tick.lock'):
                result = execute(plan, cfg['ledger_dir'])
        else:
            result = {'dry_run': True, 'planned_actions': 18, 'reserved_sdk_calls': 27, 'purpose': PURPOSE, 'roles': 6}
        print(json.dumps(result))
        return 0
    except Exception as error:
        print(json.dumps({'status': 'stopped_no_retry', 'error_type': type(error).__name__, 'purpose': PURPOSE}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
