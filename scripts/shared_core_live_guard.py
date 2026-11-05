"""Reviewed live-only quality guard; does not alter the training-frozen extractor."""
from dataclasses import replace
from scripts import shared_core_features as frozen
from scripts import github_live_projection_v1 as github_activity


def project_live(row):
    if github_activity.claims_repository_activity(row):
        return github_activity.project(row)
    event = frozen.project_live(row)
    # Preserve action-unknown priority even if a missing resource masked it.
    # Otherwise unsupported raw labels could incorrectly enter novelty history.
    if event.source == 'github_events':
        try:
            frozen.github_kind(row['action'])
        except ValueError:
            return replace(event, issue='unknown_action')
    elif event.source == 'cloudflare_access':
        action = row['action'].removesuffix(' (denied)')
        if action not in {'login', 'logout', 'allow', 'deny', 'access'}:
            return replace(event, issue='unknown_action')
        if action == 'access':
            return replace(event, issue='native_action_missing_or_default_ambiguous')
    return event
