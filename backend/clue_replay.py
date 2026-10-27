"""Read-only, explicitly enabled CLUE replay. Never reads or writes live state."""
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from backend.clue_replay_contract import FEATURES, PROFILE, TIERS, priority, validate_policy
router = APIRouter(prefix='/replay/clue', tags=['Offline CLUE replay'])


def read_bundle(directory):
    root = Path(directory)
    raw = {}
    for name in ('manifest.json', 'policy.json', 'replay.json'):
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Missing or oversized replay artifact')
        raw[name] = path.read_bytes()
    manifest = json.loads(raw['manifest.json'])
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 1:
        raise ValueError('Unsupported bundle')
    for name in ('policy.json', 'replay.json'):
        if hashlib.sha256(raw[name]).hexdigest() != manifest.get(name + '_sha256'):
            raise ValueError('Replay digest differs')
    policy = json.loads(raw['policy.json'])
    validate_policy(policy)
    data = json.loads(raw['replay.json'])
    if not isinstance(data, dict) or data.get('profile') != PROFILE or data.get('schema_version') != 1:
        raise ValueError('Unsupported replay profile')
    rows = data['rows']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 5000:
        raise ValueError('Invalid replay rows')
    seen, clean = set(), []
    cuts = policy['cutoffs_utc']
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid replay row')
        split, account, day = row['split'], row['account'], row['day']
        if split not in ('heldout', 'calibration') or date.fromisoformat(day).isoformat() != day:
            raise ValueError('Invalid row partition')
        if not isinstance(account, str) or not account.startswith('cohort-') or not account[7:].isdigit():
            raise ValueError('Only cohort aliases are served')
        start, end = (cuts[2], cuts[3]) if split == 'calibration' else (cuts[3], cuts[4])
        if not start < day <= end or (account, day) in seen:
            raise ValueError('Row outside its disjoint partition')
        seen.add((account, day))
        expected = priority(row['raw_mse'], policy['medium_threshold'], policy['high_threshold'])
        if row['review_priority'] != expected:
            raise ValueError('Priority differs from frozen policy')
        features, residuals = row['features'], row['residuals']
        if (not isinstance(features, dict) or not isinstance(residuals, dict)
                or set(features) != set(policy['features']) or set(residuals) != set(policy['features'])):
            raise ValueError('Row feature contract differs')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
               for v in [*features.values(), *residuals.values()]):
            raise ValueError('Invalid numerical evidence')
        if not math.isclose(sum(residuals.values()), row['raw_mse'], rel_tol=1e-5, abs_tol=1e-7):
            raise ValueError('Residuals do not reconstruct the score')
        # Whitelist output, even if a local artifact contains extra private fields.
        clean.append({'account': account, 'day': day, 'split': split,
                      'raw_mse': row['raw_mse'], 'review_priority': expected,
                      'threshold_multiple': row['raw_mse'] / policy['high_threshold'],
                      'features': features, 'residuals': residuals})
    return policy, sorted(clean, key=lambda r: (r['day'], r['account']))


def configured_bundle():
    directory = os.getenv('CLUE_REPLAY_DIR')
    if not directory:
        raise ValueError('Replay not configured')
    return read_bundle(directory)


@router.get('/metadata')
def metadata():
    try:
        policy, rows = configured_bundle()
    except (ValueError, OSError, KeyError, TypeError, OverflowError):
        return {'available': False, 'message': 'Offline CLUE replay is not configured or failed validation. Live data is unchanged.'}
    splits = {}
    for split in ('heldout', 'calibration'):
        selected = [r for r in rows if r['split'] == split]
        splits[split] = {'account_days': len(selected), 'accounts': len({r['account'] for r in selected}),
                         'dates': sorted({r['day'] for r in selected}),
                         'counts': {tier: sum(r['review_priority'] == tier for r in selected) for tier in TIERS}}
    public_policy = {k: policy[k] for k in ('schema_version', 'profile', 'features', 'medium_threshold',
                     'high_threshold', 'medium_quantile', 'high_quantile', 'quantile_method', 'boundary_rule',
                     'units', 'cutoffs_utc', 'model_sha256', 'scaler_sha256', 'dataset_sha256', 'candidate_manifest_sha256')}
    return {'available': True, 'profile': PROFILE, 'policy': public_policy, 'splits': splits,
            'notice': 'Normal benchmark data: few alerts are expected. Review priority is not compromise probability.',
            'limitations': 'Population novelty can miss account misuse. This is offline CLUE storage activity, not live-provider detection. Previously inspected held-out dates are development evidence for later revisions.',
            'attribution': 'CLUE-LDS, Landauer et al., DOI 10.5281/zenodo.7119953, CC BY 4.0'}


@router.get('/rows')
def replay_rows(split: str = Query('heldout', pattern='^(heldout|calibration)$'),
                day: str | None = None, review_priority: str | None = Query(None, pattern='^(Low|Medium|High)$')):
    try:
        _, rows = configured_bundle()
    except (ValueError, OSError, KeyError, TypeError, OverflowError):
        raise HTTPException(503, 'Replay unavailable; configure a verified offline bundle.') from None
    selected = [r for r in rows if r['split'] == split and (day is None or r['day'] == day)
                and (review_priority is None or r['review_priority'] == review_priority)]
    return {'split': split, 'total': len(selected), 'rows': selected}
