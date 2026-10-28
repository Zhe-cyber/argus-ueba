"""Normal-only feature separation. No anomaly threshold or runtime registration."""
from collections import Counter, defaultdict
from dataclasses import dataclass
import math
import re
from statistics import median
from types import MappingProxyType

from scripts.personal_baseline import exact_date, document_digest
from scripts.resource_observability import token

VIEWS = ('action_mix', 'parent_depth1', 'parent_depth2')
METHOD = 'clue_context_diagnostic_v1'
TOL = 1e-12


def parent_category(path, depth):
    if not isinstance(path, str) or not path or depth not in (1, 2):
        raise ValueError('Require a literal path and fixed context depth')
    parents = [part for part in path.split('/') if part][:-1]
    return token('clue-7119953', 'parent_proxy', depth, parents[:depth])


def distribution(counts):
    if (not isinstance(counts, dict) or not counts
            or any(not isinstance(k, str) or re.fullmatch('[0-9a-f]{64}', k) is None
                   or type(v) is not int or v <= 0 for k, v in counts.items())):
        raise ValueError('Require nonempty positive integer category counts')
    total = sum(counts.values())
    return {k: v / total for k, v in counts.items()}


def js(left, right):
    for values in (left, right):
        if (not values or any(isinstance(p, bool) or not isinstance(p, (int, float))
                              or not math.isfinite(p) or p <= 0 for p in values.values())
                or not math.isclose(math.fsum(values.values()), 1, rel_tol=0, abs_tol=TOL)):
            raise ValueError('Require nonempty probability distributions')
    pieces = []
    for key in sorted(set(left) | set(right)):
        p, q = left.get(key, 0), right.get(key, 0)
        if p:
            pieces.append(.5 * p * math.log2(2 * p / (p + q)))
        if q:
            pieces.append(.5 * q * math.log2(2 * q / (p + q)))
    value = math.fsum(pieces)
    if value < -TOL or value > 1 + TOL:
        raise ValueError('JS divergence outside mathematical range')
    return min(1.0, max(0.0, value))


def checked(rows, start, end):
    rows = list(rows)
    exact_date(start)
    exact_date(end)
    if start > end:
        raise ValueError('Invalid date window')
    seen = set()
    for row in rows:
        if not isinstance(row.get('user'), str) or not row['user'] or len(row['user']) > 256:
            raise ValueError('Invalid account')
        day = exact_date(row['date'])
        key = row['user'], day
        if key in seen or not start <= day <= end:
            raise ValueError('Duplicate/out-of-window account-day')
        seen.add(key)
        if (type(row.get('event_count')) is not int or row['event_count'] < 1
                or type(row.get('distinct_paths')) is not int or not 0 <= row['distinct_paths'] <= row['event_count']):
            raise ValueError('Invalid event/path counts')
        coverage = row.get('coverage')
        if (not isinstance(coverage, dict)
                or set(coverage) != {'invalid_resource_events', 'missing_required_paths', 'unknown_action_events'}
                or any(type(v) is not int or not 0 <= v <= row['event_count'] for v in coverage.values())):
            raise ValueError('Invalid coverage')
        if not isinstance(row.get('views'), dict) or set(row['views']) != set(VIEWS):
            raise ValueError('Wrong view contract')
        for view in VIEWS:
            values = row['views'][view]
            expected = row['event_count'] if view == 'action_mix' else row['distinct_paths']
            if (not isinstance(values, dict) or any(type(v) is not int or v <= 0 for v in values.values())
                    or sum(values.values()) != expected):
                raise ValueError('Category/event counts differ')
            if values:
                distribution(values)
    return sorted(rows, key=lambda r: (r['date'], r['user']))


@dataclass(frozen=True)
class Reference:
    start: str
    end: str
    digest: str
    centres: object
    days: object
    vocabulary: object

    def document(self):
        return {'method': METHOD, 'fit_start': self.start, 'fit_end': self.end, 'fit_rows_sha256': self.digest,
                'min_fitting_dates': 5, 'distance': 'base2_JS_divergence', 'day_weighting': 'equal',
                'centres': {view: {u: dict(p) for u, p in centres.items()} for view, centres in self.centres.items()},
                'usable_fitting_dates': {view: dict(counts) for view, counts in self.days.items()},
                'full_fitting_vocabulary': {view: sorted(values) for view, values in self.vocabulary.items()},
                'status': 'exploratory_normal_separation_only', 'activated': False}


def fit(rows, start, end):
    rows = checked(rows, start, end)
    if not rows or any(any(r['coverage'].values()) for r in rows):
        raise ValueError('Empty/unresolved fitting data')
    users = sorted({r['user'] for r in rows})
    centres, days, vocabulary = {}, {}, {}
    for view in VIEWS:
        profiles = {u: [] for u in users}
        for row in rows:
            if row['views'][view]:
                profiles[row['user']].append(distribution(row['views'][view]))
        values = {}
        for user, daily in profiles.items():
            if len(daily) >= 5:
                keys = set().union(*(p.keys() for p in daily))
                values[user] = MappingProxyType({t: math.fsum(p.get(t, 0) for p in daily) / len(daily) for t in sorted(keys)})
        centres[view] = MappingProxyType(values)
        days[view] = MappingProxyType({u: len(d) for u, d in profiles.items()})
        vocabulary[view] = frozenset(t for daily in profiles.values() for p in daily for t in p)
    return Reference(start, end, document_digest(rows), MappingProxyType(centres), MappingProxyType(days), MappingProxyType(vocabulary))


def compare(reference, rows, start, end):
    rows = checked(rows, start, end)
    if start <= reference.end:
        raise ValueError('Diagnostic dates must follow fitting')
    result = {view: [] for view in VIEWS}
    for view in VIEWS:
        centres = reference.centres[view]
        vocabulary = reference.vocabulary[view]
        for row in rows:
            record = {'user': row['user'], 'date': row['date']}
            if any(row['coverage'].values()):
                status = 'unresolved_event_coverage'
            elif not row['views'][view]:
                status = 'no_resource_activity'
            elif row['user'] not in centres:
                status = 'insufficient_or_unknown_fitting_history'
            elif len(centres) < 4:
                status = 'fewer_than_three_other_references'
            else:
                query = distribution(row['views'][view])
                own = js(query, centres[row['user']])
                others = [js(query, p) for u, p in centres.items() if u != row['user']]
                other_median, best = median(others), min([own, *others])
                nearest_count = sum(abs(v - best) <= TOL for v in [own, *others])
                record.update(own_distance=own, median_other_distance=other_median,
                              median_other_minus_own=other_median - own,
                              own_closer_than_median=other_median - own > TOL,
                              tied_with_median=abs(other_median - own) <= TOL,
                              own_uniquely_nearest=own - best <= TOL and nearest_count == 1,
                              own_tied_for_nearest=abs(own - best) <= TOL and nearest_count > 1,
                              globally_unseen_category_mass=math.fsum(p for t, p in query.items() if t not in vocabulary),
                              no_overlap_with_own=not bool(set(query) & set(centres[row['user']])))
                status = 'ready'
            record['status'] = status
            result[view].append(record)
    return result


def summarize(records):
    if len({(r['user'], r['date']) for r in records}) != len(records):
        raise ValueError('Duplicate diagnostic rows')
    ready = [r for r in records if r['status'] == 'ready']
    per_account = defaultdict(list)
    for row in ready:
        per_account[row['user']].append(row['own_closer_than_median'])
    return {'original_rows': len(records), 'comparable_rows': len(ready), 'comparable_accounts': len(per_account),
            'status_counts': dict(sorted(Counter(r['status'] for r in records).items())),
            'own_closer_than_median_other': sum(r['own_closer_than_median'] for r in ready),
            'tied_with_median_other': sum(r['tied_with_median'] for r in ready),
            'own_farther_than_median_other': sum(not r['own_closer_than_median'] and not r['tied_with_median'] for r in ready),
            'own_uniquely_nearest': sum(r['own_uniquely_nearest'] for r in ready),
            'own_tied_for_nearest': sum(r['own_tied_for_nearest'] for r in ready),
            'own_no_category_overlap': sum(r['no_overlap_with_own'] for r in ready),
            'median_own_distance': median(r['own_distance'] for r in ready) if ready else None,
            'median_other_minus_own': median(r['median_other_minus_own'] for r in ready) if ready else None,
            'median_globally_unseen_category_mass': median(r['globally_unseen_category_mass'] for r in ready) if ready else None,
            'equal_account_mean_own_closer_fraction': math.fsum(sum(v) / len(v) for v in per_account.values()) / len(per_account) if per_account else None}
