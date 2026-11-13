"""Opt-in, read-only validation of externally pinned diagnostic receipt artifacts."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
import re

FEATURES = ['event_count', 'unique_actions', 'unique_resources', 'off_hours_fraction', 'new_action_count',
            'volume_log_ratio', 'new_resource_share', 'action_mix_js_distance', 'hour_profile_js_distance']
SCOPES = {**dict.fromkeys(FEATURES[:4], 'current_day_only'), 'new_action_count': 'expanding_history_days',
          **dict.fromkeys(FEATURES[5:], 'rolling_window_days')}
SCHEMAS = {'clue_v2_live_diagnostic_receipt_v1', 'clue_v2_live_diagnostic_receipt_v2'}
LABEL = 'experimental model diagnostic — not validated for this live source'
SOURCES = {'aws_cloudtrail', 'github_events', 'cloudflare_access'}
MYT = timezone(timedelta(hours=8))


class ReceiptError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise ReceiptError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'invalid_json')
            result[key] = value
        return result
    def constant(_):
        raise ReceiptError('invalid_json')
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ReceiptError('invalid_json') from error


def stamp(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(result.tzinfo is not None and result.utcoffset() is not None, 'invalid_cutoff')
        return result.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError) as error:
        raise ReceiptError('invalid_cutoff') from error


def hexhash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def key_tuple(key, code='invalid_key'):
    require(isinstance(key, dict) and set(key) == {'source', 'scope', 'account', 'day'}, code)
    require(isinstance(key['source'], str) and key['source'] in SOURCES
            and isinstance(key['scope'], str) and 0 < len(key['scope']) <= 256
            and isinstance(key['account'], str) and re.fullmatch('acct_[0-9a-f]{64}', key['account']), code)
    try:
        require(date.fromisoformat(key['day']).isoformat() == key['day'], code)
    except (ValueError, TypeError) as error:
        raise ReceiptError(code) from error
    return tuple(key[n] for n in ('source', 'scope', 'account', 'day'))


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_provenance(value):
    require(isinstance(value, dict) and value.get('profile') == 'clue_ae_v2', 'invalid_provenance')
    require(type(value.get('coverage_policy_version')) is int and value['coverage_policy_version'] > 0
            and isinstance(value.get('projection'), str) and bool(value['projection'])
            and isinstance(value.get('transform'), str) and bool(value['transform']), 'invalid_provenance')
    for name in ('preregistration_sha256', 'training_manifest_sha256', 'feature_contract_sha256',
                 'coverage_policy_sha256'):
        require(hexhash(value.get(name)), 'invalid_provenance')
    sources = value.get('source_sha256')
    require(isinstance(sources, dict) and bool(sources)
            and all(isinstance(k, str) and hexhash(v) for k, v in sources.items()), 'invalid_provenance')
    require(isinstance(value.get('detectors'), dict) and set(value['detectors']) == {'B', 'C'}, 'invalid_provenance')
    for detector in value['detectors'].values():
        require(isinstance(detector, dict) and all(hexhash(detector.get(k))
                for k in ('model_sha256', 'scaler_sha256')), 'invalid_provenance')


def verify_current_sources(provenance):
    root = Path(__file__).resolve().parents[1]
    for name, expected in provenance['source_sha256'].items():
        path = (root / name).resolve()
        require(path.is_relative_to(root) and path.is_file(), 'source_binding_mismatch')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'source_binding_mismatch')


def validate_history(row):
    history = row['history']
    require(isinstance(history, dict) and history.get('window_usable_days') == 28
            and history.get('min_prior_usable_days') == 5, 'invalid_history')
    prior = history.get('prior_accepted_days')
    require(isinstance(prior, list) and all(isinstance(d, str) for d in prior), 'invalid_history')
    require(prior == sorted(set(prior)), 'invalid_history')
    for day in prior:
        try:
            require(date.fromisoformat(day).isoformat() == day and day < row['key']['day'], 'invalid_history')
        except (ValueError, TypeError) as error:
            raise ReceiptError('invalid_history') from error
    if row['schema'].endswith('_v2'):
        require(history.get('expanding_history_days') == prior
                and history.get('rolling_window_days') == prior[-28:]
                and history.get('feature_history_scope') == SCOPES, 'invalid_history')
    return {'expanding_history_days': prior, 'rolling_window_days': prior[-28:],
            'feature_history_scope': SCOPES}


def validate_scores(row):
    detectors = row['detectors']
    require(isinstance(row.get('input'), dict) and row['input'].get('status') in {
        'eligible', 'cold_start', 'invalid_input', 'not_scored_by_coverage_policy'}, 'invalid_input_status')
    require(isinstance(row.get('coverage'), dict), 'invalid_coverage')
    require(isinstance(detectors, dict) and not set(detectors) - {'B', 'C'}, 'invalid_scores')
    if not detectors:
        require(isinstance(row['input'].get('why_unscored'), str) and bool(row['input']['why_unscored']), 'missing_reason')
        return
    inputs, coverage = row['input'], row['coverage']
    require(inputs.get('status') == 'eligible' and inputs.get('five_feature_eligible') is True
            and len(row['history']['prior_accepted_days']) >= 5, 'ineligible_score')
    require(coverage.get('policy_status') in {'usable', 'outside_policy_completeness_unknown'}, 'ineligible_score')
    if coverage['policy_status'] == 'usable':
        counts = [coverage.get(k) for k in ('planned', 'verified', 'unresolved', 'not_yet_ingested')]
        require(all(type(n) is int and n >= 0 for n in counts) and counts[0] > 0
                and counts[0] >= counts[1] and counts[1] * 10 >= counts[0] * 9
                and counts[2:] == [0, 0] and row.get('completeness') == 'policy_verified', 'ineligible_score')
    features = row.get('features')
    require(isinstance(features, dict) and features.get('names') == FEATURES
            and isinstance(features.get('raw_values'), dict) and set(features['raw_values']) == set(FEATURES), 'invalid_features')
    require(all(number(v) or (k == 'new_resource_share' and v is None)
                for k, v in features['raw_values'].items()), 'invalid_features')
    for name, detector in detectors.items():
        columns = FEATURES[:5] if name == 'B' else FEATURES
        if name == 'C':
            require(inputs.get('nine_feature_eligible') is True and features['raw_values']['new_resource_share'] is not None,
                    'ineligible_score')
        require(isinstance(detector, dict), 'invalid_scores')
        score, terms = detector.get('score_raw_mse'), detector.get('terms')
        require(number(score) and score >= 0 and isinstance(terms, list) and len(terms) == len(columns), 'invalid_scores')
        require(all(isinstance(t, dict) for t in terms)
                and {t.get('feature') for t in terms} == set(columns), 'invalid_terms')
        for term in terms:
            values = [term.get(k) for k in ('squared_residual', 'additive_term', 'share_of_reconstruction_error')]
            require(all(number(v) and v >= 0 for v in values), 'invalid_terms')
            require(math.isclose(values[1], values[0] / len(columns), rel_tol=2e-5, abs_tol=1e-7), 'invalid_terms')
        require(math.isclose(sum(t['additive_term'] for t in terms), score, rel_tol=2e-5, abs_tol=1e-7), 'invalid_terms')
        total = sum(t['squared_residual'] for t in terms)
        require(all(math.isclose(t['share_of_reconstruction_error'], t['squared_residual'] / (total or 1),
                                rel_tol=2e-5, abs_tol=1e-7) for t in terms), 'invalid_terms')


@dataclass(frozen=True)
class ReceiptIndex:
    rows: dict
    cutoff_utc: str
    recorded: bool

    def lookup(self, source, scope, account, day):
        key = key_tuple(dict(source=source, scope=scope, account=account, day=day), 'invalid_query')
        row = self.rows.get(key)
        common = {'cutoff_utc': self.cutoff_utc, 'mode': 'recorded' if self.recorded else 'live_diagnostic',
                  'live_activation': False, 'risk_tier': None}
        if row is None:
            return {**common, 'status': 'unavailable', 'reason': 'No diagnostic receipt for this account-day.'}
        return {**common, 'status': 'diagnostic' if row['detectors'] else 'unscored',
                'receipt': deepcopy(row), 'history_scopes': deepcopy(validate_history(row))}


def load_bundle(directory, *, manifest_sha256, expected_provenance, now=None,
                max_age_seconds=172800, recorded_mode=False):
    """Validate the entire externally pinned artifact before exposing any row."""
    try:
        directory = Path(directory).resolve(strict=True)
        manifest_path, rows_path = directory / 'manifest.json', directory / 'receipts.jsonl'
        require(manifest_path.stat().st_size <= 2_000_000 and rows_path.stat().st_size <= 64_000_000, 'artifact_too_large')
        raw_manifest, raw_rows = manifest_path.read_bytes(), rows_path.read_bytes()
        require(len(raw_manifest) <= 2_000_000 and len(raw_rows) <= 64_000_000, 'artifact_too_large')
        require(hexhash(manifest_sha256) and hashlib.sha256(raw_manifest).hexdigest() == manifest_sha256, 'manifest_hash_mismatch')
        manifest = strict_json(raw_manifest)
        require(isinstance(manifest, dict), 'invalid_manifest')
        schema = manifest.get('schema', '').removesuffix('_manifest')
        require(schema in SCHEMAS and manifest.get('schema') == schema + '_manifest', 'unsupported_schema')
        validate_provenance(expected_provenance)
        require(manifest.get('provenance') == expected_provenance, 'provenance_mismatch')
        require(manifest.get('live_activation') is False and manifest.get('alerts_created') is False
                and manifest.get('label') == LABEL, 'activation_not_allowed')
        cutoff = stamp(manifest.get('cutoff_utc'))
        now = now or datetime.now(timezone.utc)
        require(now.tzinfo is not None and now.utcoffset() is not None and cutoff <= now, 'future_cutoff')
        require(type(recorded_mode) is bool and type(max_age_seconds) in (int, float)
                and math.isfinite(max_age_seconds) and max_age_seconds >= 0, 'invalid_options')
        require(recorded_mode or (now - cutoff).total_seconds() <= max_age_seconds, 'stale_artifact')
        if not recorded_mode:
            verify_current_sources(expected_provenance)
        require(hashlib.sha256(raw_rows).hexdigest() == manifest.get('receipts_sha256'), 'receipts_hash_mismatch')
        lines = raw_rows.splitlines()
        require(len(lines) <= 50_000 and type(manifest.get('receipts')) is int
                and manifest['receipts'] == len(lines), 'receipt_count_mismatch')
        rows = {}
        for line in lines:
            require(len(line) <= 256_000, 'artifact_too_large')
            row = strict_json(line)
            require(isinstance(row, dict), 'invalid_receipt')
            key = key_tuple(row.get('key'))
            require(key not in rows, 'duplicate_key')
            require(row.get('schema') == schema and row.get('provenance') == expected_provenance
                    and row.get('cutoff_utc') == manifest['cutoff_utc'], 'receipt_binding_mismatch')
            require(row.get('receipt_id') == digest({k: row[k] for k in ('key', 'cutoff_utc', 'provenance')}), 'receipt_id_mismatch')
            require(row.get('live_activation') is False and row.get('alert') is False
                    and row.get('risk_tier') is None and row.get('label') == LABEL, 'activation_not_allowed')
            require(row.get('source_timezone') == 'Asia/Kuala_Lumpur'
                    and key[3] < cutoff.astimezone(MYT).date().isoformat(), 'open_day')
            validate_history(row)
            validate_scores(row)
            rows[key] = row
        require(type(manifest.get('scored_receipts')) is int
                and sum(bool(r['detectors']) for r in rows.values()) == manifest['scored_receipts'], 'receipt_count_mismatch')
        return ReceiptIndex(rows, manifest['cutoff_utc'], recorded_mode)
    except ReceiptError:
        raise
    except (OSError, KeyError, TypeError, AttributeError, ValueError, OverflowError) as error:
        raise ReceiptError('invalid_artifact') from error


def configured_lookup(config, *, approved, source, scope, account, day, now=None):
    """Backend-only configuration; browser requests cannot supply paths or trust pins."""
    query = dict(source=source, scope=scope, account=account, day=day)
    key_tuple(query, 'invalid_query')
    if approved is not True or config is None:
        return {'status': 'unavailable', 'reason': 'Model diagnostics are not enabled.',
                'live_activation': False, 'risk_tier': None}
    require(isinstance(config, dict) and set(config) <= {
        'directory', 'manifest_sha256', 'expected_provenance', 'recorded_mode', 'max_age_seconds'}, 'invalid_configuration')
    require({'directory', 'manifest_sha256', 'expected_provenance'} <= set(config), 'invalid_configuration')
    index = load_bundle(**config, now=now)
    return index.lookup(source, scope, account, day)


def availability_lookup(config, *, source, scope, account, day, now=None):
    """Expose verified input readiness/coverage without exposing any model scores."""
    key_tuple(dict(source=source, scope=scope, account=account, day=day), 'invalid_query')
    if config is None:
        return {'status': 'unavailable', 'reason': 'No reviewed diagnostic artifact is configured.',
                'live_activation': False, 'risk_tier': None, 'scores_visible': False}
    result = configured_lookup(config, approved=True, source=source, scope=scope, account=account, day=day, now=now)
    result['scores_visible'] = False
    row = result.get('receipt')
    if row is not None:
        if row['input']['status'] == 'eligible':
            row['input']['why_unscored'] = 'Model input is ready; experimental score display is pending approval.'
        row['detectors'], row['features'], row['facts'] = {}, None, []
        result['status'] = 'unscored'
    return result
