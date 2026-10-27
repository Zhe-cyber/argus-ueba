"""Actor safety and audit-correlation tests; no real providers or credentials."""
from copy import deepcopy
import io
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from scripts import audit_simulation as audit, run_simulation as runner, setup_simulation as setup
from scripts.simulation_lab import FIXTURE, PERSONAS, buckets, build_template

ACCOUNT, STACK = '123456789012', 'argus-ueba-actors'
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def cloud(monkeypatch):
    import boto3
    state = SimpleNamespace(calls=[], root=False, logging=True, covered=True, fail_read=False, current=None)
    class STS:
        def get_caller_identity(self):
            state.calls.append(('GetCallerIdentity', {}))
            return {'Account': ACCOUNT, 'Arn': (f'arn:aws:iam::{ACCOUNT}:root' if state.root else
                    f'arn:aws:iam::{ACCOUNT}:user/argus-lab/{STACK}-runner')}
        def assume_role(self, **kwargs):
            state.calls.append(('AssumeRole', kwargs))
            persona = kwargs['RoleSessionName'].removeprefix('argus-')
            state.current = persona
            return {'AssumedRoleUser': {'Arn': f'arn:aws:sts::{ACCOUNT}:assumed-role/{STACK}-{persona}/argus-{persona}',
                                       'AssumedRoleId': f'FAKEROLE-{persona}:argus-{persona}'},
                    'Credentials': {'AccessKeyId': 'DUMMYKEY', 'SecretAccessKey': 'DUMMYSECRET', 'SessionToken': 'DUMMYTOKEN'}}
    class Trail:
        def get_trail_status(self, **kwargs):
            state.calls.append(('GetTrailStatus', kwargs))
            return {'IsLogging': state.logging}
        def get_event_selectors(self, **kwargs):
            state.calls.append(('GetEventSelectors', kwargs))
            return {'EventSelectors': [{'ReadWriteType': 'ReadOnly', 'DataResources': [{
                'Type': 'AWS::S3::Object', 'Values': [f'arn:aws:s3:::{b}/' for b in buckets(ACCOUNT, STACK)] if state.covered else []}]}]}
    class S3:
        def response(self, operation, kwargs):
            state.calls.append((operation, kwargs))
            if operation == 'GetObject' and state.fail_read:
                raise RuntimeError('DUMMYSECRET must never be printed')
            result = {'ResponseMetadata': {'RequestId': f'request-{len(state.calls)}'}}
            if operation != 'GetBucketLocation':
                result.update(Metadata={'argus-lab': STACK}, ContentLength=len(FIXTURE))
            if operation == 'GetObject':
                result['Body'] = io.BytesIO(FIXTURE)
            return result
        def get_object(self, **kwargs): return self.response('GetObject', kwargs)
        def head_object(self, **kwargs): return self.response('HeadObject', kwargs)
        def get_bucket_location(self, **kwargs): return self.response('GetBucketLocation', kwargs)
        def close(self): pass
    def client(service, **kwargs):
        return {'sts': STS, 'cloudtrail': Trail, 's3': S3}[service]()
    monkeypatch.setattr(boto3, 'Session', lambda **kwargs: SimpleNamespace(client=client))
    monkeypatch.setattr(boto3, 'client', client)
    return state


def test_plans_are_reproducible_bounded_and_keep_the_same_identity():
    baseline = runner.make_plan(ACCOUNT, STACK)
    assert baseline == runner.make_plan(ACCOUNT, STACK)
    transition = runner.make_plan(ACCOUNT, STACK, phase='transition')
    assert baseline['personas'] == transition['personas'] == list(PERSONAS)
    assert baseline['planned_requests'] == 28
    assert transition['planned_requests'] == 47
    assert {a['operation'] for a in transition['actions']} == set(runner.METHODS)
    assert all(a['bucket'] in buckets(ACCOUNT, STACK) for a in transition['actions'])
    with pytest.raises(ValueError, match='budget'):
        runner.make_plan(ACCOUNT, STACK, max_requests=10)


def test_default_cli_does_not_construct_clients_or_write_files(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr(runner, 'execute', lambda *a, **k: pytest.fail('Dry-run executed cloud activity'))
    monkeypatch.setattr('sys.argv', ['run_simulation', '--account-id', ACCOUNT])
    assert runner.main() == 0
    assert json.loads(capsys.readouterr().out)['mode'] == 'dry_run'
    assert list(tmp_path.iterdir()) == []


def test_template_has_no_keys_or_outside_read_permissions():
    template = build_template()
    assert json.loads((ROOT / 'infra/aws-simulation.json').read_text()) == template
    resources = template['Resources']
    roles = [r for r in resources.values() if r['Type'] == 'AWS::IAM::Role']
    storage = [r for r in resources.values() if r['Type'] == 'AWS::S3::Bucket']
    assert len(roles) == 6 and len(storage) == 7
    assert not any(r['Type'] == 'AWS::IAM::AccessKey' for r in resources.values())
    for role in roles:
        statements = role['Properties']['Policies'][0]['PolicyDocument']['Statement']
        assert {a for s in statements for a in s['Action']} == {'s3:GetObject', 's3:GetBucketLocation'}
        assert all(s['Resource'] != '*' for s in statements)
        assert role['Properties']['AssumeRolePolicyDocument']['Statement'][0]['Principal'] == {'AWS': {'Fn::GetAtt': ['RunnerUser', 'Arn']}}
    for bucket in storage:
        assert bucket['DeletionPolicy'] == 'Retain'
        assert all(bucket['Properties']['PublicAccessBlockConfiguration'].values())


def test_trail_data_selector_is_optional_read_only_and_scoped():
    template = json.loads((ROOT / 'infra/aws-live.json').read_text())
    assert template['Parameters']['EnableSimulationData']['Default'] == 'false'
    selectors = template['Resources']['Trail']['Properties']['EventSelectors']
    assert selectors[0]['IncludeManagementEvents'] is True
    data = selectors[1]['Fn::If'][1]
    assert data['ReadWriteType'] == 'ReadOnly' and data['IncludeManagementEvents'] is False
    values = data['DataResources'][0]['Values']
    assert len(values) == 7
    assert all('${SimulationStack}-${AWS::AccountId}-' in v['Fn::Sub'] for v in values)


@pytest.mark.parametrize('condition', ['root', 'logging', 'covered'])
def test_execution_stops_before_persona_actions_without_valid_audit_identity(cloud, condition):
    setattr(cloud, condition, condition == 'root')
    with pytest.raises(ValueError):
        runner.execute(runner.make_plan(ACCOUNT, STACK), 'test', 'argus-ueba-live-trail')
    assert not any(name in runner.METHODS or name == 'AssumeRole' for name, _ in cloud.calls)


def test_provider_calls_are_bounded_neutral_and_credentials_stay_out_of_manifest(cloud):
    snapshots = []
    plan = runner.make_plan(ACCOUNT, STACK)
    result = runner.execute(plan, 'test', 'argus-ueba-live-trail', progress=lambda r: snapshots.append(deepcopy(r)))
    assert result['status'] == 'completed'
    assert len(cloud.calls) == plan['planned_requests']
    assert len(result['principals']) == len(set(result['principals'].values())) == 6
    assert all(r['status'] == 'ok' and r['request_id'] for r in result['results'])
    assert 'DUMMYSECRET' not in json.dumps(snapshots) and 'DUMMYTOKEN' not in json.dumps(result)
    assert not any(word in json.dumps(cloud.calls).lower() for word in ('transition', 'baseline', 'attacker'))


def test_tampered_plan_and_unverified_transition_do_not_touch_cloud(cloud):
    plan = runner.make_plan(ACCOUNT, STACK)
    plan['actions'][0]['bucket'] = 'unrelated-production'
    with pytest.raises(ValueError):
        runner.execute(plan, 'test', 'argus-ueba-live-trail')
    with pytest.raises(ValueError, match='baseline'):
        runner.execute(runner.make_plan(ACCOUNT, STACK, phase='transition'), 'test', 'argus-ueba-live-trail')
    assert cloud.calls == []


def test_failure_preserves_private_checkpoint_without_secret_output(monkeypatch, cloud, tmp_path, capsys):
    cloud.fail_read = True
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr('sys.argv', ['run_simulation', '--account-id', ACCOUNT, '--execute'])
    assert runner.main() == 1
    paths = list((tmp_path / 'data/live/experiments').glob('*/manifest.json'))
    saved = json.loads(paths[0].read_text())
    assert saved['status'] == 'failed' and saved['results'][0]['status'] == 'ok'
    assert 'DUMMYSECRET' not in capsys.readouterr().err + paths[0].read_text()


def test_audit_requires_matching_native_evidence_not_merely_api_success(monkeypatch, cloud, tmp_path):
    result = runner.execute(runner.make_plan(ACCOUNT, STACK), 'test', 'argus-ueba-live-trail')
    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    folder = tmp_path / 'data/live/experiments/run'
    folder.mkdir(parents=True)
    manifest = folder / 'manifest.json'
    manifest.write_text(json.dumps(result))
    state = tmp_path / 'data/live/connected'
    state.mkdir()
    with sqlite3.connect(state / 'events.db') as con:
        con.execute('CREATE TABLE events(event_id TEXT,source TEXT,source_account_id TEXT,action TEXT,resource TEXT,metadata TEXT,timestamp TEXT)')
        for i, row in enumerate(result['results']):
            metadata = {'requestID': row['request_id'], 'userIdentity': {'principalId': result['principals'][row['persona']]}}
            con.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)',
                        (f'native-{i}', 'aws_cloudtrail', ACCOUNT, row['operation'], row['bucket'], json.dumps(metadata), '2026-10-27T12:00:00Z'))
    report, path = audit.verify(manifest, state)
    assert report['status'] == 'complete' and report['matched_actions'] == len(result['results'])
    runner.check_baseline(manifest, path, runner.make_plan(ACCOUNT, STACK, phase='transition'))
    with sqlite3.connect(state / 'events.db') as con:
        con.execute("DELETE FROM events WHERE event_id='native-0'")
    report, _ = audit.verify(manifest, state)
    assert report['status'] == 'pending'
    with pytest.raises(ValueError):
        runner.check_baseline(manifest, path, runner.make_plan(ACCOUNT, STACK, phase='transition'))


def test_setup_plan_never_uses_credentials_by_default(monkeypatch):
    monkeypatch.setattr(setup, 'aws', lambda *args: pytest.fail('Planning accessed AWS'))
    args = SimpleNamespace(account_id=ACCOUNT, stack=STACK, live_stack='argus-ueba-live', deploy=False, configure_runner=False)
    assert setup.setup(args)['new_model_training'] is False


def test_existing_runner_profile_is_reused_only_for_the_exact_lab_user(monkeypatch, tmp_path):
    home = tmp_path / 'home'
    folder = home / '.aws'
    folder.mkdir(parents=True)
    credentials = folder / 'credentials'
    credentials.write_text('[default]\naws_access_key_id=unchanged\n[argus-simulator]\naws_access_key_id=dummy\n')
    original = credentials.read_bytes()
    monkeypatch.setattr(setup.Path, 'home', lambda: home)
    calls = []
    def identity(profile, region, *args):
        calls.append((profile, args))
        return {'Account': ACCOUNT, 'Arn': f'arn:aws:iam::{ACCOUNT}:user/argus-lab/{STACK}-runner'}
    monkeypatch.setattr(setup, 'aws', identity)
    assert setup.configure_runner('setup', ACCOUNT, STACK) == 'argus-simulator'
    assert credentials.read_bytes() == original
    assert calls == [('argus-simulator', ('sts', 'get-caller-identity'))]
    monkeypatch.setattr(setup, 'aws', lambda *args: {'Account': ACCOUNT, 'Arn': f'arn:aws:iam::{ACCOUNT}:root'})
    with pytest.raises(ValueError):
        setup.configure_runner('setup', ACCOUNT, STACK)
