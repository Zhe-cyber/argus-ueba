"""Native repository-activity projection for live diagnostics only.

No ingestion, provider calls or changes to the frozen Events API label mapping.
Repository-activity kinds retain a separate namespace; a push does not imply a
known number of commits, an audit event, a human actor or a successful login.
"""
from dataclasses import replace
import json
import re

from scripts import shared_core_features as frozen

PROFILE = 'github_repository_activity_projection_v1'
FORMAT = 'github_repository_activity_v1'
LABELS = {'push': 'Repository push', 'force_push': 'Repository force push',
          'branch_creation': 'Repository branch creation', 'branch_deletion': 'Repository branch deletion',
          'pr_merge': 'Repository PR merge', 'merge_queue_merge': 'Repository merge queue merge'}


def metadata(row):
    value = row.get('metadata') or {}
    value = json.loads(value) if isinstance(value, str) else value
    if not isinstance(value, dict):
        raise ValueError('Native activity metadata must be an object')
    return value


def claims_repository_activity(row):
    if row.get('source') != 'github_events':
        return False
    meta = metadata(row)
    return (meta.get('evidence_format') == FORMAT
            or str(row.get('event_id', '')).startswith('repository-activity:')
            or str(row.get('action', '')).startswith('Repository '))


def project(row):
    """Return a frozen Event with validated live native kind, or an explicit issue."""
    if row.get('source') != 'github_events':
        raise ValueError('GitHub source required')
    event = frozen.project_live(row)  # Preserve shared identity/day/resource/provenance checks.
    meta = metadata(row)
    if not meta.get('evidence_format'):
        return replace(event, issue='unknown_action')  # Display label alone remains unsupported.
    if (meta.get('evidence_format') != FORMAT
            or meta.get('provider_endpoint') != 'repository_activity'
            or meta.get('provider_api_version') != '2022-11-28'
            or meta.get('repository_context_basis') != 'collector_verified_request'):
        return replace(event, issue='unsupported_native_activity_provenance')
    kind = meta.get('activity_type')
    if not isinstance(kind, str) or kind not in LABELS:
        return replace(event, issue='unknown_action')
    if row['action'] != LABELS[kind]:
        return replace(event, issue='native_activity_label_mismatch')
    repo, activity, actor = (meta.get(k) for k in ('repository_id', 'native_activity_id', 'actor_id'))
    if (any(type(n) is not int or n <= 0 for n in (repo, activity, actor))
            or row['event_id'] != f'repository-activity:{repo}:{activity}'
            or not re.fullmatch(r'github-owner:[1-9][0-9]*', row['source_account_id'])):
        return replace(event, issue='native_activity_identity_mismatch')
    if (any(not isinstance(meta.get(k), str) or not re.fullmatch(r'[0-9a-f]{40}', meta[k])
            for k in ('before', 'after'))
            or not isinstance(meta.get('ref'), str) or not meta['ref'].startswith('refs/')):
        return replace(event, issue='invalid_native_activity_reference')
    resource = row.get('resource')
    if (not isinstance(resource, str)
            or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', resource)
            or any(part in {'.', '..'} for part in resource.split('/'))):
        return replace(event, issue='missing_required_resource')
    return replace(event, action='repository_activity:' + kind, issue=None)
