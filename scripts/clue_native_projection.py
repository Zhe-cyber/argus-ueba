"""Separate native CLUE projection adapter; frozen extractor remains unchanged."""
from collections import defaultdict
from datetime import date
import hashlib

from scripts.clue_features import Window, instant


def project_rows(events, swap=None, switch_day=None):
    swap = swap or {}
    if not isinstance(swap, dict) or any(not isinstance(v, str) for v in swap.values()):
        raise ValueError('Require a reciprocal mapping')
    if swap:
        if (len(swap) != 2 or any(not isinstance(u, str) or not u for u in swap)
                or any(other == user or swap.get(other) != user for user, other in swap.items())
                or not isinstance(switch_day, str) or date.fromisoformat(switch_day).isoformat() != switch_day):
            raise ValueError('Require a reciprocal pair and exact switch date')
    elif switch_day is not None:
        raise ValueError('Switch date without a pair')
    windows, first, last, count = defaultdict(dict), None, None, 0
    for event in events:
        day = instant(event['time']).date().isoformat()
        first, last = min(first, day) if first else day, max(last, day) if last else day
        if event['uidType'] != 'name':
            continue
        actor = hashlib.sha256(('clue-7119953:' + event['uid']).encode()).hexdigest()
        account = swap.get(actor, actor) if swap and day >= switch_day else actor
        if account not in windows and len(windows) >= 10_000:
            raise ValueError('Identity bound exceeded')
        if day not in windows[account]:
            count += 1
            if count > 200_000:
                raise ValueError('Account-day bound exceeded')
            windows[account][day] = Window()
        windows[account][day].add(event)
    rows = []
    for user, days in sorted(windows.items()):
        prior, history_days = set(), 0
        for day, window in sorted(days.items()):
            rows.append({'user': user, 'date': day, 'capture_boundary': day in (first, last),
                         'history_days': history_days,
                         'coverage': {'path_events': window.path_events, 'missing_required_paths': window.missing_required_paths,
                                      'unknown_action_events': window.unknown_actions},
                         'features': window.finish(prior)})
            prior.update(window.actions)
            history_days += 1
    return rows
