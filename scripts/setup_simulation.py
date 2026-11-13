"""Review the fixed lab plan by default; --deploy uses temporary setup credentials.

No root access keys. The optional runner key is for the narrowly scoped lab IAM
user only, saved directly to a new named AWS profile, never printed or passed as
a process argument. Existing collector/default profiles are not overwritten.
"""
from __future__ import annotations

import argparse
import configparser
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.setup_aws import aws
from scripts.simulation_lab import FIXTURE, FIXTURE_KEY, PERSONAS, REGION, buckets, build_template, role_arn, validate_scope

TEMPLATE = ROOT / 'infra/aws-simulation.json'
LIVE_TEMPLATE = ROOT / 'infra/aws-live.json'


def plan(account, stack, live_stack):
    validate_scope(account, stack)
    validate_scope(account, live_stack)
    if stack == live_stack:
        raise ValueError('Actor and collection stacks must be separate')
    return {'account': account, 'region': REGION, 'lab_stack': stack, 'live_stack': live_stack,
            'runner_user': stack + '-runner', 'machine_roles': [role_arn(account, stack, p) for p in PERSONAS],
            'synthetic_buckets': buckets(account, stack), 'fixture_key': FIXTURE_KEY,
            'role_actions': ['s3:GetObject (exact fixture keys)', 's3:GetBucketLocation (toy buckets only)'],
            'changes': ['six lab roles and a separate bootstrap user', 'seven private retained synthetic buckets',
                        'S3 read data events on those buckets only; existing management logging retained'],
            'automatic_execution': False, 'new_model_training': False}


def deploy(profile, template, stack, parameters):
    subprocess.run(['aws', 'cloudformation', 'deploy', '--profile', profile, '--region', REGION,
                    '--template-file', str(template), '--stack-name', stack,
                    '--capabilities', 'CAPABILITY_NAMED_IAM', '--parameter-overrides', *parameters,
                    '--tags', 'Project=Argus', '--no-fail-on-empty-changeset', '--no-cli-pager'],
                   check=True, timeout=900)


def assert_owned_stack(profile, stack, expected_resources, expected_logicals=None):
    result = aws(profile, REGION, 'cloudformation', 'describe-stacks', '--stack-name', stack)['Stacks'][0]
    if (result['StackStatus'] not in ('CREATE_COMPLETE', 'UPDATE_COMPLETE')
            or not any(t == {'Key': 'Project', 'Value': 'Argus'} for t in result.get('Tags', []))):
        raise ValueError('Stack ownership or complete state is unverified')
    resources = aws(profile, REGION, 'cloudformation', 'list-stack-resources', '--stack-name', stack)['StackResourceSummaries']
    if expected_logicals is not None and {r['LogicalResourceId'] for r in resources} != set(expected_logicals):
        raise ValueError('Refusing to replace a stack with additional/unrecognized resources')
    for logical, physical in expected_resources.items():
        if not any(r['LogicalResourceId'] == logical and r.get('PhysicalResourceId') == physical for r in resources):
            raise ValueError('Stack resources differ from the fixed lab plan')
    return result


def configure_runner(profile, account, stack, destination_profile='argus-simulator'):
    # Refuse an existing profile rather than silently replace or rotate credentials.
    folder = Path.home() / '.aws'
    credential_path, config_path = folder / 'credentials', folder / 'config'
    credentials, configuration = configparser.RawConfigParser(), configparser.RawConfigParser()
    credentials.read(credential_path)
    configuration.read(config_path)
    user = stack + '-runner'
    expected_arn = f'arn:aws:iam::{account}:user/argus-lab/{user}'
    if credentials.has_section(destination_profile) or configuration.has_section('profile ' + destination_profile):
        caller = aws(destination_profile, REGION, 'sts', 'get-caller-identity')
        if caller.get('Account') != account or caller.get('Arn') != expected_arn:
            raise ValueError('Runner profile already exists for a different/unverified identity')
        return destination_profile
    actual = aws(profile, REGION, 'iam', 'get-user', '--user-name', user)['User']
    if actual['Arn'] != expected_arn:
        raise ValueError('Runner user identity mismatch')
    existing = aws(profile, REGION, 'iam', 'list-access-keys', '--user-name', user)['AccessKeyMetadata']
    if existing:
        raise ValueError('Runner already has keys; do not create an extra credential automatically')
    key = aws(profile, REGION, 'iam', 'create-access-key', '--user-name', user)['AccessKey']
    try:
        credentials[destination_profile] = {'aws_access_key_id': key['AccessKeyId'],
                                             'aws_secret_access_key': key['SecretAccessKey']}
        configuration['profile ' + destination_profile] = {'region': REGION}
        folder.mkdir(exist_ok=True)
        for target, parser in [(credential_path, credentials), (config_path, configuration)]:
            # Atomic replacements stay in the verified standard AWS directory.
            if target.resolve().parent != folder.resolve():
                raise ValueError('Refusing a redirected AWS configuration target')
            descriptor, temporary = tempfile.mkstemp(prefix='argus-', dir=folder)
            try:
                with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                    parser.write(handle)
                os.replace(temporary, target)
            finally:
                if os.path.isfile(temporary):
                    os.unlink(temporary)
    except Exception:
        # Revoke only the just-created credential if local persistence failed.
        aws(profile, REGION, 'iam', 'delete-access-key', '--user-name', user, '--access-key-id', key['AccessKeyId'])
        raise
    finally:
        key.clear()
    return destination_profile


def setup(args):
    report = plan(args.account_id, args.stack, args.live_stack)
    if not args.deploy:
        if args.configure_runner:
            raise ValueError('--configure-runner requires --deploy')
        return report
    identity = aws(args.profile, REGION, 'sts', 'get-caller-identity')
    if identity['Account'] != args.account_id:
        raise ValueError('Setup identity belongs to a different account; no resources changed')
    # Check the existing collection stack before creating or altering lab resources.
    live = assert_owned_stack(args.profile, args.live_stack, {'Trail': args.live_stack + '-trail',
                        'EventQueue': 'https://sqs.us-east-1.amazonaws.com/' + args.account_id + '/' + args.live_stack + '-events'},
                              json.loads(LIVE_TEMPLATE.read_text())['Resources'])
    parameters = {row['ParameterKey']: row['ParameterValue'] for row in live['Parameters']}
    if not parameters.get('CollectorUser'):
        raise ValueError('Existing collector identity is unverified')
    # Never adopt/replace a foreign same-name stack or discard unrelated data coverage.
    existing_stacks = aws(args.profile, REGION, 'cloudformation', 'list-stacks')['StackSummaries']
    expected = {'RunnerUser': args.stack + '-runner',
                **{f'Bucket{i:02d}': bucket for i, bucket in enumerate(report['synthetic_buckets'], 1)},
                **{f'Persona{i:02d}': args.stack + '-' + persona for i, persona in enumerate(PERSONAS, 1)}}
    if any(s['StackName'] == args.stack and s['StackStatus'] != 'DELETE_COMPLETE' for s in existing_stacks):
        assert_owned_stack(args.profile, args.stack, expected, json.loads(TEMPLATE.read_text())['Resources'])
    coverage = aws(args.profile, REGION, 'cloudtrail', 'get-event-selectors', '--trail-name', args.live_stack + '-trail')
    allowed_scopes = {f'arn:aws:s3:::{bucket}/' for bucket in report['synthetic_buckets']}
    if coverage.get('AdvancedEventSelectors') or any(
        resource.get('Type') != 'AWS::S3::Object' or not set(resource.get('Values', [])).issubset(allowed_scopes)
        for selector in coverage.get('EventSelectors', []) for resource in selector.get('DataResources', [])
    ):
        raise ValueError('Refusing to replace existing unrelated data-event coverage')
    for template in (TEMPLATE, LIVE_TEMPLATE):
        aws(args.profile, REGION, 'cloudformation', 'validate-template', '--template-body', 'file://' + str(template))
    descriptor, rendered_path = tempfile.mkstemp(prefix='argus-lab-template-', suffix='.json')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(build_template(args.account_id, args.stack), handle)
        deploy(args.profile, Path(rendered_path), args.stack, ['TrailName=' + args.live_stack + '-trail'])
    finally:
        os.unlink(rendered_path)
    assert_owned_stack(args.profile, args.stack, expected, json.loads(TEMPLATE.read_text())['Resources'])
    # Use a short-lived CLI-exported setup session in memory, never an argument/file.
    session_data = aws(args.profile, REGION, 'configure', 'export-credentials', '--format', 'process')
    import boto3
    iam = boto3.client('iam', region_name=REGION, aws_access_key_id=session_data['AccessKeyId'],
                       aws_secret_access_key=session_data['SecretAccessKey'], aws_session_token=session_data.get('SessionToken'))
    try:
        # Import does not reconcile properties; converge only this lab user's exact policy.
        iam.put_user_policy(UserName=args.stack + '-runner', PolicyName='AssumeOnlyLabRolesAndCheckAudit',
                            PolicyDocument=json.dumps({'Version': '2012-10-17', 'Statement': [
                                {'Effect': 'Allow', 'Action': ['sts:AssumeRole'], 'Resource': report['machine_roles']},
                                {'Effect': 'Allow', 'Action': ['cloudtrail:GetEventSelectors', 'cloudtrail:GetTrailStatus'],
                                 'Resource': f'arn:aws:cloudtrail:{REGION}:{args.account_id}:trail/{args.live_stack}-trail'},
                            ]}))
    finally:
        iam.close()
    s3 = boto3.client('s3', region_name=REGION, aws_access_key_id=session_data['AccessKeyId'],
                      aws_secret_access_key=session_data['SecretAccessKey'], aws_session_token=session_data.get('SessionToken'))
    try:
        for bucket in report['synthetic_buckets']:
            # Also converge retained/imported lab buckets to the declared safeguards.
            s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration=dict.fromkeys(
                ['BlockPublicAcls', 'BlockPublicPolicy', 'IgnorePublicAcls', 'RestrictPublicBuckets'], True))
            s3.put_bucket_ownership_controls(Bucket=bucket, OwnershipControls={'Rules': [{'ObjectOwnership': 'BucketOwnerEnforced'}]})
            s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={
                'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]})
            s3.put_bucket_lifecycle_configuration(Bucket=bucket, LifecycleConfiguration={
                'Rules': [{'ID': 'ExpireSyntheticFixture', 'Status': 'Enabled',
                           'Filter': {'Prefix': ''}, 'Expiration': {'Days': 30}}]})
            try:
                existing = s3.head_object(Bucket=bucket, Key=FIXTURE_KEY)
            except s3.exceptions.ClientError as error:
                if error.response['Error']['Code'] not in ('404', 'NoSuchKey', 'NotFound'):
                    raise
                existing = None
            if existing and (existing.get('Metadata', {}).get('argus-lab') != args.stack
                             or existing.get('ContentLength') != len(FIXTURE)):
                raise ValueError('Refusing to overwrite a non-lab object')
            if not existing:
                s3.put_object(Bucket=bucket, Key=FIXTURE_KEY, Body=FIXTURE, ContentType='text/plain',
                              Metadata={'argus-lab': args.stack, 'classification': 'synthetic'})
    finally:
        s3.close()
        session_data.clear()
    deploy(args.profile, LIVE_TEMPLATE, args.live_stack,
           ['CollectorUser=' + parameters['CollectorUser'], 'EnableSimulationData=true', 'SimulationStack=' + args.stack])
    if args.configure_runner:
        report['runner_profile'] = configure_runner(args.profile, args.account_id, args.stack)
    report['deployed'] = True
    report['baseline_activity_generated'] = False
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-id', required=True)
    parser.add_argument('--stack', default='argus-ueba-actors')
    parser.add_argument('--live-stack', default='argus-ueba-live')
    parser.add_argument('--profile', default='argus-setup')
    parser.add_argument('--deploy', action='store_true')
    parser.add_argument('--configure-runner', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(setup(args), indent=2))
        return 0
    except Exception:
        print('Lab setup stopped. Check account, temporary setup login, stack ownership and local profile state. No credential or raw API response displayed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
