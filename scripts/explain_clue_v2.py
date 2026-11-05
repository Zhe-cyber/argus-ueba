"""W33 explanations: per-feature reconstruction-error terms (layer 1), account-relative behaviour facts
(layer 2) and the reason a day is unscored (layer 4).

Pure functions over the frozen W33 feature/history state and frozen models; inert on import.
Facts compare with the account's *available prior usable history* only: history excludes invalid
days and begins at collection or warm-up, so nothing here establishes lifetime novelty, intent or
compromise. Explanations must use the same start-of-day state as the score: `explain` takes the
History itself and re-derives the snapshot without mutating it, rejecting any advanced, future or
different state. Call it before committing the original day.
"""
from collections import Counter
import statistics

from scripts import clue_v2_features as v2, train_clue_v2 as trainer
from scripts.shared_core_features import HOURS

FEATURE_TEXT = {
    'event_count': 'number of events',
    'unique_actions': 'number of distinct action kinds',
    'unique_resources': 'number of distinct resources',
    'off_hours_fraction': 'share of events outside the model\'s reference hours',
    'new_action_count': 'action kinds not observed in the available prior usable history',
    'volume_log_ratio': 'volume relative to this account\'s recent median',
    'new_resource_share': 'share of resources not used in this account\'s recent usable days',
    'action_mix_js_distance': 'difference from this account\'s recent action mix',
    'hour_profile_js_distance': 'difference from this account\'s recent hour profile',
}
# Explanation-only convention, separate from the frozen reference-hours feature (CLUE 07-19 UTC,
# live 08-20 MYT) and from the rarity rule's own window: an hour is "usual" when it held at least
# this share of the account's prior windowed events.
USUAL_HOUR_SHARE = 0.05
LIMITATIONS = [
    'Facts compare with the available prior usable history only; history excludes invalid days and starts at '
    'collection or warm-up, so it does not establish lifetime novelty.',
    'Reconstruction-error terms explain the model score, not the cause or intent of the activity; they are not '
    'probabilities of compromise or causal SHAP effects.',
]


def contributions(model, scaler, columns, features):
    """Squared residuals in the transformed/scaled feature space. Additive terms (residual / dimension)
    sum exactly to the raw MSE score; shares are shares of reconstruction error."""
    import torch
    x = torch.from_numpy(scaler.transform(trainer.matrix([{'features': features}], columns)))
    with torch.no_grad():
        squared = ((model(x) - x) ** 2)[0]
    score = float(squared.mean())
    residuals = [float(value) for value in squared]
    total = sum(residuals) or 1.0
    ranked = sorted(zip(columns, residuals), key=lambda item: (-item[1], item[0]))
    return {'score_raw_mse': score, 'space': 'log1p-counts, fit-only standardised',
            'terms': [{'feature': name, 'text': FEATURE_TEXT[name], 'squared_residual': value,
                       'additive_term': value / len(columns), 'share_of_reconstruction_error': value / total}
                      for name, value in ranked]}


def _hour_ranges(hours):
    hours, ranges, start = sorted(hours), [], None
    for index, hour in enumerate(hours):
        if start is None:
            start = hour
        if index + 1 == len(hours) or hours[index + 1] != hour + 1:
            ranges.append(f'{start:02d}:00' if start == hour else f'{start:02d}:00-{hour:02d}:59')
            start = None
    return ', '.join(ranges)


def _largest(counter):
    """Deterministic largest share: highest count, then name."""
    name, count = sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0]
    return name, count / sum(counter.values())


def behaviour_facts(state, day):
    """Plain-language comparisons with the account's prior usable days. Internal: use `explain`."""
    window = list(state.window)
    if not window or not day.usable:
        raise ValueError('Facts need a usable day and prior usable history')
    zone = HOURS[day.key[0]][0]
    n = len(window)
    facts = []
    median = statistics.median(w[0] for w in window)
    ratio = day.core.count / median if median else None
    facts.append({'kind': 'volume', 'today': day.core.count, 'recent_median': median, 'ratio': ratio,
                  'text': f'{day.core.count} events today; the median over this account\'s last {n} usable active '
                          f'days is {median:g}' + (f' (about {ratio:.1f}x).' if ratio is not None else '.')})
    new_kinds = sorted(set(day.core.actions) - set(state.actions))
    if new_kinds:
        facts.append({'kind': 'new_actions', 'actions': new_kinds,
                      'text': f'{len(new_kinds)} action kind(s) not observed in the available prior usable history: '
                              f'{", ".join(new_kinds)}.'})
    if day.core.resources:
        union = frozenset().union(*(w[1] for w in window))
        new = len(day.core.resources - union)
        facts.append({'kind': 'new_resources', 'new': new, 'total': len(day.core.resources),
                      'text': f'{new} of {len(day.core.resources)} resources used today were not used in this '
                              f'account\'s last {n} usable active days.'})
    else:
        facts.append({'kind': 'no_resources',
                      'text': 'No resource-bearing events today; resource-based features are unavailable.'})
    prior_hours = [sum(w[3][h] for w in window) for h in range(24)]
    total_prior = sum(prior_hours)
    usual = sorted(h for h in range(24) if total_prior and prior_hours[h] / total_prior >= USUAL_HOUR_SHARE)
    today_hours = [h for h in range(24) if day.hours[h]]
    if usual:
        outside = sum(day.hours[h] for h in range(24) if h not in usual)
        text = (f'{outside} of {day.core.count} events fell outside the hours that held at least '
                f'{USUAL_HOUR_SHARE:.0%} of this account\'s recent events ({_hour_ranges(usual)} {zone}); '
                f'today: {_hour_ranges(today_hours)} {zone}.')
    else:
        outside = None
        text = (f'No concentrated usual hours can be established: no hour held at least {USUAL_HOUR_SHARE:.0%} of '
                f'this account\'s recent events. The model\'s hour-profile distance is the relevant measure. '
                f'Today: {_hour_ranges(today_hours)} {zone}.')
    facts.append({'kind': 'hours', 'convention': f'hours holding >= {USUAL_HOUR_SHARE:.0%} of prior windowed events',
                  'usual_hours': usual, 'events_outside_usual_hours': outside, 'today_hours': today_hours,
                  'timezone': zone, 'text': text})
    prior_mix = sum((w[2] for w in window), Counter())
    today_top, today_share = _largest(day.action_counts)
    usual_top, usual_share = _largest(prior_mix)
    facts.append({'kind': 'action_mix', 'today_largest': today_top, 'today_share': today_share,
                  'recent_largest': usual_top, 'recent_share': usual_share,
                  'text': f'Largest action share today: {today_top} ({today_share:.0%}); in the last {n} usable '
                          f'active days: {usual_top} ({usual_share:.0%}).'})
    return facts


def why_unscored(snapshot):
    """Layer 4: the explicit reason a day has no (or only a partial) score."""
    if snapshot['status'] == 'cold_start':
        return f'Insufficient history: {snapshot["prior_usable_days"]} of {v2.K} usable prior days.'
    if snapshot['status'] == 'invalid_input':
        return 'Input incomplete for this day: ' + ', '.join(f'{k} ({n})' for k, n in sorted(snapshot['issues'].items())) + '.'
    if not snapshot['nine_feature_eligible']:
        return 'No resource today: the nine-feature model cannot score; the five-feature view only.'
    return None


def explain(snapshot, history, day, bundle):
    """Explain one day from the same start-of-day state as its score.

    `history` is the W33 History *before* this day is committed. The snapshot is re-derived without
    mutation and must equal the supplied one, so an advanced, future or different state is rejected."""
    if history.snapshot(day) != snapshot:  # raises on chronology; compares status, prior days and features
        raise ValueError('Explanation state differs from the scored start-of-day snapshot')
    source, scope, account, date = day.key
    result = {'key': {'source': source, 'scope': scope, 'account': account, 'day': date},
              'status': snapshot['status'], 'why_unscored': why_unscored(snapshot), 'detectors': {}, 'facts': [],
              'limitations': LIMITATIONS}
    if snapshot['status'] != 'eligible':
        return result
    result['facts'] = behaviour_facts(history.state[day.key[:3]], day)
    features = snapshot['features']
    for name, (model, scaler, columns) in bundle.items():
        if name == 'C' and not snapshot['nine_feature_eligible']:
            continue
        values = features if name == 'C' else dict(
            features, new_resource_share=0.0 if features['new_resource_share'] is None else features['new_resource_share'])
        result['detectors'][name] = contributions(model, scaler, columns, values)
    return result
