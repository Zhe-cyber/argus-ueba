"""Pure Python review-priority contract shared by the offline exporter and API."""
from datetime import date
import math

PROFILE = 'clue_behavior_v1'
TIERS = ('Low', 'Medium', 'High')
FEATURES = ['event_count', 'unique_actions', 'unique_paths', 'utc_off_hours_events',
            'new_action_count', 'file_access_events', 'login_attempt_events',
            'login_success_events', 'sharing_events', 'permission_change_events']


def priority(score, medium, high):
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in (score, medium, high)) or not 0 <= medium <= high or score < 0:
        raise ValueError('Invalid review-priority inputs')
    return 'High' if score > high else 'Medium' if score > medium else 'Low'


def validate_policy(policy):
    if (not isinstance(policy, dict) or policy.get('schema_version') != 1 or policy.get('profile') != PROFILE
            or policy.get('medium_quantile') != .95 or policy.get('high_quantile') != .99
            or policy.get('quantile_method') != 'linear'
            or policy.get('boundary_rule') != 'strictly_greater'
            or policy.get('units') != 'raw_reconstruction_mse'):
        raise ValueError('Unsupported replay policy')
    priority(0, policy['medium_threshold'], policy['high_threshold'])
    if policy['high_threshold'] <= 0:
        raise ValueError('Degenerate threshold')
    cuts = policy['cutoffs_utc']
    if (not isinstance(cuts, list) or len(cuts) != 5
            or any(not isinstance(d, str) or date.fromisoformat(d).isoformat() != d for d in cuts)
            or cuts != sorted(set(cuts))):
        raise ValueError('Invalid chronological cutoffs')
    if policy['features'] != FEATURES:
        raise ValueError('Invalid feature contract')
    for field in ('model_sha256', 'scaler_sha256', 'dataset_sha256', 'candidate_manifest_sha256'):
        value = policy[field]
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Invalid provenance binding')
