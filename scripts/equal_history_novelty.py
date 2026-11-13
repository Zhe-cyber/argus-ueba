"""Fixed-five-resource-date novelty: offline calibration gate, not a live model."""
from dataclasses import dataclass
from datetime import date
import re
from types import MappingProxyType

from scripts.account_familiarity import checked
from scripts.personal_baseline import document_digest, exact_date, quantile_linear

METHOD = 'clue_resource_novelty_fixed5_v2'
K = 5


def tokens(values):
    if (not isinstance(values, list)
            or any(not isinstance(t, str) or re.fullmatch('[0-9a-f]{64}', t) is None for t in values)
            or values != sorted(set(values))):
        raise ValueError('Invalid distinct resource tokens')
    return frozenset(values)


@dataclass(frozen=True)
class Reference:
    start: str
    end: str
    rows_digest: str
    fitting_dates: object
    selected_dates: object
    personal: object
    global_resources: frozenset

    def document(self):
        return {'schema_version': 1, 'method': METHOD, 'reference_dates': K,
                'fit_start': self.start, 'fit_end': self.end, 'fit_rows_sha256': self.rows_digest,
                'fitting_resource_dates': dict(self.fitting_dates),
                'selected_dates': {u: list(days) for u, days in self.selected_dates.items()},
                'personal_resources': {u: sorted(values) for u, values in self.personal.items()},
                'global_full_fit_resources': sorted(self.global_resources),
                'status': 'development_only', 'activated': False}


def load_reference(doc):
    if (doc.get('schema_version') != 1 or doc.get('method') != METHOD or doc.get('reference_dates') != K
            or doc.get('status') != 'development_only' or doc.get('activated') is not False):
        raise ValueError('Wrong fixed-history contract')
    start, end = exact_date(doc['fit_start']), exact_date(doc['fit_end'])
    digest = doc['fit_rows_sha256']
    if start > end or not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None:
        raise ValueError('Invalid fitting dates/digest')
    counts, selected, personal = doc['fitting_resource_dates'], doc['selected_dates'], doc['personal_resources']
    max_days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    if (not isinstance(counts, dict) or not counts or len(counts) > 10_000
            or any(not isinstance(u, str) or not u or len(u) > 256 or type(n) is not int or not 0 <= n <= max_days
                   for u, n in counts.items()) or not isinstance(selected, dict) or not isinstance(personal, dict)):
        raise ValueError('Invalid population')
    eligible = {u for u, n in counts.items() if n >= K}
    if set(selected) != eligible or set(personal) != eligible:
        raise ValueError('Eligibility differs from fitting counts')
    global_resources = tokens(doc['global_full_fit_resources'])
    frozen_dates, frozen_resources = {}, {}
    for user in sorted(eligible):
        days = selected[user]
        if (not isinstance(days, list) or len(days) != K or days != sorted(set(days))
                or any(not start <= exact_date(day) <= end for day in days)):
            raise ValueError('Require five distinct fitting dates')
        resources = tokens(personal[user])
        if not resources or not resources <= global_resources:
            raise ValueError('Personal resources absent from global fitting vocabulary')
        frozen_dates[user], frozen_resources[user] = tuple(days), resources
    return Reference(start, end, digest, MappingProxyType(dict(counts)), MappingProxyType(frozen_dates),
                     MappingProxyType(frozen_resources), global_resources)


def fit(rows, start, end):
    rows = checked(rows, start, end)
    if not rows or any(any(r['coverage'].values()) for r in rows):
        raise ValueError('Empty or unresolved fitting data')
    by_user = {u: [] for u in sorted({r['user'] for r in rows})}
    global_resources = set()
    for row in rows:
        global_resources.update(row['resources'])
        if row['resources']:
            by_user[row['user']].append(row)
    selected = {u: dates[-K:] for u, dates in by_user.items() if len(dates) >= K}
    return load_reference({'schema_version': 1, 'method': METHOD, 'reference_dates': K,
                           'fit_start': start, 'fit_end': end, 'fit_rows_sha256': document_digest(rows),
                           'fitting_resource_dates': {u: len(dates) for u, dates in by_user.items()},
                           'selected_dates': {u: [r['date'] for r in dates] for u, dates in selected.items()},
                           'personal_resources': {u: sorted({t for r in dates for t in r['resources']}) for u, dates in selected.items()},
                           'global_full_fit_resources': sorted(global_resources), 'status': 'development_only', 'activated': False})


def score(reference, row):
    checked([row])
    if row['date'] <= reference.end:
        raise ValueError('Scoring must follow fitting')
    resources = frozenset(row['resources'])
    result = {'score': None, 'distinct_resources': len(resources),
              'globally_unseen_fraction': len(resources - reference.global_resources) / len(resources) if resources else None}
    if any(row['coverage'].values()):
        status = 'unresolved_event_coverage'
    elif not resources:
        status = 'no_resource_activity'
    elif row['user'] not in reference.fitting_dates:
        status = 'unknown_account'
    elif row['user'] not in reference.personal:
        status = 'insufficient_fitting_resource_dates'
    else:
        result['score'] = len(resources - reference.personal[row['user']]) / len(resources)
        status = 'ready'
    result['status'] = status
    return result


def calibrate(reference, rows, start, end):
    rows = checked(rows, start, end)
    if start <= reference.end:
        raise ValueError('Calibration overlaps fitting')
    scored = [(r, score(reference, r)) for r in rows]
    valid = [(r, s) for r, s in scored if s['score'] is not None]
    values = [s['score'] for _, s in valid]
    if len(values) < 6 or len({r['user'] for r, _ in valid}) < 3:
        raise ValueError('Require six scorable rows across three accounts')
    threshold = quantile_linear(values)
    return {'method': METHOD, 'threshold': threshold, 'quantile': .99, 'quantile_method': 'linear',
            'boundary_rule': 'strictly_greater', 'rows': len(rows), 'scored_rows': len(values),
            'unscored_rows': len(rows) - len(values), 'scored_accounts': len({r['user'] for r, _ in valid}),
            'normal_calibration_alerts': sum(v > threshold for v in values),
            'exact_threshold_ties': sum(v == threshold for v in values),
            'near_threshold_rows_reporting_only': sum(abs(v - threshold) <= 1e-12 for v in values),
            'gate': 'saturated_no_go' if threshold == 1 else 'development_comparison_pending',
            'switch_evaluation_status': 'not_run', 'reference_sha256': document_digest(reference.document()),
            'rows_sha256': document_digest(rows), 'start': start, 'end': end}
