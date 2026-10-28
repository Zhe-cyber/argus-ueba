"""Offline resource semantics only; no model, provider I/O or runtime registration."""
from dataclasses import dataclass
import hashlib
import json
import re


CONTRACT = 'resource_observability_v1'


def token(*parts):
    return hashlib.sha256(json.dumps([CONTRACT, *parts], ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def text(value):
    return isinstance(value, str) and bool(value) and len(value) <= 16384


@dataclass(frozen=True)
class Resource:
    status: str
    container: str | None = None
    object: str | None = None


def clue_resource(event):
    params = event.get('params', {})
    if not isinstance(params, dict):
        return Resource('invalid_params')
    path = params.get('path')
    if not text(path):
        return Resource('missing_or_invalid_path')
    # The uid must never become part of the resource identity.
    return Resource('literal_path', object=token('clue-7119953', 'path', path))


def aws_s3_resource(event):
    if event.get('eventSource') != 's3.amazonaws.com':
        return Resource('unsupported_service')
    account = event.get('recipientAccountId')
    if not isinstance(account, str) or re.fullmatch(r'[0-9]{12}', account) is None:
        return Resource('missing_or_invalid_account_scope')
    params = event.get('requestParameters')
    if not isinstance(params, dict) or not text(params.get('bucketName')):
        return Resource('missing_or_invalid_bucket')
    bucket = params['bucketName']
    container = token('aws', account, 's3', 'bucket', bucket)
    if 'key' not in params:
        return Resource('bucket_only', container=container)
    if not text(params['key']):
        return Resource('missing_or_invalid_key', container=container)
    return Resource('object_key', container,
                    token('aws', account, 's3', 'object', bucket, params['key']))


def resource(source, event):
    if not isinstance(event, dict):
        return Resource('invalid_event')
    if source == 'clue-7119953':
        return clue_resource(event)
    if source == 'aws_cloudtrail':
        return aws_s3_resource(event)
    return Resource('unsupported_source')
