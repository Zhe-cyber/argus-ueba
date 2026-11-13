"""Re-associate only this task's retained, unkeyed lab resources after rollback.

No bucket, object or IAM user is deleted. --apply removes the failed stack record
only after every resource is DELETE_SKIPPED, then uses CloudFormation auto-import.
Default is inspection. Never repairs the existing live collection stack.
"""
import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.setup_aws import aws
from scripts.simulation_lab import PERSONAS, REGION, buckets, build_template, validate_scope


def recover(account, stack, profile='argus-setup', apply=False):
    validate_scope(account, stack)
    identity = aws(profile, REGION, 'sts', 'get-caller-identity')
    if identity['Account'] != account:
        raise ValueError('Wrong setup account')
    data = aws(profile, REGION, 'configure', 'export-credentials', '--format', 'process')
    import boto3
    session = boto3.Session(region_name=REGION, aws_access_key_id=data['AccessKeyId'],
                            aws_secret_access_key=data['SecretAccessKey'], aws_session_token=data.get('SessionToken'))
    data.clear()
    cfn, s3, iam = (session.client(name) for name in ('cloudformation', 's3', 'iam'))
    old = cfn.describe_stacks(StackName=stack)['Stacks'][0]
    if old['StackStatus'] != 'ROLLBACK_COMPLETE' or {'Key': 'Project', 'Value': 'Argus'} not in old.get('Tags', []):
        raise ValueError('Only a task-owned rolled-back lab can be recovered')
    resources = cfn.list_stack_resources(StackName=old['StackId'])['StackResourceSummaries']
    allowed = {f'Bucket{i:02d}': bucket for i, bucket in enumerate(buckets(account, stack), 1)}
    allowed['RunnerUser'] = stack + '-runner'
    if not resources or any(r['ResourceStatus'] != 'DELETE_SKIPPED' or r['LogicalResourceId'] not in allowed
                            or allowed.get(r['LogicalResourceId']) != r.get('PhysicalResourceId') for r in resources):
        raise ValueError('Unexpected/non-retained resources; refusing stack deletion')
    if not any(r['LogicalResourceId'] == 'RunnerUser' for r in resources):
        raise ValueError('Runner user is not recorded in the failed stack')
    owned = {row['Name'] for row in s3.list_buckets()['Buckets']}
    existing_buckets = []
    for bucket in buckets(account, stack):
        if bucket not in owned:
            try:
                s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=account)
            except Exception as error:
                if getattr(error, 'response', {}).get('ResponseMetadata', {}).get('HTTPStatusCode') != 404:
                    raise ValueError('Missing bucket name is not verified available') from None
            else:
                raise ValueError('Bucket name is already in use outside the verified ownership list')
            continue
        if not any(r.get('PhysicalResourceId') == bucket for r in resources):
            raise ValueError('Existing bucket is not recorded in the failed stack')
        tags = s3.get_bucket_tagging(Bucket=bucket)['TagSet']
        if not all(item in tags for item in [{'Key': 'Project', 'Value': 'Argus'}, {'Key': 'Purpose', 'Value': 'SyntheticLab'}]):
            raise ValueError('Retained bucket ownership tags differ')
        existing_buckets.append(bucket)
    user = iam.get_user(UserName=stack + '-runner')['User']
    if (user['Arn'] != f'arn:aws:iam::{account}:user/argus-lab/{stack}-runner'
            or {'Key': 'Project', 'Value': 'Argus'} not in user.get('Tags', [])
            or {'Key': 'Purpose', 'Value': 'SyntheticLab'} not in user.get('Tags', [])
            or iam.list_access_keys(UserName=stack + '-runner')['AccessKeyMetadata']):
        raise ValueError('Runner is not the original unkeyed lab user')
    if any(role['RoleName'] == stack + '-' + p for role in iam.list_roles(PathPrefix='/argus-lab/')['Roles'] for p in PERSONAS):
        raise ValueError('Unexpected existing actor role; refusing automatic adoption')
    report = {'retained_buckets': len(existing_buckets), 'unkeyed_runner': True,
              'resource_deletions': 0, 'applied': False}
    if not apply:
        return report
    print(json.dumps({'recovery_stage': 'remove_failed_stack_record', 'resource_deletions': 0}), flush=True)
    cfn.delete_stack(StackName=old['StackId'])
    cfn.get_waiter('stack_delete_complete').wait(StackName=old['StackId'], WaiterConfig={'Delay': 3, 'MaxAttempts': 40})
    change = 'argus-recover-' + uuid4().hex[:12]
    cfn.create_change_set(StackName=stack, ChangeSetName=change, ChangeSetType='CREATE',
                          ImportExistingResources=True, TemplateBody=json.dumps(build_template(account, stack)),
                          Parameters=[{'ParameterKey': 'TrailName', 'ParameterValue': 'argus-ueba-live-trail'}],
                          Capabilities=['CAPABILITY_NAMED_IAM'], Tags=[{'Key': 'Project', 'Value': 'Argus'}])
    cfn.get_waiter('change_set_create_complete').wait(StackName=stack, ChangeSetName=change,
                                                     WaiterConfig={'Delay': 3, 'MaxAttempts': 60})
    described = cfn.describe_change_set(StackName=stack, ChangeSetName=change)
    if any(row['ResourceChange']['Action'] not in ('Add', 'Import') for row in described['Changes']):
        raise ValueError('Recovery change set contains an unexpected modification/deletion')
    print(json.dumps({'recovery_stage': 'auto_import_retained_resources_and_create_missing_lab_resources'}), flush=True)
    cfn.execute_change_set(StackName=stack, ChangeSetName=change, DisableRollback=True)
    cfn.get_waiter('stack_create_complete').wait(StackName=stack, WaiterConfig={'Delay': 5, 'MaxAttempts': 80})
    report['applied'] = True
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-id', required=True)
    parser.add_argument('--stack', default='argus-ueba-actors')
    parser.add_argument('--profile', default='argus-setup')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(recover(args.account_id, args.stack, args.profile, args.apply)))
    except Exception:
        parser.exit(1, 'Recovery stopped; retained resources are preserved. Inspect stack status before retrying.\n')
