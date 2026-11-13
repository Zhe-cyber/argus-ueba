"""Fixed, synthetic-only AWS actor lab definitions. Importing performs no I/O."""
import re

PERSONAS = tuple(f'persona-{i:02d}' for i in range(1, 7))
FIXTURE_KEY = 'fixture.txt'
FIXTURE = b'Argus synthetic activity fixture. No production or personal data.\n'
REGION = 'us-east-1'


def validate_scope(account, stack):
    if not re.fullmatch(r'[0-9]{12}', account):
        raise ValueError('Expected 12-digit AWS account ID')
    if not re.fullmatch(r'argus-[a-z0-9-]{1,17}', stack):
        raise ValueError('Lab stack must start argus- and be at most 23 lowercase characters')


def buckets(account, stack):
    validate_scope(account, stack)
    return [f'{stack}-{account}-p{i:02d}' for i in range(1, 7)] + [f'{stack}-{account}-confidential']


def role_arn(account, stack, persona):
    validate_scope(account, stack)
    if persona not in PERSONAS:
        raise ValueError('Unknown persona')
    return f'arn:aws:iam::{account}:role/argus-lab/{stack}-{persona}'


def build_template(account=None, stack=None):
    if account is not None:
        validate_scope(account, stack)
    resources = {}
    bucket_refs, object_refs = [], []
    for index in range(1, 8):
        logical = f'Bucket{index:02d}'
        suffix = f'p{index:02d}' if index < 7 else 'confidential'
        bucket_refs.append({'Fn::GetAtt': [logical, 'Arn']})
        object_refs.append({'Fn::Sub': '${' + logical + '.Arn}/' + FIXTURE_KEY})
        resources[logical] = {
            'Type': 'AWS::S3::Bucket', 'DeletionPolicy': 'Retain', 'UpdateReplacePolicy': 'Retain',
            'Properties': {
                'BucketName': {'Fn::Sub': '${AWS::StackName}-${AWS::AccountId}-' + suffix},
                'PublicAccessBlockConfiguration': dict.fromkeys(
                    ['BlockPublicAcls', 'BlockPublicPolicy', 'IgnorePublicAcls', 'RestrictPublicBuckets'], True),
                'OwnershipControls': {'Rules': [{'ObjectOwnership': 'BucketOwnerEnforced'}]},
                'BucketEncryption': {'ServerSideEncryptionConfiguration': [
                    {'ServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]},
                'LifecycleConfiguration': {'Rules': [{'Id': 'ExpireSyntheticFixture', 'Status': 'Enabled',
                                                     'ExpirationInDays': 30}]},
                'Tags': [{'Key': 'Project', 'Value': 'Argus'}, {'Key': 'Purpose', 'Value': 'SyntheticLab'}],
            },
        }
        resources[logical + 'Policy'] = {'Type': 'AWS::S3::BucketPolicy', 'Properties': {
            'Bucket': {'Ref': logical}, 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [{
                'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*',
                'Resource': [{'Fn::GetAtt': [logical, 'Arn']}, {'Fn::Sub': '${' + logical + '.Arn}/*'}],
                'Condition': {'Bool': {'aws:SecureTransport': 'false'}},
            }]},
        }}
    role_refs = [{'Fn::Sub': 'arn:${AWS::Partition}:iam::${AWS::AccountId}:role/argus-lab/${AWS::StackName}-' + p}
                 for p in PERSONAS]
    resources['RunnerUser'] = {
        'Type': 'AWS::IAM::User', 'DeletionPolicy': 'Retain', 'UpdateReplacePolicy': 'Retain',
        'Properties': {'UserName': {'Fn::Sub': '${AWS::StackName}-runner'}, 'Path': '/argus-lab/',
                       'Tags': [{'Key': 'Project', 'Value': 'Argus'}, {'Key': 'Purpose', 'Value': 'SyntheticLab'}],
                       'Policies': [{'PolicyName': 'AssumeOnlyLabRolesAndCheckAudit', 'PolicyDocument': {
                           'Version': '2012-10-17', 'Statement': [
                               {'Effect': 'Allow', 'Action': ['sts:AssumeRole'], 'Resource': role_refs},
                               {'Effect': 'Allow', 'Action': ['cloudtrail:GetEventSelectors', 'cloudtrail:GetTrailStatus'],
                                'Resource': {'Fn::Sub': 'arn:${AWS::Partition}:cloudtrail:us-east-1:${AWS::AccountId}:trail/${TrailName}'}},
                           ],
                       }}]},
    }
    for index, persona in enumerate(PERSONAS, 1):
        resources[f'Persona{index:02d}'] = {
            'Type': 'AWS::IAM::Role', 'Properties': {
                'RoleName': {'Fn::Sub': '${AWS::StackName}-' + persona}, 'Path': '/argus-lab/',
                'MaxSessionDuration': 3600,
                'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [{
                    'Effect': 'Allow', 'Principal': {'AWS': {'Fn::GetAtt': ['RunnerUser', 'Arn']}},
                    'Action': 'sts:AssumeRole',
                }]},
                'Policies': [{'PolicyName': 'ReadOnlySyntheticFixtures', 'PolicyDocument': {
                    'Version': '2012-10-17', 'Statement': [
                        {'Effect': 'Allow', 'Action': ['s3:GetObject'], 'Resource': object_refs},
                        {'Effect': 'Allow', 'Action': ['s3:GetBucketLocation'], 'Resource': bucket_refs},
                    ],
                }}],
                'Tags': [{'Key': 'Project', 'Value': 'Argus'}, {'Key': 'Purpose', 'Value': 'SyntheticLab'}],
            },
        }
    template = {
        'AWSTemplateFormatVersion': '2010-09-09',
        'Description': 'Argus synthetic-only activity lab: 6 machine roles, 7 private fixture buckets. No app/model deployment.',
        'Parameters': {'TrailName': {'Type': 'String', 'Default': 'argus-ueba-live-trail',
                                     'AllowedPattern': 'argus-[a-z0-9-]+'}},
        'Resources': resources,
        'Outputs': {
            'RunnerUserName': {'Value': {'Ref': 'RunnerUser'}},
            'RunnerUserArn': {'Value': {'Fn::GetAtt': ['RunnerUser', 'Arn']}},
            **{f'Persona{i:02d}RoleArn': {'Value': {'Fn::GetAtt': [f'Persona{i:02d}', 'Arn']}} for i in range(1, 7)},
            **{f'Bucket{i:02d}Name': {'Value': {'Ref': f'Bucket{i:02d}'}} for i in range(1, 8)},
        },
    }
    if account is not None:
        for i, bucket in enumerate(buckets(account, stack), 1):
            template['Resources'][f'Bucket{i:02d}']['Properties']['BucketName'] = bucket
        template['Resources']['RunnerUser']['Properties']['UserName'] = stack + '-runner'
        for i, persona in enumerate(PERSONAS, 1):
            template['Resources'][f'Persona{i:02d}']['Properties']['RoleName'] = stack + '-' + persona
    return template
