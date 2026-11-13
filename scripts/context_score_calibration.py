"""Own-account JS scores and fixed normal-only gates. Offline, not registered live."""
from collections import Counter
from datetime import date
import math
import re
from types import MappingProxyType

from scripts import context_feature_diagnostic as context
from scripts.personal_baseline import exact_date, document_digest, quantile_linear

METHOD = 'clue_context_js_calibration_v1'
MODES = (*context.VIEWS, 'joint_primary')


def token_set(value):
    if (not isinstance(value, list)
            or any(not isinstance(t, str) or re.fullmatch('[0-9a-f]{64}', t) is None for t in value)
            or value != sorted(set(value))):
        raise ValueError('Invalid context vocabulary')
    return frozenset(value)


def load_reference(doc):
    if (doc.get('method') != context.METHOD or doc.get('distance') != 'base2_JS_divergence'
            or doc.get('day_weighting') != 'equal' or type(doc.get('min_fitting_dates')) is not int
            or doc['min_fitting_dates'] != 5 or doc.get('status') != 'exploratory_normal_separation_only'
            or doc.get('activated') is not False):
        raise ValueError('Wrong frozen reference contract')
    start, end = exact_date(doc['fit_start']), exact_date(doc['fit_end'])
    digest = doc['fit_rows_sha256']
    if start > end or not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None:
        raise ValueError('Invalid reference dates/digest')
    supplied, counts, vocabulary = doc['centres'], doc['usable_fitting_dates'], doc['full_fitting_vocabulary']
    if any(not isinstance(v, dict) or set(v) != set(context.VIEWS) for v in (supplied, counts, vocabulary)):
        raise ValueError('Wrong reference views')
    centres, days, vocab, population = {}, {}, {}, None
    max_dates = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    for view in context.VIEWS:
        n, p = counts[view], supplied[view]
        if (not isinstance(n, dict) or not n or len(n) > 10_000 or not isinstance(p, dict)
                or any(not isinstance(u, str) or not u or len(u) > 256 or type(k) is not int or not 0 <= k <= max_dates for u, k in n.items())
                or (population is not None and set(n) != population) or set(p) != {u for u, k in n.items() if k >= 5}):
            raise ValueError('Invalid reference population/eligibility')
        population = set(n)
        vocab[view] = token_set(vocabulary[view])
        own = {}
        for user, probabilities in p.items():
            if (not isinstance(probabilities, dict) or not probabilities or not set(probabilities) <= vocab[view]
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in probabilities.values())):
                raise ValueError('Invalid reference probabilities')
            context.js(probabilities, probabilities)  # Also verifies normalized total mass.
            own[user] = MappingProxyType(dict(probabilities))
        centres[view], days[view] = MappingProxyType(own), MappingProxyType(dict(n))
    reference = context.Reference(start, end, digest, MappingProxyType(centres), MappingProxyType(days), MappingProxyType(vocab))
    if document_digest(reference.document()) != document_digest(doc):
        raise ValueError('Reference roundtrip changes the frozen document')
    return reference


def score(reference, row):
    context.checked([row], row['date'], row['date'])
    if row['date'] <= reference.end:
        raise ValueError('Scores must follow fitting')
    result = {'scores': {}, 'statuses': {}, 'globally_unseen_category_mass': {}}
    for view in context.VIEWS:
        value, mass = None, None
        if any(row['coverage'].values()):
            status = 'unresolved_event_coverage'
        elif not row['views'][view]:
            status = 'no_resource_activity'
        elif row['user'] not in reference.centres[view]:
            status = 'insufficient_or_unknown_fitting_history'
        else:
            query = context.distribution(row['views'][view])
            value = context.js(query, reference.centres[view][row['user']])
            mass = math.fsum(p for t, p in query.items() if t not in reference.vocabulary[view])
            status = 'ready'
        result['scores'][view], result['statuses'][view] = value, status
        result['globally_unseen_category_mass'][view] = mass
    required = [result['scores'][v] for v in ('action_mix', 'parent_depth1')]
    ready = all(v is not None for v in required)
    result['scores']['joint_primary'] = max(required) if ready else None
    result['statuses']['joint_primary'] = 'ready' if ready else 'required_view_unavailable'
    return result


def calibrate(reference, rows, start, end):
    rows = context.checked(rows, start, end)
    if start <= reference.end:
        raise ValueError('Calibration overlaps fitting')
    scored = [(row, score(reference, row)) for row in rows]
    report = {}
    for mode in MODES:
        available = [(r, s['scores'][mode]) for r, s in scored if s['scores'][mode] is not None]
        values = [v for _, v in available]
        accounts = len({r['user'] for r, _ in available})
        enough = len(values) >= 6 and accounts >= 3
        threshold = quantile_linear(values) if enough else None
        gate = ('insufficient_normal_calibration' if not enough else
                'near_ceiling_no_go' if threshold >= 1 - 1e-12 else 'ready_for_development_comparison')
        report[mode] = {'threshold': threshold, 'gate': gate, 'rows': len(rows), 'scored_rows': len(values),
                        'unscored_rows': len(rows) - len(values), 'scored_accounts': accounts,
                        'normal_calibration_alerts': sum(v > threshold for v in values) if enough else None,
                        'normal_calibration_alert_fraction': sum(v > threshold for v in values) / len(values) if enough else None,
                        'exact_threshold_ties': sum(v == threshold for v in values) if enough else None,
                        'near_threshold_rows_reporting_only': sum(abs(v - threshold) <= 1e-12 for v in values) if enough else None,
                        'maximum_distance_rows': sum(v == 1 for v in values),
                        'status_counts': dict(sorted(Counter(s['statuses'][mode] for _, s in scored).items())),
                        'quantile': .99, 'quantile_method': 'linear', 'boundary_rule': 'strictly_greater',
                        'start': start, 'end': end, 'rows_sha256': document_digest(rows),
                        'reference_document_sha256': document_digest(reference.document())}
    return report, scored
