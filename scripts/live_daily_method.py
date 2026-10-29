"""Prospective closed-day lab scoring. No model loading, providers or activation."""
from collections import Counter
import math
import statistics

from scripts.aws_lab_daily_features import CONTRACT

METHOD = {'profile': 'aws_lab_method_v1', 'primary': 'personal_resource_excess_cross_entropy',
          'peer_pseudocount': 0.5, 'role_shrinkage_events': 5.0, 'alpha': 0.05,
          'ae_dimensions': [8, 4, 2, 4, 8], 'epochs': 200, 'seed': 42,
          'learning_rate': 0.001, 'weight_decay': 0.001, 'gradient_clip': 5.0,
          'volume_scale_floor': 0.1, 'combined': 'personal_OR_ae'}
COMPONENTS = ('personal', 'population', 'ae', 'volume')
ROLES = tuple(f'persona-{i:02d}' for i in range(1, 7))
DOMAIN = tuple(CONTRACT['resource_domain'])


def distribution(counts, prior=0.5):
    total = sum(counts.values()) + prior * len(DOMAIN)
    return {c: (counts.get(c, 0) + prior) / total for c in DOMAIN}


def entropy(prob):
    return -sum(p * math.log(p) for p in prob.values())


def excess(prob, counts):
    if set(counts) - set(DOMAIN) or not counts or sum(counts.values()) <= 0:
        raise ValueError('Out-of-domain or empty resource context')
    if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in counts.values()):
        raise ValueError('Resource counts must be positive integers')
    total = sum(counts.values())
    return sum((n / total) * (-math.log(prob[c])) for c, n in counts.items()) - entropy(prob)


def fit_references(rows):
    counts = {role: Counter() for role in ROLES}
    pooled = Counter()
    for row in rows:
        counts[row['persona']].update(row['resource_counts'])
        pooled.update(row['resource_counts'])
    references = {}
    for role, own in counts.items():
        if not own:
            raise ValueError('Missing fitting role')
        peer = distribution(pooled - own, METHOD['peer_pseudocount'])
        weight = METHOD['role_shrinkage_events']
        references[role] = {c: (own[c] + weight * peer[c]) / (sum(own.values()) + weight) for c in DOMAIN}
    volumes = [math.log1p(r['features']['event_count']) for r in rows]
    center = statistics.median(volumes)
    scale = max(1.4826 * statistics.median(abs(v - center) for v in volumes), METHOD['volume_scale_floor'])
    return {'profile': METHOD['profile'], 'personal': references, 'population': distribution(pooled),
            'volume_center': center, 'volume_scale': scale}


def context_scores(ref, row):
    return {'personal': excess(ref['personal'][row['persona']], row['resource_counts']),
            'population': excess(ref['population'], row['resource_counts']),
            'volume': abs(math.log1p(row['features']['event_count']) - ref['volume_center']) / ref['volume_scale']}


def empirical_threshold(values):
    if not values or any(not math.isfinite(v) for v in values):
        raise ValueError('Invalid calibration scores')
    ordered = sorted(values)
    allowed = len(values) // 20  # exact floor(5%*n), avoiding floating rounding
    threshold = ordered[len(values) - allowed - 1]
    alerts = sum(v > threshold for v in values)
    return {'threshold': threshold, 'normal_account_days': len(values), 'normal_alerts': alerts,
            'normal_alert_fraction': alerts / len(values), 'tail_resolution': 1 / len(values),
            'ties_at_threshold': sum(v == threshold for v in values),
            'gate': 'no_go_constant_calibration' if min(values) == max(values) else 'normal_calibration_only',
            'comparison': 'strictly_greater', 'empirical_budget': METHOD['alpha']}


def calibrate(scored, references):
    components = {name: empirical_threshold([r[name] for r in scored]) for name in COMPONENTS}
    primary = components['personal']['threshold']
    ceilings = {role: {'upper_bound': max(-math.log(p) for p in prob.values()) - entropy(prob),
                       'can_cross_threshold': max(-math.log(p) for p in prob.values()) - entropy(prob) > primary}
                for role, prob in references['personal'].items()}
    combined = sum(r['personal'] > primary or r['ae'] > components['ae']['threshold'] for r in scored)
    primary_ok = components['personal']['gate'] == 'normal_calibration_only' and all(v['can_cross_threshold'] for v in ceilings.values())
    per_role = {}
    for role in ROLES:
        own = [r for r in scored if r['persona'] == role]
        if not own: raise ValueError('Missing calibration role')
        per_role[role] = {}
        for name in COMPONENTS:
            alerts = sum(r[name] > components[name]['threshold'] for r in own)
            per_role[role][name] = {'account_days': len(own), 'alerts': alerts, 'alert_fraction': alerts / len(own)}
    return {'components': components, 'primary_role_ceilings': ceilings,
            'primary_gate': 'normal_calibration_only' if primary_ok else 'no_go_constant_or_blind_role',
            'combined_normal_alerts': combined, 'combined_normal_account_days': len(scored),
            'combined_normal_alert_fraction': combined / len(scored),
            'combined_budget_pass': combined * 20 <= len(scored),
            'combined_gate': ('normal_calibration_only' if primary_ok and components['ae']['gate'] == 'normal_calibration_only'
                              and combined * 20 <= len(scored) else 'no_go_component_or_union'),
            'per_role': per_role,
            'evaluation_status': 'normal_calibration_only', 'activated': False}


def validation_summary(scored, calibration):
    components = {}
    for name in COMPONENTS:
        alerts = sum(r[name] > calibration['components'][name]['threshold'] for r in scored)
        components[name] = {'account_days': len(scored), 'alerts': alerts, 'alert_fraction': alerts / len(scored)}
    union = sum(r['personal'] > calibration['components']['personal']['threshold']
                or r['ae'] > calibration['components']['ae']['threshold'] for r in scored)
    return {'components': components, 'combined_alerts': union, 'account_days': len(scored),
            'combined_alert_fraction': union / len(scored),
            'limitations': 'Normal validation reused for AE checkpoint selection; not independent detection evaluation.'}


def build_ae():
    import torch.nn as nn
    return nn.Sequential(nn.Linear(8, 4), nn.Tanh(), nn.Linear(4, 2), nn.Tanh(),
                         nn.Linear(2, 4), nn.Tanh(), nn.Linear(4, 8))
