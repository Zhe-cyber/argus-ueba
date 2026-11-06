"""Offline shared_behavior_core_v1 candidate. No runtime registration or model."""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from zoneinfo import ZoneInfo
from scripts.clue_features import KNOWN_ACTIONS, SHARING

PROFILE = 'shared_behavior_core_v1'
FEATURES = ['event_count', 'unique_actions', 'unique_resources', 'off_hours_fraction', 'new_action_count']
K = 5
HOURS = {'clue': ('UTC', 7, 19), 'aws_cloudtrail': ('Asia/Kuala_Lumpur', 8, 20),
         'github_events': ('Asia/Kuala_Lumpur', 8, 20), 'cloudflare_access': ('Asia/Kuala_Lumpur', 8, 20)}
PATH_REQUIRED = {'file_accessed', 'file_created', 'file_deleted', 'file_updated', 'file_written',
                 'permission_changed', 'version_deleted', 'version_restored', 'deleted_from_trashbin',
                 'comment_added', 'comment_deleted', 'public_share_accessed', 'public_share_update_permission'}
SHARE_PATH_REQUIRED = SHARING
PUBLIC_PATH_MISSING = {'public_share_expiration_date_changed', 'public_share_password_changed'}
GH_LABELS = {'Code push': 'PushEvent', 'Branch/tag created': 'CreateEvent', 'Branch/tag deleted': 'DeleteEvent',
             'Pull request': 'PullRequestEvent', 'Issue activity': 'IssuesEvent', 'Issue comment': 'IssueCommentEvent',
             'Repository forked': 'ForkEvent', 'Repository starred': 'WatchEvent', 'Release published': 'ReleaseEvent',
             'Member change': 'MemberEvent', 'Repository made public': 'PublicEvent', 'Wiki updated': 'GollumEvent',
             'Commit comment': 'CommitCommentEvent', 'PR review': 'PullRequestReviewEvent'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def instant(value):
    if not isinstance(value, str):
        raise ValueError('Timestamp string required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp offset required')
    return result.astimezone(timezone.utc)


def namespace_path(value):
    if not isinstance(value, str) or not value or len(value) > 16384:
        return None
    parts = [part for part in value.split('/') if part]
    return parts[0] if parts else None


def clue_path(row):
    params, action = row.get('params', {}), row.get('type')
    if not isinstance(params, dict):
        return None, 'invalid_params'
    if action in {'file_copied', 'file_renamed'}:
        field = 'newpath'
    elif action == 'restored_from_trashbin':
        field = 'filePath'
    elif action in SHARE_PATH_REQUIRED:
        field = 'fileTarget'
    elif action in PATH_REQUIRED or action in PUBLIC_PATH_MISSING:
        field = 'path'
    else:
        field = 'path' if 'path' in params else None
    if field is None:
        return None, None
    path = params.get(field)
    if namespace_path(path) is None:
        return None, 'missing_required_resource'
    return path, None


@dataclass(frozen=True)
class Event:
    source: str
    scope: str
    account: str
    reference: str
    timestamp: datetime
    action: str
    resource: str | None
    payload_digest: str
    issue: str | None = None

    @property
    def local(self):
        return self.timestamp.astimezone(ZoneInfo(HOURS[self.source][0]))

    @property
    def day(self):
        return self.local.date().isoformat()

    @property
    def off_hours(self):
        _, start, end = HOURS[self.source]
        return not start <= self.local.hour < end


def project_clue(row, synthetic=False):
    if row.get('uidType') != 'name' or not isinstance(row.get('uid'), str) or not row['uid']:
        raise ValueError('Named CLUE account required')
    native = row.get('id')
    if not (type(native) is int and native > 0):
        if not (synthetic and isinstance(native, str) and native.startswith('sim:') and row.get('_argus_scenario')):
            raise ValueError('Native CLUE ID required; synthetic intake is explicit')
    action = row.get('type')
    if not isinstance(action, str) or not action or len(action) > 128:
        raise ValueError('Native action required')
    path, issue = clue_path(row)
    if action not in KNOWN_ACTIONS:
        issue = 'unknown_action'
    resource = digest(['clue', '7119953', 'namespace', namespace_path(path)]) if path else None
    return Event('clue', '7119953', hashlib.sha256(('clue-7119953:' + row['uid']).encode()).hexdigest(),
                 str(native), instant(row['time']), action, resource, digest(row), issue)


def github_kind(label):
    if label in GH_LABELS:
        return GH_LABELS[label]
    if re.fullmatch(r'Code push \([0-9]+ commits?\)', label):
        return 'PushEvent'
    if re.fullmatch(r'PR [A-Za-z_]+', label):
        return 'PullRequestEvent'
    if re.fullmatch(r'Issue [A-Za-z_]+', label):
        return 'IssuesEvent'
    raise ValueError('Unknown or ambiguous GitHub display projection')


def project_live(row):
    source, scope, account = row.get('source'), row.get('source_account_id'), row.get('account_key')
    if source not in HOURS or source == 'clue' or not isinstance(scope, str) or not scope:
        raise ValueError('Supported source and namespace required')
    if not isinstance(account, str) or re.fullmatch(r'acct_[0-9a-f]{64}', account) is None:
        raise ValueError('Native scoped account key required')
    native, payload = row.get('event_id'), row.get('payload_digest')
    if not isinstance(native, str) or not native or not isinstance(payload, str) or re.fullmatch(r'[0-9a-f]{64}', payload) is None:
        raise ValueError('Native event provenance required')
    meta = row.get('metadata') or {}
    if isinstance(meta, str):
        meta = json.loads(meta)
    if not isinstance(meta, dict) or not isinstance(row.get('action'), str):
        raise ValueError('Invalid projection metadata/action')
    action, value, issue = row['action'], row.get('resource'), None
    resource = None
    if source == 'github_events':
        try:
            action = github_kind(action)
        except ValueError:
            issue = 'unknown_action'
        if isinstance(value, str) and re.fullmatch(r'[^/\s]+/[^/\s]+', value):
            resource = digest([source, scope, 'repository', value])
        else:
            issue = 'missing_required_resource'
    elif source == 'cloudflare_access':
        # Native action only: never infer successful authentication from no denied suffix.
        action = action.removesuffix(' (denied)')
        if action not in {'login', 'logout', 'allow', 'deny', 'access'}:
            issue = 'unknown_action'
        elif action == 'access':
            issue = 'native_action_missing_or_default_ambiguous'
        if isinstance(value, str) and value and not any(c.isspace() for c in value):
            resource = digest([source, scope, 'application', value])
        else:
            issue = 'missing_required_resource'
    else:
        service = meta.get('eventSource')
        if not isinstance(service, str) or not re.fullmatch(r'[A-Za-z0-9.-]+\.amazonaws\.com', service) or not re.fullmatch(r'[A-Za-z0-9_]+', action):
            raise ValueError('AWS native service/action provenance required')
        if service == 's3.amazonaws.com' and action in {'GetObject', 'HeadObject', 'GetBucketLocation', 'ListObjects', 'ListObjectsV2', 'ListBucket'}:
            if isinstance(value, str) and re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', value):
                resource = digest([source, scope, 's3_bucket', value])
            else:
                issue = 'missing_required_resource'
        elif (service, action) not in {('s3.amazonaws.com', 'ListBuckets'), ('sts.amazonaws.com', 'GetCallerIdentity'), ('signin.amazonaws.com', 'ConsoleLogin')}:
            issue = 'unsupported_service_resource_semantics'
        action = service + ':' + action
    return Event(source, scope, account, native, instant(row['timestamp']), action, resource, payload, issue)


class Day:
    def __init__(self):
        self.key = None
        self.references, self.actions, self.resources = {}, set(), set()
        self.count, self.off = 0, 0
        self.issues = Counter()

    def add(self, event):
        key = event.source, event.scope, event.account, event.day
        if self.key is not None and self.key != key:
            raise ValueError('Cannot mix accounts, sources, scopes or days')
        self.key = key
        if event.reference in self.references:
            if self.references[event.reference] != event.payload_digest:
                raise ValueError('Conflicting native event ID')
            return False
        self.references[event.reference] = event.payload_digest
        self.count += 1; self.off += event.off_hours
        if event.issue:
            self.issues[event.issue] += 1
        if event.issue not in {'unknown_action', 'native_action_missing_or_default_ambiguous'}:
            self.actions.add(event.action)
        if event.resource is not None:
            self.resources.add(event.resource)
        return True

    def features(self, prior_actions):
        if not self.count:
            raise ValueError('No fabricated idle-day vectors')
        return dict(zip(FEATURES, [self.count, len(self.actions), len(self.resources),
                                  self.off / self.count, len(self.actions - prior_actions)]))


class History:
    def __init__(self):
        self.state = {}

    def snapshot(self, day):
        if not day.key:
            raise ValueError('Observed day required')
        source, scope, account, date = day.key
        count, actions, last = self.state.get((source, scope, account), (0, frozenset(), None))
        if last is not None and date <= last:
            raise ValueError('History must advance by closed day')
        eligible = count >= K and not day.issues
        return {'prior_active_days': count, 'eligible': eligible,
                'features': day.features(actions) if eligible else None,
                'issues': dict(day.issues), 'cold_start': count < K}

    def commit_original(self, day):
        self.snapshot(day)  # validates chronology, even when the day is unscorable
        source, scope, account, date = day.key
        count, actions, _ = self.state.get((source, scope, account), (0, frozenset(), None))
        self.state[source, scope, account] = (count + 1, actions | day.actions, date)
