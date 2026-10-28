"""Separate CLUE daily sets for familiarity. Does not change the frozen extractor."""
from datetime import date
import hashlib

from scripts.clue_features import KNOWN_ACTIONS, REQUIRED_PATH, instant
from scripts.resource_observability import resource, token


def project(events, swap=None, switch_day=None):
    if swap is None:
        swap = {}
    if not isinstance(swap, dict):
        raise ValueError('Require a reciprocal mapping')
    if swap:
        if (len(swap) != 2 or any(not isinstance(u, str) or not u for u in swap)
                or any(not isinstance(v, str) or v == u or swap.get(v) != u for u, v in swap.items())
                or not isinstance(switch_day, str) or date.fromisoformat(switch_day).isoformat() != switch_day):
            raise ValueError('Require a reciprocal pair and exact date')
    elif switch_day is not None:
        raise ValueError('Switch date without a pair')
    windows, first, last, memberships = {}, None, None, 0
    for event in events:
        day = instant(event['time']).date().isoformat()
        first, last = min(first, day) if first else day, max(last, day) if last else day
        if event['uidType'] != 'name':
            continue
        user = hashlib.sha256(('clue-7119953:' + event['uid']).encode()).hexdigest()
        if swap and day >= switch_day:
            user = swap.get(user, user)
        key = user, day
        if key not in windows:
            if len(windows) >= 200_000:
                raise ValueError('Account-day bound exceeded')
            windows[key] = {'user': user, 'date': day, 'event_count': 0, 'path_event_count': 0,
                            'resources': set(), 'actions': set(),
                            'coverage': {'invalid_resource_events': 0, 'missing_required_paths': 0,
                                         'unknown_action_events': 0}}
        row = windows[key]
        action = event.get('type')
        if not isinstance(action, str) or not action or len(action) > 128:
            raise ValueError('Invalid native action')
        row['event_count'] += 1
        action_token = token('clue-7119953', 'action', action)
        before = len(row['actions']) + len(row['resources'])
        row['actions'].add(action_token)
        row['coverage']['unknown_action_events'] += action not in KNOWN_ACTIONS
        item = resource('clue-7119953', event)
        params = event.get('params', {})
        supplied_invalid = not isinstance(params, dict) or ('path' in params and item.object is None)
        row['coverage']['invalid_resource_events'] += supplied_invalid
        row['coverage']['missing_required_paths'] += action in REQUIRED_PATH and item.object is None
        if item.object is not None:
            row['path_event_count'] += 1
            row['resources'].add(item.object)
        memberships += len(row['actions']) + len(row['resources']) - before
        if memberships > 4_000_000:
            raise ValueError('Token membership bound exceeded')
    rows = []
    for _, row in sorted(windows.items()):
        row['resources'], row['actions'] = sorted(row['resources']), sorted(row['actions'])
        row['capture_boundary'] = row['date'] in (first, last)
        rows.append(row)
    return rows
