"""Fixed offline native-event transformations; no model access or cloud actions."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from scripts.shared_core_features import canonical, digest, instant, clue_path, namespace_path

SEED = 42
MAX_DAY_EVENTS = 1_000_000
FAMILIES = {'mass_access', 'off_hours', 'new_action', 'account_switch'}


def rank(family, account, day, reference=''):
    return digest([SEED, family, account, day, str(reference)])


def pairs(population):
    if len(population) != len(set(population)):
        raise ValueError('Population must be unique')
    ordered = sorted(population, key=lambda account: (rank('account_switch', account, ''), account))
    return list(zip(ordered[::2], ordered[1::2]))


def changed(row, family, account, day, ordinal):
    result = deepcopy(row)
    result['id'] = 'sim:' + digest([SEED, family, account, day, row['id'], ordinal])
    result['_argus_scenario'] = family
    return result


def generate(family, rows, account, day, prior_actions, donor=None, target_uid=None):
    if family not in FAMILIES:
        raise ValueError('Unknown scenario')
    if not rows:
        return None, 'no_activity'
    if len(rows) > MAX_DAY_EVENTS:
        return None, 'safety_cap'
    if any(instant(row['time']).date().isoformat() != day for row in rows):
        raise ValueError('Native rows must stay in the declared UTC day')
    if len({row['uid'] for row in rows}) != 1:
        raise ValueError('One target account required')
    base = deepcopy(rows)
    if family == 'mass_access':
        reads = [row for row in rows if row['type'] == 'file_accessed']
        if not reads:
            return None, 'no_file_access'
        if len(rows) + 4 * len(reads) > MAX_DAY_EVENTS:
            return None, 'safety_cap'
        for copy_number in range(4):
            base.extend(changed(row, family, account, day, copy_number) for row in reads)
    elif family == 'off_hours':
        if all(not 7 <= instant(row['time']).hour < 19 for row in rows):
            return None, 'already_entirely_off_hours'
        midnight = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
        ordered = sorted(rows, key=lambda row: (instant(row['time']), str(row['id'])))
        base = []
        for index, row in enumerate(ordered):
            event = changed(row, family, account, day, index)
            # Strict order with microsecond resolution, within 00:00–05:59 UTC.
            offset = (index * (6 * 3600 * 1_000_000 - 1)) // max(len(ordered), 1)
            event['time'] = (midnight + timedelta(microseconds=offset)).isoformat()
            base.append(event)
    elif family == 'new_action':
        if 'permission_changed' in prior_actions:
            return None, 'permission_action_already_seen'
        templates = [row for row in rows if namespace_path(clue_path(row)[0]) is not None and clue_path(row)[1] is None]
        if not templates:
            return None, 'no_resource_template'
        if len(rows) + 5 > MAX_DAY_EVENTS:
            return None, 'safety_cap'
        template = min(templates, key=lambda row: (rank(family, account, day, row['id']), str(row['id'])))
        for index in range(5):
            event = changed(template, family, account, day, index)
            event['type'] = 'permission_changed'
            event['params'] = {'path': clue_path(template)[0]}
            base.append(event)
    else:
        if not donor:
            return None, 'donor_inactive'
        if len(donor) > MAX_DAY_EVENTS:
            return None, 'safety_cap'
        if any(instant(row['time']).date().isoformat() != day for row in donor) or len({row['uid'] for row in donor}) != 1:
            raise ValueError('One donor account on the same UTC day required')
        uid = target_uid or rows[0]['uid']
        base = [changed(row, family, account, day, index) for index, row in enumerate(donor)]
        for event in base:
            event['uid'] = uid
    return base, 'generated'
