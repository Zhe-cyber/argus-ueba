"""Inspect/validate by default; --deploy provisions Argus through AWS CLI.

No credentials are created, exported or printed. Use a temporary setup profile.
An existing non-root IAM user receives access only to the collection queue.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'infra' / 'aws-live.json'


def aws(profile: str, region: str, *args: str) -> dict:
    result = subprocess.run(
        ['aws', *args, '--profile', profile, '--region', region,
         '--output', 'json', '--no-cli-pager'],
        capture_output=True, text=True, timeout=60, check=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else {}


def setup(args) -> dict:
    if args.region != 'us-east-1':
        raise ValueError('This initial global-service demo is restricted to us-east-1')
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,23}', args.stack):
        raise ValueError('Stack name must be lowercase, start with a letter, and be at most 24 characters')
    if not re.fullmatch(r'\d{12}', args.account_id):
        raise ValueError('Provide the expected 12-digit AWS account ID')
    identity = aws(args.profile, args.region, 'sts', 'get-caller-identity')
    if identity['Account'] != args.account_id:
        raise ValueError('AWS session account does not match --account-id; no resources changed')
    aws(args.profile, args.region, 'iam', 'get-user', '--user-name', args.collector_user)
    validation = aws(args.profile, args.region, 'cloudformation', 'validate-template',
                     '--template-body', 'file://' + str(TEMPLATE))
    report = {'account': identity['Account'], 'region': args.region, 'stack': args.stack,
              'collector_user': args.collector_user, 'template_validated': True,
              'deployed': False, 'capabilities': validation.get('Capabilities', [])}
    if not args.deploy:
        return report
    # Deploy waits for stack completion and treats an unchanged stack as success.
    subprocess.run(
        ['aws', 'cloudformation', 'deploy', '--profile', args.profile, '--region', args.region,
         '--template-file', str(TEMPLATE), '--stack-name', args.stack,
         '--parameter-overrides', f'CollectorUser={args.collector_user}',
         '--capabilities', 'CAPABILITY_NAMED_IAM', '--tags', 'Project=Argus',
         '--no-fail-on-empty-changeset', '--no-cli-pager'],
        check=True, timeout=900,
    )
    stack = aws(args.profile, args.region, 'cloudformation', 'describe-stacks',
                '--stack-name', args.stack)['Stacks'][0]
    report.update(deployed=True, status=stack['StackStatus'],
                  outputs={row['OutputKey']: row['OutputValue'] for row in stack.get('Outputs', [])})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='argus-setup')
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--account-id', required=True)
    parser.add_argument('--stack', default='argus-ueba-live')
    parser.add_argument('--collector-user', default='argus-readonly')
    parser.add_argument('--deploy', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(setup(args), indent=2))
    except (ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'Setup failed: {exc}\n')


if __name__ == '__main__':
    main()
