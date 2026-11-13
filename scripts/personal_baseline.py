"""Offline CLUE numeric reference model. No runtime registration, I/O or training labels.

Population and personal modes differ only in their fitting reference centre.
Shared robust scales prevent sparse per-account variance from deciding the comparison.
"""
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from statistics import median
from types import MappingProxyType

from scripts.clue_features import FEATURES, PROFILE

METHOD = 'clue_numeric_reference_v1'
MIN_FIT_DAYS = 5
MAD_FACTOR = 1.4826
SCALE_FLOOR = 0.25
QUANTILE = 0.99


def exact_date(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError('Require an exact ISO calendar date')
    return value


def document_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def vector(row):
    if not isinstance(row.get('user'), str) or not row['user'] or len(row['user']) > 256:
        raise ValueError('Invalid account')
    exact_date(row.get('date'))
    if row.get('capture_boundary', False):
        raise ValueError('Partial capture dates are not model rows')
    values = row.get('features')
    if not isinstance(values, dict) or set(values) != set(FEATURES):
        raise ValueError('Wrong ten-feature contract')
    for value in values.values():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Features must be finite nonnegative counts')
    if values['event_count'] <= 0:
        raise ValueError('No synthetic idle-day rows')
    coverage = row.get('coverage', {})
    if not isinstance(coverage, dict) or coverage.get('missing_required_paths', 0) or coverage.get('unknown_action_events', 0):
        raise ValueError('Unresolved feature coverage')
    return tuple(math.log1p(values[f]) for f in FEATURES)


def checked_rows(rows, start, end):
    exact_date(start)
    exact_date(end)
    if start > end or not rows:
        raise ValueError('Empty/invalid reference window')
    seen, result = set(), []
    for row in rows:
        values = vector(row)
        key = (row['user'], row['date'])
        if key in seen or not start <= row['date'] <= end:
            raise ValueError('Duplicate row or row outside declared window')
        seen.add(key)
        result.append((row, values))
    return sorted(result, key=lambda item: (item[0]['date'], item[0]['user']))


@dataclass(frozen=True)
class Reference:
    fit_start: str
    fit_end: str
    fit_rows_digest: str
    pooled: tuple
    scales: tuple
    centres: object
    fitting_days: object

    def document(self):
        return {'schema_version': 1, 'method': METHOD, 'input_profile': PROFILE, 'features': list(FEATURES),
                'transform': 'log1p', 'scale_rule': 'max(1.4826*pooled_MAD,0.25)',
                'aggregation': 'mean_absolute_scaled_deviation', 'min_fitting_active_dates': MIN_FIT_DAYS,
                'fit_start': self.fit_start, 'fit_end': self.fit_end, 'fit_rows_sha256': self.fit_rows_digest,
                'pooled_centre': list(self.pooled), 'shared_scales': list(self.scales),
                'personal_centres': {u: list(x) for u, x in sorted(self.centres.items())},
                'fitting_active_dates': dict(sorted(self.fitting_days.items())),
                'status': 'development_only', 'activated': False}


def fit_reference(rows, start, end):
    checked = checked_rows(rows, start, end)
    arrays, accounts = [x for _, x in checked], {}
    for row, values in checked:
        accounts.setdefault(row['user'], []).append(values)
    pooled = tuple(median(x[j] for x in arrays) for j in range(len(FEATURES)))
    scales = tuple(max(MAD_FACTOR * median(abs(x[j] - pooled[j]) for x in arrays), SCALE_FLOOR)
                   for j in range(len(FEATURES)))
    centres = {u: tuple(median(x[j] for x in values) for j in range(len(FEATURES)))
               for u, values in accounts.items() if len(values) >= MIN_FIT_DAYS}
    counts = {u: len(values) for u, values in accounts.items()}
    return Reference(start, end, document_digest([r for r, _ in checked]), pooled, scales,
                     MappingProxyType(centres), MappingProxyType(counts))


def load_reference(document):
    if (document.get('schema_version') != 1 or document.get('method') != METHOD
            or document.get('input_profile') != PROFILE or document.get('features') != FEATURES
            or document.get('transform') != 'log1p' or document.get('scale_rule') != 'max(1.4826*pooled_MAD,0.25)'
            or document.get('aggregation') != 'mean_absolute_scaled_deviation'
            or document.get('min_fitting_active_dates') != MIN_FIT_DAYS
            or document.get('status') != 'development_only' or document.get('activated') is not False):
        raise ValueError('Unsupported offline reference contract')
    start, end = exact_date(document['fit_start']), exact_date(document['fit_end'])
    digest = document['fit_rows_sha256']
    if start > end or not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Invalid reference dates/digest')

    def numbers(value, minimum):
        if (not isinstance(value, list) or len(value) != len(FEATURES)
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < minimum for v in value)):
            raise ValueError('Invalid reference vector')
        return tuple(value)

    counts, centres = document['fitting_active_dates'], document['personal_centres']
    if not isinstance(counts, dict) or not counts or not isinstance(centres, dict):
        raise ValueError('Invalid fitting population')
    if any(not isinstance(u, str) or not u or len(u) > 256 or type(n) is not int or n < 1 for u, n in counts.items()):
        raise ValueError('Invalid fitting counts')
    if set(centres) != {u for u, n in counts.items() if n >= MIN_FIT_DAYS}:
        raise ValueError('Personal eligibility differs from fitting counts')
    return Reference(start, end, digest, numbers(document['pooled_centre'], 0), numbers(document['shared_scales'], SCALE_FLOOR),
                     MappingProxyType({u: numbers(x, 0) for u, x in centres.items()}), MappingProxyType(dict(counts)))


def score(reference, row, personal=True):
    values = vector(row)
    if row['date'] <= reference.fit_end:
        raise ValueError('Scoring must follow the reference fitting window')
    centre = reference.centres.get(row['user']) if personal else reference.pooled
    if centre is None:
        return {'status': 'insufficient_fitting_history' if row['user'] in reference.fitting_days else 'unknown_account',
                'score': None, 'components': []}
    components = [{'feature': feature, 'raw_count': row['features'][feature], 'reference_log1p': centre[j],
                   'shared_scale_log1p': reference.scales[j],
                   'contribution': abs(values[j] - centre[j]) / reference.scales[j] / len(FEATURES)}
                  for j, feature in enumerate(FEATURES)]
    value = math.fsum(c['contribution'] for c in components)
    if not math.isfinite(value):
        raise ValueError('Nonfinite reference score')
    return {'status': 'ready', 'score': value, 'components': components}


def quantile_linear(values, q=QUANTILE):
    if not values or not 0 <= q <= 1 or any(not math.isfinite(v) for v in values):
        raise ValueError('Invalid quantile inputs')
    ordered = sorted(values)
    point = (len(ordered) - 1) * q
    low, high = math.floor(point), math.ceil(point)
    return ordered[low] + (ordered[high] - ordered[low]) * (point - low)


def calibrate(reference, rows, start, end, personal=True):
    checked = checked_rows(rows, start, end)
    if start <= reference.fit_end:
        raise ValueError('Calibration overlaps fitting')
    scored = [(row, score(reference, row, personal)['score']) for row, _ in checked]
    available = [value for _, value in scored if value is not None]
    if len(available) < 6:
        raise ValueError('Require six scorable calibration account-days')
    threshold = quantile_linear(available)
    return {'mode': 'personal' if personal else 'population', 'threshold': threshold,
            'quantile': QUANTILE, 'quantile_method': 'linear', 'boundary_rule': 'strictly_greater',
            'reference_sha256': document_digest(reference.document()), 'start': start, 'end': end,
            'rows': len(checked), 'scored_rows': len(available), 'unavailable_rows': len(checked) - len(available),
            'scored_accounts': len({r['user'] for r, value in scored if value is not None}),
            'normal_calibration_alerts': sum(value > threshold for value in available),
            'degenerate_calibration': max(available) == min(available),
            'rows_sha256': document_digest([r for r, _ in checked])}


def alert(value, threshold):
    if value is None:
        return None
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in (value, threshold)):
        raise ValueError('Invalid score/threshold')
    return value > threshold


def either(left, right):
    if any(value is not None and type(value) is not bool for value in (left, right)):
        raise ValueError('Expected booleans or unavailable')
    if left is True or right is True:
        return True
    return False if left is False and right is False else None
