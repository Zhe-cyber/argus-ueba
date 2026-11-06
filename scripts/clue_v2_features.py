"""W33 clue_ae_v2 nine-feature extraction, chronological history and fit-only cohort.

Inert on import. Features 1-5 reuse the frozen W23 Day reducer unchanged; this
module adds only the W33 history policy and features 6-9. No model, scores,
scenario generation or archive access here.
"""
from collections import Counter, deque
from dataclasses import dataclass, field
import hashlib
import json
import math
import statistics

from scripts import clue_v2_access as access
from scripts.shared_core_features import Day, digest

PROFILE = 'clue_ae_v2'
FEATURES = ['event_count', 'unique_actions', 'unique_resources', 'off_hours_fraction', 'new_action_count',
            'volume_log_ratio', 'new_resource_share', 'action_mix_js_distance', 'hour_profile_js_distance']
CORE = FEATURES[:5]
K = 5
WINDOW = 28
COHORT_MAX = 500
COHORT_SEED = 42
CLAMP = 1e-12
FEATURE_CONTRACT = {
    'profile': PROFILE, 'features': FEATURES, 'core_reducer': 'shared_core_features.Day (W23, unchanged)',
    'min_prior_usable_active_days': K, 'bounded_window_usable_active_days': WINDOW,
    'feature_5_history': 'expanding prior usable original days',
    'features_6_9_history': 'last <=28 prior usable original active days',
    'invalid_original_days': 'excluded from features and history; chronology still advances',
    'volume_log_ratio': 'log1p(today) - log1p(median prior counts); even median = mean of middle two',
    'new_resource_share': 'share of today distinct resources absent from window union; none today -> unavailable',
    'js': 'base-2 JS distance, event-weighted, per-distribution pseudocount mass 1 over shared support',
    'action_support': 'sorted union of today and window kinds', 'hour_support': 'UTC hours 0-23',
    'clamp': CLAMP, 'cohort': {'seed': COHORT_SEED, 'tag': 'clue_ae_v2_cohort', 'max': COHORT_MAX,
                               'min_active_fit_days': K, 'tie_break': 'account UTF-8 bytes'},
}


def contract_sha256():
    return digest(FEATURE_CONTRACT)


def _clamped(value, name):
    if not math.isfinite(value) or value < -CLAMP or value > 1 + CLAMP:
        raise ValueError(f'{name} outside [0,1] beyond round-off')
    return min(max(value, 0.0), 1.0)


def js_distance(today, prior):
    """Base-2 Jensen-Shannon distance between aligned event-count vectors."""
    if len(today) != len(prior) or not today:
        raise ValueError('Aligned nonempty supports required')
    bins = len(today)
    def smooth(counts):
        if any(c < 0 for c in counts):
            raise ValueError('Negative count')
        total = sum(counts)
        return [(c + 1 / bins) / (total + 1) for c in counts]
    p, q = smooth(today), smooth(prior)
    terms = []
    for a, b in zip(p, q):
        m = (a + b) / 2
        terms.append(0.5 * a * math.log2(a / m) + 0.5 * b * math.log2(b / m))
    return _clamped(math.sqrt(_clamped(math.fsum(terms), 'JS divergence')), 'JS distance')


class V2Day:
    """One account's original or injected day. Wraps the frozen W23 reducer."""

    def __init__(self):
        self.core = Day()
        self.action_counts = Counter()
        self.hours = [0] * 24
        self.synthetic = False

    def add(self, event):
        if not self.core.add(event):
            return False  # duplicate native ID: no extra event weight
        self.action_counts[event.action] += 1
        self.hours[event.local.hour] += 1
        self.synthetic |= event.reference.startswith('sim:')
        return True

    @property
    def key(self):
        return self.core.key

    @property
    def usable(self):
        return self.core.count > 0 and not self.core.issues


@dataclass
class AccountState:
    usable_days: int = 0
    actions: frozenset = frozenset()
    window: deque = field(default_factory=lambda: deque(maxlen=WINDOW))
    last: str | None = None


class History:
    """Start-of-day snapshots for any number of variants; one commit per original day."""

    def __init__(self):
        self.state = {}

    def _state(self, day):
        if not day.key:
            raise ValueError('Observed day required')
        source, scope, account, date = day.key
        state = self.state.get((source, scope, account), AccountState())
        if state.last is not None and date <= state.last:
            raise ValueError('History must advance by closed day')
        return state

    def snapshot(self, day):
        state = self._state(day)
        base = {'prior_usable_days': state.usable_days, 'issues': dict(day.core.issues),
                'features': None, 'unavailable': {}, 'five_feature_eligible': False,
                'nine_feature_eligible': False}
        if not day.usable:
            return {**base, 'status': 'invalid_input'}
        if state.usable_days < K:
            return {**base, 'status': 'cold_start'}
        values = day.core.features(state.actions)
        window = list(state.window)
        values['volume_log_ratio'] = math.log1p(day.core.count) - math.log1p(statistics.median(w[0] for w in window))
        union = frozenset().union(*(w[1] for w in window))
        unavailable = {}
        if day.core.resources:
            values['new_resource_share'] = len(day.core.resources - union) / len(day.core.resources)
        else:
            values['new_resource_share'] = None
            unavailable['new_resource_share'] = 'no_resource_today'
        prior_actions = sum((w[2] for w in window), Counter())
        support = sorted(set(day.action_counts) | set(prior_actions))
        values['action_mix_js_distance'] = js_distance([day.action_counts[k] for k in support],
                                                       [prior_actions[k] for k in support])
        prior_hours = [sum(w[3][h] for w in window) for h in range(24)]
        values['hour_profile_js_distance'] = js_distance(day.hours, prior_hours)
        for name in FEATURES:
            if values[name] is not None and not math.isfinite(values[name]):
                raise ValueError(f'Nonfinite {name}')
        return {**base, 'status': 'eligible', 'features': {name: values[name] for name in FEATURES},
                'unavailable': unavailable, 'five_feature_eligible': True,
                'nine_feature_eligible': not unavailable}

    def commit_original(self, day):
        if day.synthetic:
            raise ValueError('Injected variants never update history')
        state = self._state(day)
        source, scope, account, date = day.key
        state.last = date
        if day.usable:
            state.usable_days += 1
            state.actions = state.actions | frozenset(day.core.actions)
            state.window.append((day.core.count, frozenset(day.core.resources),
                                 Counter(day.action_counts), tuple(day.hours)))
        self.state[source, scope, account] = state


def cohort_rank(account):
    encoded = json.dumps([COHORT_SEED, 'clue_ae_v2_cohort', account], ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def fitting_activity(days_by_account):
    """Count distinct original active fitting days per account; any other date fails closed."""
    lo, hi = access.POLICY['fit']
    counts = {}
    for account, days in days_by_account.items():
        for day in days:
            access.check_day(day, 'pretest')
            if not lo <= day <= hi:
                raise ValueError('Cohort activity must come from fitting dates only')
        counts[account] = len(set(days))
    return counts


def select_cohort(active_fit_days):
    eligible = [account for account, days in active_fit_days.items() if days >= K]
    ranked = sorted(eligible, key=lambda account: (cohort_rank(account), account.encode('utf-8')))
    selected = ranked[:COHORT_MAX]
    return {'selected': selected, 'candidates': len(active_fit_days), 'eligible': len(eligible),
            'below_min_active_fit_days': len(active_fit_days) - len(eligible),
            'excluded_by_cap': len(eligible) - len(selected),
            'cohort_sha256': digest(sorted(selected))}
