"""Bounded, one-shot collectors for a LOCAL Argus live backend. No background jobs.

AWS acknowledges only committed receipts; malformed/rejected messages stay for
retry/DLQ. Cloudflare/GitHub queries are bounded samples, not complete histories.
Only counts/status are printed; provider credentials remain in their local stores.
"""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlencode, urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class CollectionError(Exception):
    pass


def local_api(url):
    parsed = urlparse(url)
    try:
        loopback = ipaddress.ip_address(parsed.hostname or '').is_loopback
        port = parsed.port
    except ValueError:
        loopback, port = False, None
    if (parsed.scheme != 'http' or not loopback or port is None or parsed.username
            or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise CollectionError('Backend must be an explicit HTTP loopback IP and port, with no extra URL components.')
    return url.rstrip('/')


class LocalBackend:
    def __init__(self, url):
        self.url = local_api(url)
        self.session = requests.Session()
        self.session.trust_env = False  # Never route personal logs through an ambient proxy.

    def preflight(self):
        try:
            response = self.session.get(self.url + '/', timeout=10, allow_redirects=False)
            health = response.json()
        except (requests.RequestException, ValueError):
            raise CollectionError('Local backend is not ready; no events forwarded.') from None
        if (response.status_code != 200 or not isinstance(health, dict) or health.get('application_mode') != 'live'
                or health.get('ingestion_protocol') != 'native-receipt-v1'):
            raise CollectionError('Require a live backend with native-receipt-v1; no events forwarded.')

    def post_receipt(self, source, namespace, record, native_id):
        try:
            response = self.session.post(self.url + '/ingest', timeout=45, allow_redirects=False,
                                         json={'source': source, 'source_account_id': namespace, 'event': record})
            receipt = response.json()
        except (requests.RequestException, ValueError):
            return None
        if (source == 'github_events' and response.status_code == 409
                and receipt == {'detail': 'Native event key already exists with different content'}):
            return {'status': 'payload_conflict'}
        if (response.status_code != 200 or not isinstance(receipt, dict)
                or receipt.get('source') != source or receipt.get('source_account_id') != namespace
                or receipt.get('event_id') != str(native_id) or type(receipt.get('duplicate')) is not bool
                or not isinstance(receipt.get('total_events'), int) or receipt['total_events'] < 1):
            return None
        return {'status': 'committed', 'duplicate': receipt['duplicate']}

    def post(self, source, namespace, record, native_id):
        receipt = self.post_receipt(source, namespace, record, native_id)
        return receipt['duplicate'] if receipt and receipt['status'] == 'committed' else None

    def post_github_activity(self, namespace, repository, repo_id, record):
        from backend.github_activity import receipt_id
        expected = receipt_id(repo_id, record.get('id'))
        try:
            response = self.session.post(self.url + '/ingest/github-repository-activity', timeout=45,
                allow_redirects=False, json={'source_account_id': namespace, 'repository': repository,
                                             'repository_id': repo_id, 'event': record})
            receipt = response.json()
        except (requests.RequestException, ValueError):
            return None
        if (response.status_code != 200 or not isinstance(receipt, dict)
                or receipt.get('source') != 'github_events' or receipt.get('source_account_id') != namespace
                or receipt.get('event_id') != expected or type(receipt.get('duplicate')) is not bool
                or type(receipt.get('total_events')) is not int or receipt['total_events'] < 1):
            return None
        return receipt['duplicate']


def archive_github_revision(directory, namespace, record, native_id):
    """Keep changed provider representations separate from immutable event receipts.

    Content-addressed, exclusively created snapshots are not new activity events.
    A failed or corrupt snapshot remains a collection failure.
    """
    payload = json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(payload) > 512 * 1024:
        raise CollectionError('Provider revision exceeds archive size limit.')
    payload_sha = hashlib.sha256(payload).hexdigest()
    identity = {'source': 'github_events', 'source_account_id': namespace,
                'event_id': str(native_id), 'payload_sha256': payload_sha}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (key + '.json')
    snapshot = {**identity, 'schema': 'github_provider_revision_v1', 'event': record,
                'captured_at_utc': datetime.now(timezone.utc).isoformat(),
                'interpretation': 'Changed provider representation; not a new activity event.'}
    try:
        with path.open('xb') as stream:
            stream.write(json.dumps(snapshot, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        return True
    except FileExistsError:
        if path.stat().st_size > 1024 * 1024:
            raise CollectionError('Existing revision archive is invalid.')
        existing = json.loads(path.read_bytes())
        if (not isinstance(existing, dict) or any(existing.get(k) != v for k, v in identity.items())
                or existing.get('schema') != snapshot['schema'] or existing.get('event') != record):
            raise CollectionError('Existing revision archive is invalid.')
        return False


def stats():
    return dict(received=0, inserted=0, duplicates=0, retained=0, malformed=0, skipped=0, acknowledged=0)


def valid_time(value):
    try:
        return bool(isinstance(value, str) and datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo)
    except ValueError:
        return False


def forward(backend, source, namespace, records, native_field, revision_dir=None):
    counts = stats()
    if revision_dir is not None:
        if source != 'github_events':
            raise CollectionError('Revision archive is supported only for GitHub.')
        counts.update(provider_revisions=0, revision_snapshots_created=0)
    for record in records:
        counts['received'] += 1
        native = record.get(native_field)
        timestamp = record.get('created_at')
        if not isinstance(native, (str, int)) or isinstance(native, bool) or not str(native).strip() or not valid_time(timestamp):
            counts['malformed'] += 1
            counts['retained'] += 1
            continue
        if revision_dir is not None:
            receipt = backend.post_receipt(source, namespace, record, native)
            if receipt and receipt['status'] == 'payload_conflict':
                try:
                    created = archive_github_revision(revision_dir, namespace, record, native)
                except (OSError, ValueError, CollectionError):
                    counts['retained'] += 1
                else:
                    counts['provider_revisions'] += 1
                    counts['revision_snapshots_created'] += int(created)
                continue
            duplicate = receipt['duplicate'] if receipt and receipt['status'] == 'committed' else None
        else:
            duplicate = backend.post(source, namespace, record, native)
        counts['retained' if duplicate is None else ('duplicates' if duplicate else 'inserted')] += 1
    return counts


def aws_record(body, account):
    if not isinstance(body, dict):
        return None
    if isinstance(body.get('detail'), dict):
        if (body.get('account') != account or not str(body.get('source', '')).startswith('aws.')
                or body.get('detail-type') not in ('AWS API Call via CloudTrail', 'AWS Console Sign In via CloudTrail')):
            return None
        record = body['detail']
    else:
        record = body
    identity = record.get('userIdentity')
    if not isinstance(identity, dict):
        return None
    native_account = record.get('recipientAccountId') or identity.get('accountId')
    if native_account and native_account != account:
        return None
    if 'detail' not in body and native_account != account:
        return None
    if not (isinstance(record.get('eventID'), str) and record['eventID'].strip()
            and record.get('eventName') and valid_time(record.get('eventTime'))):
        return None
    return record


def consume_sqs(sqs, queue_url, account, backend, batches=1):
    counts = stats()
    for _ in range(batches):
        messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=1).get('Messages', [])
        for message in messages:
            counts['received'] += 1
            try:
                record = aws_record(json.loads(message['Body']), account)
            except (ValueError, TypeError, KeyError):
                record = None
            if record is None or not message.get('ReceiptHandle'):
                counts['malformed'] += 1
                counts['retained'] += 1
                continue
            duplicate = backend.post('aws_cloudtrail', account, record, record['eventID'])
            if duplicate is None:
                counts['retained'] += 1
                continue
            counts['duplicates' if duplicate else 'inserted'] += 1
            try:
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message['ReceiptHandle'])
                counts['acknowledged'] += 1
            except Exception:
                counts['retained'] += 1  # Retry is safe even when deletion failed.
    return counts


def collect_aws(args, backend):
    import boto3
    queue = urlparse(args.queue_url)
    if (queue.scheme != 'https' or queue.netloc != 'sqs.us-east-1.amazonaws.com'
            or queue.query or queue.fragment
            or not re.fullmatch('/' + args.account_id + r'/[a-zA-Z0-9_-]+', queue.path)):
        raise CollectionError('Queue URL must belong to the expected account in us-east-1.')
    session = boto3.Session(profile_name=args.profile, region_name='us-east-1')
    caller = session.client('sts').get_caller_identity()
    if caller['Account'] != args.account_id or caller['Arn'].endswith(':root'):
        raise CollectionError('Require a non-root collector identity in the expected account.')
    sqs = session.client('sqs')
    attributes = sqs.get_queue_attributes(QueueUrl=args.queue_url, AttributeNames=['QueueArn', 'RedrivePolicy'])['Attributes']
    expected_arn = f"arn:aws:sqs:us-east-1:{args.account_id}:{queue.path.rsplit('/', 1)[1]}"
    redrive = json.loads(attributes.get('RedrivePolicy', '{}'))
    if attributes.get('QueueArn') != expected_arn or not redrive.get('deadLetterTargetArn', '').startswith(f'arn:aws:sqs:us-east-1:{args.account_id}:'):
        raise CollectionError('Queue account or dead-letter configuration is unverified.')
    return consume_sqs(sqs, args.queue_url, args.account_id, backend, args.batches)


def collect_cloudflare(args, backend):
    from scripts.setup_cloudflare import Cloudflare, load_token
    api = Cloudflare(args.account_id, load_token(args.account_id))
    now = datetime.now(timezone.utc)
    query = urlencode({'limit': 100, 'direction': 'desc', 'since': (now - timedelta(hours=24)).isoformat(), 'until': now.isoformat()})
    records = api.call('GET', 'access/logs/access_requests?' + query)
    if not isinstance(records, list):
        raise CollectionError('Unexpected Cloudflare log response.')
    matching = [r for r in records if isinstance(r, dict) and r.get('app_uid') == args.app_id]
    selected = [r for r in matching if isinstance(r.get('user_email'), str)
                and r['user_email'].strip() and type(r.get('allowed')) is bool]
    counts = forward(backend, 'cloudflare_access', args.account_id, selected, 'ray_id')
    invalid = len(matching) - len(selected)
    counts['received'] = len(records)
    counts['malformed'] += invalid
    counts['retained'] += invalid
    counts['skipped'] = len(records) - len(matching)
    return counts


def gh_json(path):
    result = subprocess.run(['gh', 'api', '--hostname', 'github.com', path], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise CollectionError('GitHub CLI request failed; no raw error or record displayed.')
    return json.loads(result.stdout)


def collect_github(args, backend):
    repo = gh_json('repos/' + args.repo)
    viewer = gh_json('user')
    if repo.get('owner', {}).get('id') != viewer.get('id') and not repo.get('permissions', {}).get('admin'):
        raise CollectionError('Repository ownership/admin access was not verified.')
    records = gh_json('repos/' + args.repo + '/events?per_page=100&page=1')
    if not isinstance(records, list):
        raise CollectionError('Unexpected GitHub activity response.')
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    selected = [r for r in records if isinstance(r, dict) and valid_time(r.get('created_at'))
                and datetime.fromisoformat(r['created_at'].replace('Z', '+00:00')) >= since]
    counts = forward(backend, 'github_events', 'github-owner:' + str(repo['owner']['id']), selected, 'id',
                     revision_dir=getattr(args, 'revision_dir', None))
    counts['received'] = len(records)
    counts['skipped'] = len(records) - len(selected)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', default='http://127.0.0.1:8000')
    sub = parser.add_subparsers(dest='source', required=True)
    aws = sub.add_parser('aws')
    aws.add_argument('--account-id', required=True)
    aws.add_argument('--queue-url', required=True)
    aws.add_argument('--profile', default='argus-collector')
    aws.add_argument('--batches', type=int, choices=range(1, 6), default=1)
    cf = sub.add_parser('cloudflare')
    cf.add_argument('--account-id', required=True)
    cf.add_argument('--app-id', required=True)
    gh = sub.add_parser('github', description='GitHub activity Events API, not organization security audit logs.')
    gh.add_argument('--repo', required=True)
    gh.add_argument('--revision-dir', type=Path, help='Private local archive for changed GitHub event representations.')
    args = parser.parse_args()
    if args.source == 'aws' and not re.fullmatch(r'[0-9]{12}', args.account_id):
        parser.error('AWS account ID must have 12 digits')
    if args.source == 'cloudflare' and (not re.fullmatch(r'[a-f0-9]{32}', args.account_id)
            or not re.fullmatch(r'[a-f0-9-]{36}', args.app_id)):
        parser.error('Invalid Cloudflare account/application ID')
    if args.source == 'github' and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repo):
        parser.error('Invalid owner/repository name')
    try:
        backend = LocalBackend(args.api)
        backend.preflight()
        result = {'aws': collect_aws, 'cloudflare': collect_cloudflare, 'github': collect_github}[args.source](args, backend)
        print(json.dumps({'source': args.source, 'bounded_sample': True, **result}))
        return 1 if result['retained'] else 0
    except Exception:
        print('Collection stopped. Check local backend, account/profile and provider access. No raw records or errors displayed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
