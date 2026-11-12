"""Live evaluation scenarios S1-S4 (specs/L7-live-evaluation-rules.md section 2) on the AWS and Cloudflare lab.
OWNER-RUN ONLY.

    python scripts/demo_scenario_live.py --scenario S1|S2|S3|S4            # dry run (default): zero network calls
    python scripts/demo_scenario_live.py --scenario S2 --live --confirm persona-05

Live needs --live, --confirm <the scenario's persona>, a local time at or after 2026-11-14T00:00:00+08:00 and the
scenario's MYT window for the whole run (S1/S2 21:00-22:00, S3/S4 10:00-17:00). At most one run record per persona
per Malaysian day: a second run for the same persona that day is refused (two personas on one day are allowed). Uses only the persona's existing read-only role (S1 also its existing Cloudflare service
token; Cloudflare is S1 only); ListObjectsV2 in S1 is expected to be denied. Hard caps per scenario (S3 calls:
S1 40, S2 5, S3 1, S4 30; STS 2; Cloudflare 8 for S1). Writes a secret-free ledger to
data/live/demo-scenario/run-<scenario>-<utc>.json. A demonstration on lab workloads; see docs/DEMO_SCENARIO.md.
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

MYT = timezone(timedelta(hours=8))
NOT_BEFORE = datetime(2026, 11, 14, tzinfo=MYT)  # was 16 Nov while the V3 study was open; that study is closed
PERSONA, STACK, SESSION_NAME = 'persona-02', 'argus-ueba-actors', 'argus-demo-persona-02'  # S1
RUNNER_SUFFIX = ':user/argus-lab/argus-ueba-actors-runner'
MAX_S3, MAX_STS, MAX_CF = 40, 2, 8  # S1 caps; S2-S4 carry their own S3 cap below
AWS_PAUSE, CF_PAUSE = 2, 5
CF_HOST = re.compile(r'argus-machine-lab\.[a-z0-9-]+\.workers\.dev')
# S1 (number in the L4 table, operation, bucket symbol, count) in execution order: #3, #1, #2, #4
AWS_STEPS = ([(3, 'GetBucketLocation', s, 1) for s in ('confidential', 'p04', 'p05', 'p06')]
             + [(1, 'GetObject', 'confidential', 12)]
             + [(2, 'GetObject', s, 6) for s in ('p04', 'p05', 'p06')]
             + [(4, 'ListObjectsV2', 'confidential', 1)])
AWS_CALLS = [(n, op, sym) for n, op, sym, c in AWS_STEPS for _ in range(c)]
EVENING, OFFICE = (21 * 60, 22 * 60), (10 * 60, 17 * 60)  # MYT minutes; the whole run must fit inside
# L7 section 2, fixed before the first attack. Counts and buckets are the rules' and are never tuned.
SCENARIOS = {
    'S1': {'persona': 'persona-02', 'steps': AWS_STEPS, 'window': EVENING, 'pause': AWS_PAUSE, 'cloudflare': True,
           'expected': 'High'},
    'S2': {'persona': 'persona-05', 'steps': [(1, 'GetObject', 'p05', 3), (1, 'GetObject', 'p04', 2)], 'window': EVENING,
           'pause': 120, 'max_s3': 5, 'cloudflare': False, 'expected': 'Low'},  # L7 v1 before freeze: was Medium
    'S3': {'persona': 'persona-04', 'steps': [(1, 'GetObject', 'confidential', 1)], 'window': OFFICE,
           'pause': AWS_PAUSE, 'max_s3': 1, 'cloudflare': False, 'expected': 'Medium'},
    'S4': {'persona': 'persona-06', 'steps': [(1, 'GetObject', 'p06', 30)], 'window': OFFICE,
           'pause': AWS_PAUSE, 'max_s3': 30, 'cloudflare': False, 'expected': 'Low or Medium'},
}


def calls(plan):
    return [(n, op, sym) for n, op, sym, c in plan['steps'] for _ in range(c)]


def cap(plan):
    return plan.get('max_s3', MAX_S3)


def duration_s(plan, cloudflare):
    return (len(calls(plan)) - 1) * plan['pause'] + ((MAX_CF - 1) * CF_PAUSE if cloudflare else 0)


def in_window(plan, cloudflare, now):
    """True when the whole run (start to planned end) falls inside the scenario's MYT window."""
    local = now.astimezone(MYT)
    start = local.hour * 60 + local.minute + local.second / 60
    return plan['window'][0] <= start and start + duration_s(plan, cloudflare) / 60 < plan['window'][1]


def print_plan(cloudflare, scenario='S1'):
    plan = SCENARIOS[scenario]
    persona = plan['persona']
    lo, hi = (f'{m // 60:02d}:{m % 60:02d}' for m in plan['window'])
    print('DRY RUN: no network calls are made.')
    print(f'Scenario {scenario}: AWS persona {persona}, {len(calls(plan))} S3 calls, {plan["pause"]} s apart'
          + (', order #3 #1 #2 #4:' if scenario == 'S1' else ':'))
    for n, op, sym, c in plan['steps']:
        print(f'  #{n} {op} on {sym} x{c}' + ('  (not permitted: AccessDenied expected)' if op == 'ListObjectsV2' else ''))
    print(f'Caps: S3 <= {cap(plan)}, STS <= {MAX_STS} (identity check + one AssumeRole, session argus-demo-{persona})')
    if plan['cloudflare']:
        print(f'Cloudflare: {"ENABLED" if cloudflare else "off (add --cloudflare)"}: {MAX_CF} GETs /workloads/{persona}/demo-N, {CF_PAUSE} s apart')
    else:
        print('Cloudflare: not used in this scenario')
    print(f'Approx. duration {duration_s(plan, cloudflare and plan["cloudflare"]) / 60:.1f} min; the whole run must fit in '
          f'{lo}-{hi} MYT. Expected tier (stated in advance): {plan["expected"]}.')
    print(f'Live needs --live --confirm {persona} and local time >= {NOT_BEFORE.isoformat()}.')


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


def run_aws(session, ledger, sleep, clock, plan=SCENARIOS['S1']):
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
    persona = plan['persona']
    assumed = sts.assume_role(RoleArn=lab.role_arn(account, STACK, persona), RoleSessionName=f'argus-demo-{persona}',
                              DurationSeconds=900)
    cred = assumed['Credentials']
    s3 = _client(session, 's3', aws_access_key_id=cred['AccessKeyId'], aws_secret_access_key=cred['SecretAccessKey'],
                 aws_session_token=cred['SessionToken'])
    names = dict(zip([f'p{i:02d}' for i in range(1, 7)] + ['confidential'], lab.buckets(account, STACK)))
    assert sts_calls <= MAX_STS
    try:
        for i, (n, op, sym) in enumerate(calls(plan)):
            if s3_calls >= cap(plan):
                ledger['aborted'] = 'S3 call cap reached'
                return False
            if i:
                sleep(plan['pause'])
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


def ran_today(folder, persona, now):
    """True when a run record (any outcome) for `persona` started on the same MYT day as `now`."""
    day = now.astimezone(MYT).date()
    for path in Path(folder).glob('run-*.json'):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
            started = datetime.fromisoformat(record['started_utc'])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if record.get('persona') == persona and started.astimezone(MYT).date() == day:
            return True
    return False


def main(argv=None, clock=lambda: datetime.now(timezone.utc), sleep=time.sleep, session_factory=_default_session,
         cf_loader=_default_cf_loader, http=_default_http, out_dir=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--scenario', choices=sorted(SCENARIOS), default='S1')
    ap.add_argument('--live', action='store_true')
    ap.add_argument('--confirm')
    ap.add_argument('--cloudflare', action='store_true')
    ap.add_argument('--profile', default='argus-simulator')
    ap.add_argument('--cf-state', help='folder holding pilot-config.json and persona-02.dpapi (default: cloudflare_lab_setup.STATE)')
    args = ap.parse_args(argv)
    plan = SCENARIOS[args.scenario]
    if args.cloudflare and not plan['cloudflare']:
        print(f'Refusing: Cloudflare is used by S1 only, not {args.scenario}.', file=sys.stderr)
        return 2
    if not args.live:
        print_plan(args.cloudflare, args.scenario)
        return 0
    if args.confirm != plan['persona']:
        print(f'Refusing: live mode needs --confirm {plan["persona"]}.', file=sys.stderr)
        return 2
    if clock() < NOT_BEFORE:
        print(f'Refusing: too early; live scenarios are allowed from {NOT_BEFORE.isoformat()}. No call was made.',
              file=sys.stderr)
        return 2
    if not in_window(plan, args.cloudflare, clock()):
        lo, hi = (f'{m // 60:02d}:{m % 60:02d}' for m in plan['window'])
        print(f'Refusing: {args.scenario} must run entirely within {lo}-{hi} MYT (about '
              f'{duration_s(plan, args.cloudflare) / 60:.0f} min). No call was made.', file=sys.stderr)
        return 2
    folder = Path(out_dir) if out_dir else ROOT / 'data/live/demo-scenario'
    if ran_today(folder, plan['persona'], clock()):
        print(f'Refusing: a scenario run for {plan["persona"]} already exists for this Malaysian day '
              '(one scenario per account-day). No call was made.', file=sys.stderr)
        return 2
    ledger = {'scenario': args.scenario, 'persona': plan['persona'], 'started_utc': clock().astimezone(timezone.utc).isoformat(),
              'calls': [], 'cloudflare_calls': []}
    ok = False
    try:
        ok = run_aws(session_factory(args.profile), ledger, sleep, clock, plan)
        if ok and args.cloudflare:
            print('Cloudflare part:', run_cloudflare(cf_loader, http, args.cf_state, ledger, sleep, clock))
    except Exception as error:  # unexpected: stop at once, record the type only
        ledger['aborted'] = f'{type(error).__name__}'
    finally:
        ledger['finished_utc'] = clock().astimezone(timezone.utc).isoformat()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'run-{args.scenario}-{clock().astimezone(timezone.utc):%Y%m%dT%H%M%SZ}.json'
        path.write_text(json.dumps(ledger, indent=2), encoding='utf-8')
    print(f'AWS part: {"done" if ok else "ABORTED: " + str(ledger.get("aborted"))}; ledger written to {path}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
