"""Separate period-aware projection; frozen W8 diagnostic exporter stays unchanged."""
from collections import Counter
import hashlib

from scripts.clue_features import KNOWN_ACTIONS, REQUIRED_PATH, instant
from scripts.context_feature_diagnostic import parent_category
from scripts.personal_baseline import exact_date
from scripts.resource_observability import resource, token


def project(events, population, start, end):
    exact_date(start)
    exact_date(end)
    if start > end:
        raise ValueError('Invalid period')
    windows, first, last, memberships = {}, None, None, 0
    for event in events:
        day = instant(event['time']).date().isoformat()
        first, last = min(first, day) if first else day, max(last, day) if last else day
        if event['uidType'] != 'name' or not start <= day <= end:
            continue
        user = hashlib.sha256(('clue-7119953:' + event['uid']).encode()).hexdigest()
        if user not in population:
            continue
        key = user, day
        if key not in windows:
            if len(windows) >= 200_000:
                raise ValueError('Account-day bound exceeded')
            windows[key] = {'user': user, 'date': day, 'event_count': 0, 'paths': {}, 'actions': Counter(),
                            'coverage': dict.fromkeys(('invalid_resource_events', 'missing_required_paths', 'unknown_action_events'), 0)}
        row = windows[key]
        action = event.get('type')
        if not isinstance(action, str) or not action or len(action) > 128:
            raise ValueError('Invalid action')
        row['event_count'] += 1
        row['actions'][token('clue-7119953', 'action', action)] += 1
        row['coverage']['unknown_action_events'] += action not in KNOWN_ACTIONS
        item, params = resource('clue-7119953', event), event.get('params', {})
        row['coverage']['invalid_resource_events'] += not isinstance(params, dict) or ('path' in params and item.object is None)
        row['coverage']['missing_required_paths'] += action in REQUIRED_PATH and item.object is None
        if item.object is not None and item.object not in row['paths']:
            row['paths'][item.object] = tuple(parent_category(params['path'], depth) for depth in (1, 2))
            memberships += 1
            if memberships > 4_000_000:
                raise ValueError('Membership bound exceeded')
    if first is None or first >= start or last <= end:
        raise ValueError('Period intersects native capture boundary')
    return [{'user': w['user'], 'date': w['date'], 'event_count': w['event_count'], 'distinct_paths': len(w['paths']),
             'coverage': w['coverage'], 'views': {'action_mix': dict(w['actions']),
                 **{view: dict(Counter(pair[j] for pair in w['paths'].values()))
                    for j, view in enumerate(('parent_depth1', 'parent_depth2'))}}}
            for _, w in sorted(windows.items())]
