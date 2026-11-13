"""Provisioning safety gates: reject wrong account/region before mutations."""
from argparse import Namespace
from unittest.mock import Mock

import pytest

from scripts import setup_aws


def options(**overrides):
    values = dict(profile='setup-test', region='us-east-1', account_id='123456789012',
                  stack='argus-test', collector_user='collector-test', deploy=True)
    values.update(overrides)
    return Namespace(**values)


def test_wrong_account_never_changes_resources(monkeypatch):
    api = Mock(return_value={'Account': '999999999999'})
    deploy = Mock()
    monkeypatch.setattr(setup_aws, 'aws', api)
    monkeypatch.setattr(setup_aws.subprocess, 'run', deploy)
    with pytest.raises(ValueError, match='does not match'):
        setup_aws.setup(options())
    assert api.call_count == 1
    deploy.assert_not_called()


@pytest.mark.parametrize('overrides', [
    {'region': 'ap-southeast-1'}, {'stack': 'Wrong_Bucket_Name'},
    {'stack': '../other'}, {'account_id': 'not-an-account'},
])
def test_invalid_target_never_contacts_aws(monkeypatch, overrides):
    api = Mock()
    monkeypatch.setattr(setup_aws, 'aws', api)
    with pytest.raises(ValueError):
        setup_aws.setup(options(**overrides))
    api.assert_not_called()


def test_default_inspection_validates_without_deployment(monkeypatch):
    api = Mock(side_effect=[{'Account': '123456789012'}, {'User': {}},
                           {'Capabilities': ['CAPABILITY_NAMED_IAM']}])
    deploy = Mock()
    monkeypatch.setattr(setup_aws, 'aws', api)
    monkeypatch.setattr(setup_aws.subprocess, 'run', deploy)
    report = setup_aws.setup(options(deploy=False))
    assert report['template_validated'] is True
    assert report['deployed'] is False
    deploy.assert_not_called()
