"""L4 REAL demo run: persona-02 "Batch reporter goes rogue" on the AWS and Cloudflare lab. OWNER-RUN ONLY.

Default is a dry run (zero network calls). Live needs --live --confirm persona-02 and a local time at or after
2026-11-16T00:00:00+08:00 (the controlled study is open until then). Uses only persona-02's existing read-only
role and its existing Cloudflare service token; ListObjectsV2 is expected to be denied. Hard caps: 40 S3 calls,
2 STS calls, 8 Cloudflare requests. Writes a secret-free ledger to data/live/demo-scenario/run-<utc>.json.
This is a demonstration outside the controlled study. See docs/DEMO_SCENARIO.md.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import simulation_lab as lab  # import-time safe: constants and pure helpers only

NOT_BEFORE = datetime(2026, 11, 16, tzinfo=timezone(timedelta(hours=8)))
PERSONA, STACK, SESSION_NAME = 'persona-02', 'argus-ueba-actors', 'argus-demo-persona-02'
RUNNER_SUFFIX = ':user/argus-lab/argus-ueba-actors-runner'
MAX_S3, MAX_STS, MAX_CF = 40, 2, 8
AWS_PAUSE, CF_PAUSE = 2, 5
CF_HOST = re.compile(r'argus-machine-lab\.[a-z0-9-]+\.workers\.dev')
# (number in the spec table, operation, bucket symbol, count) in execution order: #3, #1, #2, #4
AWS_STEPS = ([(3, 'GetBucketLocation', s, 1) for s in ('confidential', 'p04', 'p05', 'p06')]
             + [(1, 'GetObject', 'confidential', 12)]
             + [(2, 'GetObject', s, 6) for s in ('p04', 'p05', 'p06')]
             + [(4, 'ListObjectsV2', 'confidential', 1)])
AWS_CALLS = [(n, op, sym) for n, op, sym, c in AWS_STEPS for _ in range(c)]


def print_plan(cloudflare):
    print('DRY RUN: no network calls are made.')
    print(f'AWS persona {PERSONA}, {len(AWS_CALLS)} S3 calls, {AWS_PAUSE} s apart, order #3 #1 #2 #4:')
    for n, op, sym, c in AWS_STEPS:
        print(f'  #{n} {op} on {sym} x{c}' + ('  (not permitted: AccessDenied expected)' if op == 'ListObjectsV2' else ''))
    print(f'Caps: S3 <= {MAX_S3}, STS <= {MAX_STS} (identity check + one AssumeRole, session {SESSION_NAME})')
    print(f'Cloudflare: {"ENABLED" if cloudflare else "off (add --cloudflare)"}: {MAX_CF} GETs /workloads/{PERSONA}/demo-N, {CF_PAUSE} s apart')
    mins = (len(AWS_CALLS) * AWS_PAUSE + (MAX_CF * CF_PAUSE if cloudflare else 0)) / 60
    print(f'Approx. duration {mins:.1f} min. Live needs --live --confirm {PERSONA} and local time >= {NOT_BEFORE.isoformat()}.')


def _default_session(profile):
    import boto3
    return boto3.Session(profile_name=profile, region_name=lab.REGION)


def _client(session, service, **kw):
    from botocore.config import Config
    return session.client(service, config=Config(retries={'total_max_attempts': 1, 'mode': 'standard'}, connect_timeout=5,
                                                  read_timeout=30, s3={'addressing_style': 'virtual'}), **kw)


def _default_cf_loader(state_dir):
    """(host, client_id, client_secret) for persona-02 via the existing DPAPI loader. Never printed or logged."""
    from scripts import cloudflare_lab_setup as setup
    from scripts.github_lab_app import load_secret
    state = Path(state_dir) if state_dir else setup.STATE
    cfg = json.loads((state / 'pilot-config.json').read_bytes())
    token = load_secret(state / f'{PERSONA}.dpapi')
    if token['client_id'] != cfg['tokens'][PERSONA]['client_id']:
        raise ValueError('Credential scope differs')
    return cfg['host'], token['client_id'], token['client_secret']


def _default_http(url, headers):
    import requests
    with requests.Session() as s:
        s.trust_env = False
        r = s.get(url, headers=headers, timeout=25, allow_redirects=False)
    return r.status_code, r.headers.get('CF-Ray', '').split('-')[0].lower()


def run_aws(session, ledger, sleep, clock):
    """Returns True when finished, False when aborted on an unexpected error."""
    from botocore.exceptions import ClientError
    sts_calls = s3_calls = 0
    sts = _client(session, 'sts')
    sts_calls += 1
    identity = sts.get_caller_identity()
    if not identity['Arn'].endswith(RUNNER_SUFFIX):
        ledger['aborted'] = 'caller is not the lab runner'
        return False
    account = identity['Account']  # never printed or written
    sts_calls += 1
    assumed = sts.assume_role(RoleArn=lab.role_arn(account, STACK, PERSONA), RoleSessionName=SESSION_NAME, DurationSeconds=900)
    cred = assumed['Credentials']
    s3 = _client(session, 's3', aws_access_key_id=cred['AccessKeyId'], aws_secret_access_key=cred['SecretAccessKey'],
                 aws_session_token=cred['SessionToken'])
    names = dict(zip([f'p{i:02d}' for i in range(1, 7)] + ['confidential'], lab.buckets(account, STACK)))
    assert sts_calls <= MAX_STS
    try:
        for i, (n, op, sym) in enumerate(AWS_CALLS):
            if s3_calls >= MAX_S3:
                ledger['aborted'] = 'S3 call cap reached'
                return False
            if i:
                sleep(AWS_PAUSE)
            s3_calls += 1
            kwargs = {'Bucket': names[sym], 'ExpectedBucketOwner': account}
            if op == 'GetObject':
                kwargs['Key'] = lab.FIXTURE_KEY
            entry = {'time_utc': clock().astimezone(timezone.utc).isoformat(), 'step': n, 'operation': op, 'bucket': sym}
            ledger['calls'].append(entry)
            try:
                resp = getattr(s3, {'GetBucketLocation': 'get_bucket_location', 'GetObject': 'get_object',
                                    'ListObjectsV2': 'list_objects_v2'}[op])(**kwargs)
                meta = resp.get('ResponseMetadata', {})
                entry.update(status=meta.get('HTTPStatusCode'), request_id=meta.get('RequestId'))
                if op == 'GetObject' and resp.get('Body') is not None:
                    resp['Body'].close()
                if op == 'ListObjectsV2':
                    entry['note'] = 'unexpectedly allowed'
            except ClientError as error:
                meta = error.response.get('ResponseMetadata', {})
                code = error.response.get('Error', {}).get('Code')
                entry.update(status=meta.get('HTTPStatusCode'), error_code=code, request_id=meta.get('RequestId'))
                if op == 'ListObjectsV2':
                    entry['note'] = 'expected denial' if code == 'AccessDenied' else 'recorded, continue'
                    continue
                ledger['aborted'] = f'unexpected error {code} at step #{n}'
                return False
        return True
    finally:
        s3.close()


def run_cloudflare(loader, http, state_dir, ledger, sleep, clock):
    """Returns 'done' or 'stopped'. Never records headers or secrets."""
    try:
        host, client_id, secret = loader(state_dir)
        if not CF_HOST.fullmatch(host):
            raise ValueError('unexpected host')
    except Exception as error:  # credentials unreadable/expired: report the type only
        ledger['cloudflare'] = f'not started: {type(error).__name__}'
        return 'stopped'
    headers = {'CF-Access-Client-Id': client_id, 'CF-Access-Client-Secret': secret}
    for n in range(1, MAX_CF + 1):
        if n > 1:
            sleep(CF_PAUSE)
        entry = {'time_utc': clock().astimezone(timezone.utc).isoformat(), 'operation': 'GET', 'path': f'/workloads/{PERSONA}/demo-{n}'}
        ledger['cloudflare_calls'].append(entry)
        try:
            status, ray = http(f'https://{host}/workloads/{PERSONA}/demo-{n}', headers)
        except Exception as error:
            entry['error'] = type(error).__name__
            ledger['cloudflare'] = 'stopped: request error'
            return 'stopped'
        entry.update(status=status, request_id=ray)
        if status in (401, 403):
            ledger['cloudflare'] = f'stopped: HTTP {status} (token expired or not refreshed)'
            return 'stopped'
    ledger['cloudflare'] = 'done'
    return 'done'


def main(argv=None, clock=lambda: datetime.now(timezone.utc), sleep=time.sleep, session_factory=_default_session,
         cf_loader=_default_cf_loader, http=_default_http, out_dir=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--live', action='store_true')
    ap.add_argument('--confirm')
    ap.add_argument('--cloudflare', action='store_true')
    ap.add_argument('--profile', default='argus-simulator')
    ap.add_argument('--cf-state', help='folder holding pilot-config.json and persona-02.dpapi (default: cloudflare_lab_setup.STATE)')
    args = ap.parse_args(argv)
    if not args.live:
        print_plan(args.cloudflare)
        return 0
    if args.confirm != PERSONA:
        print(f'Refusing: live mode needs --confirm {PERSONA}.', file=sys.stderr)
        return 2
    if clock() < NOT_BEFORE:
        print(f'Refusing: the controlled study is still open; live demo is allowed from {NOT_BEFORE.isoformat()}. No call was made.',
              file=sys.stderr)
        return 2
    ledger = {'scenario': 'L4', 'persona': PERSONA, 'started_utc': clock().astimezone(timezone.utc).isoformat(),
              'calls': [], 'cloudflare_calls': []}
    folder = Path(out_dir) if out_dir else ROOT / 'data/live/demo-scenario'
    ok = False
    try:
        ok = run_aws(session_factory(args.profile), ledger, sleep, clock)
        if ok and args.cloudflare:
            print('Cloudflare part:', run_cloudflare(cf_loader, http, args.cf_state, ledger, sleep, clock))
    except Exception as error:  # unexpected: stop at once, record the type only
        ledger['aborted'] = f'{type(error).__name__}'
    finally:
        ledger['finished_utc'] = clock().astimezone(timezone.utc).isoformat()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'run-{clock().astimezone(timezone.utc):%Y%m%dT%H%M%SZ}.json'
        path.write_text(json.dumps(ledger, indent=2), encoding='utf-8')
    print(f'AWS part: {"done" if ok else "ABORTED: " + str(ledger.get("aborted"))}; ledger written to {path}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
