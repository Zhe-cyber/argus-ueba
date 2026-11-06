"""Native repository-activity evidence, distinct from GitHub Events API records."""
from datetime import datetime
import re


FORMAT = 'github_repository_activity_v1'
ACTIONS = {'push': 'Repository push', 'force_push': 'Repository force push',
           'branch_creation': 'Repository branch creation', 'branch_deletion': 'Repository branch deletion',
           'pr_merge': 'Repository PR merge', 'merge_queue_merge': 'Repository merge queue merge'}


def receipt_id(repo_id, activity_id):
    if (type(repo_id) is not int or repo_id <= 0 or type(activity_id) is not int or activity_id <= 0):
        raise ValueError('Positive native repository/activity IDs required')
    return f'repository-activity:{repo_id}:{activity_id}'


def normalize_activity(raw, repository, repo_id):
    if not isinstance(raw, dict) or not isinstance(repository, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Native activity and repository request context required')
    if any(part in {'.', '..'} for part in repository.split('/')):
        raise ValueError('Invalid repository request context')
    event_id = receipt_id(repo_id, raw.get('id'))
    actor = raw.get('actor')
    if (not isinstance(actor, dict) or type(actor.get('id')) is not int or actor['id'] <= 0
            or not isinstance(actor.get('login'), str) or not actor['login'].strip()):
        raise ValueError('Native activity actor required')
    kind, timestamp = raw.get('activity_type'), raw.get('timestamp')
    if kind not in ACTIONS or not isinstance(timestamp, str):
        raise ValueError('Unsupported native activity type/time')
    try:
        valid = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).tzinfo is not None
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Zoned native activity timestamp required')
    for field in ['before', 'after']:
        if not isinstance(raw.get(field), str) or not re.fullmatch(r'[0-9a-f]{40}', raw[field]):
            raise ValueError('Native activity commit references required')
    if not isinstance(raw.get('ref'), str) or not raw['ref'].startswith('refs/'):
        raise ValueError('Native activity Git reference required')
    return {'source': 'github_events', 'timestamp': timestamp, 'user': actor['login'],
            'action': ACTIONS[kind], 'resource': repository, 'ip_address': '', 'raw': raw,
            'event_id': event_id, 'metadata': {
                'evidence_format': FORMAT, 'provider_endpoint': 'repository_activity',
                'provider_api_version': '2022-11-28', 'native_activity_id': raw['id'],
                'actor_id': actor['id'], 'actor_type': actor.get('type'), 'repository_id': repo_id,
                'repository_context_basis': 'collector_verified_request',
                'activity_type': kind, 'ref': raw['ref'], 'before': raw['before'], 'after': raw['after'],
                'commit_count_status': 'unknown', 'public_status': 'not_in_activity_payload'}}
