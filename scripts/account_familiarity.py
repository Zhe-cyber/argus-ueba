"""Fixed fitting-only incidence contrast. Offline companion, not an AE or live scorer."""
from collections import Counter
from dataclasses import dataclass
from datetime import date
import math
import re
from types import MappingProxyType

from scripts.personal_baseline import document_digest, exact_date, quantile_linear

METHOD = 'clue_account_affinity_v1'
DIMENSIONS = ('resources', 'actions')
MIN_DATES = 5
SHRINKAGE = 5


def checked(rows, start=None, end=None):
    if start is not None:
        exact_date(start)
        exact_date(end)
        if start > end:
            raise ValueError('Invalid row window')
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('user'), str) or not row['user'] or len(row['user']) > 256:
            raise ValueError('Invalid account')
        day = exact_date(row.get('date'))
        key = row['user'], day
        if key in seen or (start is not None and not start <= day <= end):
            raise ValueError('Duplicate row or row outside window')
        if row.get('capture_boundary') is not False:
            raise ValueError('Partial/unknown capture boundary')
        seen.add(key)
        for field in ('event_count', 'path_event_count'):
            if type(row.get(field)) is not int or row[field] < (1 if field == 'event_count' else 0):
                raise ValueError('Invalid event coverage')
        if row['path_event_count'] > row['event_count']:
            raise ValueError('Path event coverage exceeds events')
        for dim in DIMENSIONS:
            values = row.get(dim)
            if (not isinstance(values, list)
                    or any(not isinstance(t, str) or re.fullmatch('[0-9a-f]{64}', t) is None for t in values)
                    or values != sorted(set(values))):
                raise ValueError('Require sorted distinct hashed tokens')
        if (not row['actions'] or len(row['actions']) > row['event_count']
                or len(row['resources']) > row['path_event_count']
                or bool(row['resources']) != bool(row['path_event_count'])):
            raise ValueError('Token/event coverage differs')
        coverage = row.get('coverage')
        keys = {'invalid_resource_events', 'missing_required_paths', 'unknown_action_events'}
        if (not isinstance(coverage, dict) or set(coverage) != keys
                or any(type(v) is not int or not 0 <= v <= row['event_count'] for v in coverage.values())):
            raise ValueError('Invalid resource/action coverage')
        result.append(row)
    return sorted(result, key=lambda r: (r['date'], r['user']))


@dataclass(frozen=True)
class Dimension:
    days: object
    counts: object
    pooled: object
    total_days: int


@dataclass(frozen=True)
class Reference:
    start: str
    end: str
    rows_digest: str
    dimensions: object

    def document(self):
        return {'method': METHOD, 'schema_version': 1, 'resource_contract': 'resource_observability_v1',
                'min_fitting_dates': MIN_DATES, 'shrinkage_dates': SHRINKAGE,
                'fit_start': self.start, 'fit_end': self.end, 'fit_rows_sha256': self.rows_digest,
                'status': 'development_only', 'activated': False,
                'dimensions': {dim: {'days': dict(d.days), 'counts': {u: dict(c) for u, c in d.counts.items()}}
                               for dim, d in self.dimensions.items()}}


def load_reference(doc):
    if (doc.get('method') != METHOD or doc.get('schema_version') != 1
            or doc.get('resource_contract') != 'resource_observability_v1'
            or doc.get('min_fitting_dates') != MIN_DATES or doc.get('shrinkage_dates') != SHRINKAGE
            or doc.get('status') != 'development_only' or doc.get('activated') is not False):
        raise ValueError('Wrong familiarity contract')
    start, end = exact_date(doc['fit_start']), exact_date(doc['fit_end'])
    digest = doc['fit_rows_sha256']
    if start > end or not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None:
        raise ValueError('Invalid reference dates/digest')
    dims, accounts = {}, None
    supplied = doc['dimensions']
    if not isinstance(supplied, dict) or set(supplied) != set(DIMENSIONS):
        raise ValueError('Wrong dimensions')
    max_dates = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    for dim in DIMENSIONS:
        days, counts = supplied[dim]['days'], supplied[dim]['counts']
        if (not isinstance(days, dict) or not days or not isinstance(counts, dict) or set(days) != set(counts)
                or len(days) > 10_000 or (accounts is not None and set(days) != accounts)):
            raise ValueError('Inconsistent fitting population')
        accounts = set(days)
        pooled, immutable = Counter(), {}
        for user, n in days.items():
            values = counts[user]
            if (not isinstance(user, str) or not user or len(user) > 256 or type(n) is not int
                    or not 0 <= n <= max_dates or not isinstance(values, dict) or bool(n) != bool(values)
                    or any(not isinstance(t, str) or re.fullmatch('[0-9a-f]{64}', t) is None
                           or type(k) is not int or not 1 <= k <= n for t, k in values.items())):
                raise ValueError('Invalid daily incidence counts')
            if sum(values.values()) < n:
                raise ValueError('Usable dates exceed token incidences')
            pooled.update(values)
            immutable[user] = MappingProxyType(dict(values))
        dims[dim] = Dimension(MappingProxyType(dict(days)), MappingProxyType(immutable),
                              MappingProxyType(dict(pooled)), sum(days.values()))
    return Reference(start, end, digest, MappingProxyType(dims))


def fit(rows, start, end):
    rows = checked(rows, start, end)
    if not rows or any(any(r['coverage'].values()) for r in rows):
        raise ValueError('Empty or unresolved fitting coverage')
    users = sorted({r['user'] for r in rows})
    dims = {}
    for dim in DIMENSIONS:
        days, counts = dict.fromkeys(users, 0), {u: Counter() for u in users}
        for row in rows:
            if row[dim]:
                days[row['user']] += 1
                counts[row['user']].update(row[dim])
        dims[dim] = {'days': days, 'counts': {u: dict(c) for u, c in counts.items()}}
    return load_reference({'method': METHOD, 'schema_version': 1, 'resource_contract': 'resource_observability_v1',
                           'min_fitting_dates': MIN_DATES, 'shrinkage_dates': SHRINKAGE,
                           'fit_start': start, 'fit_end': end, 'fit_rows_sha256': document_digest(rows),
                           'status': 'development_only', 'activated': False, 'dimensions': dims})


def score(reference, row):
    checked([row])
    if row['date'] <= reference.end:
        raise ValueError('Score must follow fitting')
    result = {'scores': {}, 'statuses': {}, 'dimensions': {}}
    for dim, model in reference.dimensions.items():
        known = [t for t in row[dim] if t in model.pooled]
        user = row['user']
        stats = {'distinct_tokens': len(row[dim]), 'fitting_known_tokens': len(known),
                 'globally_unseen_tokens': len(row[dim]) - len(known),
                 'globally_unseen_fraction': (len(row[dim]) - len(known)) / len(row[dim]) if row[dim] else None,
                 'fitting_usable_dates': model.days.get(user, 0), 'contrast': None}
        if user not in model.days:
            status = 'unknown_account'
        elif any(row['coverage'].values()):
            status = 'unresolved_event_coverage'
        elif model.days[user] < MIN_DATES:
            status = 'insufficient_fitting_dates'
        elif not known:
            status = 'no_fitting_known_tokens'
        else:
            values = []
            for t in known:
                pooled = (model.pooled[t] + 1) / (model.total_days + 2)
                personal = (model.counts[user].get(t, 0) + SHRINKAGE * pooled) / (model.days[user] + SHRINKAGE)
                values.append(max(0.0, math.log(pooled / personal)))
            stats['contrast'] = math.fsum(values) / len(values)
            stats['known_tokens_unseen_by_account'] = sum(t not in model.counts[user] for t in known)
            status = 'ready'
        stats['status'] = status
        result['dimensions'][dim] = stats
    r, a = result['dimensions']['resources'], result['dimensions']['actions']
    result['scores']['resource'] = r['contrast']
    result['statuses']['resource'] = r['status']
    ready = r['status'] == a['status'] == 'ready'
    result['scores']['joint'] = max(r['contrast'], a['contrast']) if ready else None
    result['statuses']['joint'] = 'ready' if ready else 'required_dimension_unavailable'
    return result


def calibrate(reference, rows, start, end):
    rows = checked(rows, start, end)
    if start <= reference.end:
        raise ValueError('Calibration overlaps fitting')
    scored = [(row, score(reference, row)) for row in rows]
    result = {}
    for mode in ('resource', 'joint'):
        valid = [(r, s['scores'][mode]) for r, s in scored if s['scores'][mode] is not None]
        values = [v for _, v in valid]
        accounts = len({r['user'] for r, _ in valid})
        if len(values) < 6 or accounts < 3:
            raise ValueError('Require six calibration rows across three accounts')
        threshold = quantile_linear(values)
        result[mode] = {'threshold': threshold, 'quantile': .99, 'quantile_method': 'linear',
                        'boundary_rule': 'strictly_greater', 'rows': len(rows), 'scored_rows': len(values),
                        'unavailable_rows': len(rows) - len(values), 'scored_accounts': accounts,
                        'normal_calibration_alerts': sum(v > threshold for v in values),
                        'degenerate_calibration': min(values) == max(values),
                        'reference_sha256': document_digest(reference.document()),
                        'rows_sha256': document_digest(rows), 'start': start, 'end': end}
    return result
