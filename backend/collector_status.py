"""Read-only, sanitized local collector receipts. Event totals never imply health."""
from datetime import datetime, timezone
import json
from pathlib import Path

MAX_STATUS_BYTES = 65536
STATES = {'claimed_unknown','api_ok_identity_pending','api_ok_activity_pending',
          'api_ok_log_pending','response_error_log_pending','api_ok_audit_pending',
          'provider_verified','missed'}


def read_status(path):
    try:
        with Path(path).open('rb') as source:
            raw = source.read(MAX_STATUS_BYTES + 1)
        if len(raw) > MAX_STATUS_BYTES:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, RecursionError):
        return None


def snapshot(value, now, max_age, phase=None):
    unknown = {'status': 'unavailable', 'last_checked_at': None}
    if not isinstance(value, dict):
        return unknown
    try:
        at = datetime.fromisoformat(value['at_utc'].replace('Z', '+00:00'))
        if at.tzinfo is None:
            return unknown
        age = (now - at).total_seconds()
        if age < -60:
            return unknown
    except (KeyError, ValueError, TypeError, AttributeError):
        return unknown
    states = value.get('action_states', {})
    if not isinstance(states, dict) or any(k not in STATES or type(n) is not int or n < 0 for k, n in states.items()):
        return unknown
    unresolved = states.get('claimed_unknown', 0) + states.get('api_ok_identity_pending', 0)
    direct_unknown = value.get('unknown_claims', 0)
    if type(direct_unknown) is not int or direct_unknown < 0:
        return unknown
    unresolved = max(unresolved, direct_unknown)
    result = {'status': 'unavailable', 'last_checked_at': at.astimezone(timezone.utc).isoformat(),
              'unresolved': unresolved, 'missed': states.get('missed', 0),
              'pending_receipts': sum(states.get(k, 0) for k in ['api_ok_activity_pending','api_ok_log_pending','response_error_log_pending','api_ok_audit_pending'])}
    if age > max_age:
        result['status'] = 'stale'
    elif value.get('status') == 'expired':
        result['status'] = 'ended'
    elif unresolved or value.get('status') in {'attention_required','stopped','stopped_review_required'} or phase is False:
        result['status'] = 'attention'
    elif phase is True or value.get('status') == 'completed':
        result['status'] = 'recent'
    return result


def summaries(connected_dir, source_root, now=None):
    now = now or datetime.now(timezone.utc)
    shared = read_status(Path(connected_dir).parent / 'pilot-local-v1/last_tick.json')
    phases = shared.get('phases', {}) if isinstance(shared, dict) else {}
    if not isinstance(phases, dict):
        phases = {}
    result = {}
    for source, phase_name in [('aws_cloudtrail','aws'),('github_events','github'),('cloudflare_access','cloudflare')]:
        phase = phases.get(phase_name, {})
        ok = phase.get('ok') if isinstance(phase, dict) else None
        collector_value = dict(shared or {})
        # A completed outer tick with missing phase evidence is never a green check.
        collector_value['status'] = 'phase_snapshot'
        result[source] = {'collector': snapshot(collector_value, now, 15 * 60, phase=ok)}
    actors = phases.get('actors', {})
    if isinstance(actors, dict):
        actors = {**actors, 'at_utc': (shared or {}).get('at_utc'), 'status': 'phase_snapshot'}
        result['aws_cloudtrail']['workload'] = snapshot(actors, now, 15 * 60, phase=actors.get('ok'))
    for source, folder, age in [('cloudflare_access','cloudflare-workload-lab-v1',15*60),
                                ('github_events','github-app-lab-v1',35*60)]:
        result[source]['workload'] = snapshot(read_status(Path(source_root)/'data/live'/folder/'last-pilot-status.json'),now,age)
    return result
