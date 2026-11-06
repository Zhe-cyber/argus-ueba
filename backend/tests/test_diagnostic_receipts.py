"""Synthetic receipt-consumer contract tests; no model, store or provider access."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json

import pytest

from workspace_next import diagnostic_receipts as consumer

NOW = datetime(2026, 11, 1, 1, tzinfo=timezone.utc)
ACCOUNT = 'acct_' + 'a' * 64


def fixture():
    provenance = {'profile': 'clue_ae_v2', 'coverage_policy_version': 2, 'projection': 'live_projection',
                  'transform': 'frozen count transform',
                  'source_sha256': {'workspace_next/diagnostic_receipts.py': hashlib.sha256(
                      __import__('pathlib').Path(consumer.__file__).read_bytes()).hexdigest()},
                  'detectors': {name: {'model_sha256': 'b' * 64, 'scaler_sha256': 'c' * 64} for name in ('B', 'C')},
                  **{name: 'd' * 64 for name in ('preregistration_sha256', 'training_manifest_sha256',
                                                'feature_contract_sha256', 'coverage_policy_sha256')}}
    prior = [f'2026-10-{n:02d}' for n in range(1, 31)]
    row = {'schema': 'clue_v2_live_diagnostic_receipt_v2', 'label': consumer.LABEL,
           'key': {'source': 'github_events', 'scope': 'github-owner:77', 'account': ACCOUNT, 'day': '2026-10-31'},
           'cutoff_utc': '2026-11-01T00:00:00+00:00', 'source_timezone': 'Asia/Kuala_Lumpur',
           'provenance': provenance, 'live_activation': False, 'alert': False, 'risk_tier': None,
           'history': {'prior_accepted_days': prior, 'expanding_history_days': prior,
                       'rolling_window_days': prior[-28:], 'feature_history_scope': consumer.SCOPES,
                       'window_usable_days': 28, 'min_prior_usable_days': 5},
           'coverage': {'policy_status': 'outside_policy_completeness_unknown'}, 'completeness': 'unknown',
           'input': {'status': 'eligible', 'five_feature_eligible': True, 'nine_feature_eligible': True, 'why_unscored': None},
           'features': {'names': consumer.FEATURES, 'raw_values': dict.fromkeys(consumer.FEATURES, 1)},
           'detectors': {}, 'facts': [], 'limitations': ['Experimental live diagnostic.']}
    for name, columns in [('B', consumer.FEATURES[:5]), ('C', consumer.FEATURES)]:
        row['detectors'][name] = {'score_raw_mse': 1., 'space': 'fit-only standardised',
            'terms': [{'feature': f, 'text': f, 'squared_residual': 1., 'additive_term': 1. / len(columns),
                       'share_of_reconstruction_error': 1. / len(columns)} for f in columns]}
    return row, provenance


def write_bundle(path, rows, provenance, **changes):
    path.mkdir(exist_ok=True)
    for row in rows:
        row['receipt_id'] = consumer.digest({k: row[k] for k in ('key', 'cutoff_utc', 'provenance')})
    body = b''.join(consumer.canonical(row) + b'\n' for row in rows)
    (path / 'receipts.jsonl').write_bytes(body)
    manifest = {'schema': rows[0]['schema'] + '_manifest', 'cutoff_utc': rows[0]['cutoff_utc'],
                'label': consumer.LABEL, 'provenance': provenance, 'live_activation': False,
                'alerts_created': False, 'receipts': len(rows), 'receipts_sha256': hashlib.sha256(body).hexdigest(),
                'scored_receipts': sum(bool(r['detectors']) for r in rows), **changes}
    raw = consumer.canonical(manifest)
    (path / 'manifest.json').write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def load(path, rows=None, provenance=None, **options):
    row, default_provenance = fixture()
    provenance = provenance or default_provenance
    pin = write_bundle(path, rows or [row], provenance)
    return consumer.load_bundle(path, manifest_sha256=pin, expected_provenance=provenance, now=NOW, **options)


@pytest.mark.parametrize('version', [1, 2])
def test_valid_legacy_and_v2_keep_expanding_and_rolling_scopes_separate(tmp_path, version):
    row, provenance = fixture()
    row['schema'] = 'clue_v2_live_diagnostic_receipt_v' + str(version)
    if version == 1:
        for field in ('expanding_history_days', 'rolling_window_days', 'feature_history_scope'):
            row['history'].pop(field)
    index = load(tmp_path, [row], provenance)
    out = index.lookup(*row['key'].values())
    assert out['status'] == 'diagnostic' and out['risk_tier'] is None
    assert len(out['history_scopes']['expanding_history_days']) == 30
    assert len(out['history_scopes']['rolling_window_days']) == 28
    out['history_scopes']['rolling_window_days'].clear()
    assert len(index.lookup(*row['key'].values())['history_scopes']['rolling_window_days']) == 28
    assert index.lookup('github_events', 'different-scope', ACCOUNT, '2026-10-31')['status'] == 'unavailable'


def test_missing_day_does_not_borrow_another_day_or_return_low(tmp_path):
    index = load(tmp_path)
    out = index.lookup('github_events', 'github-owner:77', ACCOUNT, '2026-10-30')
    assert out['status'] == 'unavailable' and 'receipt' not in out and out['risk_tier'] is None


def test_gap_receipt_is_unscored(tmp_path):
    row, provenance = fixture()
    row.update(detectors={}, features=None)
    row['input'] = {'status': 'not_scored_by_coverage_policy', 'why_unscored': 'No verified planned receipts.'}
    row['coverage'] = {'policy_status': 'incomplete', 'observed_events': 0}
    index = load(tmp_path, [row], provenance)
    assert index.lookup(*row['key'].values())['status'] == 'unscored'


@pytest.mark.parametrize('fault,code', [
    ('activation', 'activation_not_allowed'), ('tier', 'activation_not_allowed'),
    ('history', 'invalid_history'), ('scope_window', 'invalid_history'),
    ('cold_start', 'ineligible_score'), ('coverage', 'ineligible_score'),
    ('terms', 'invalid_terms'), ('negative', 'invalid_terms'),
    ('bad_key', 'invalid_key'), ('open_day', 'open_day'),
    ('wrong_provenance', 'receipt_binding_mismatch')])
def test_semantically_bad_rows_fail_even_with_recomputed_artifact_hash(tmp_path, fault, code):
    row, provenance = fixture()
    if fault == 'activation': row['live_activation'] = True
    elif fault == 'tier': row['risk_tier'] = 'Low'
    elif fault == 'history': row['history']['prior_accepted_days'].append('2026-11-01')
    elif fault == 'scope_window': row['history']['rolling_window_days'] = row['history']['prior_accepted_days']
    elif fault == 'cold_start': row['input']['status'] = 'cold_start'
    elif fault == 'coverage': row['coverage']['policy_status'] = 'incomplete'
    elif fault == 'terms': row['detectors']['C']['terms'][0]['additive_term'] = 100
    elif fault == 'negative': row['detectors']['C']['terms'][0]['squared_residual'] = -1
    elif fault == 'bad_key': row['key']['account'] = 'someone'
    elif fault == 'open_day': row['key']['day'] = '2026-11-01'
    else: row['provenance'] = {**provenance, 'coverage_policy_sha256': 'f' * 64}
    with pytest.raises(consumer.ReceiptError, match=code):
        load(tmp_path, [row], provenance)


def test_duplicate_keys_invalidate_entire_bundle(tmp_path):
    row, provenance = fixture()
    with pytest.raises(consumer.ReceiptError, match='duplicate_key'):
        load(tmp_path, [row, deepcopy(row)], provenance)


def test_manifest_and_receipt_bytes_require_external_pins(tmp_path):
    row, provenance = fixture()
    pin = write_bundle(tmp_path, [row], provenance)
    with pytest.raises(consumer.ReceiptError, match='manifest_hash_mismatch'):
        consumer.load_bundle(tmp_path, manifest_sha256='0' * 64, expected_provenance=provenance, now=NOW)
    (tmp_path / 'receipts.jsonl').write_bytes(b'{}\n')
    with pytest.raises(consumer.ReceiptError, match='receipts_hash_mismatch'):
        consumer.load_bundle(tmp_path, manifest_sha256=pin, expected_provenance=provenance, now=NOW)


def test_old_bundle_requires_explicit_recorded_mode_and_future_is_always_rejected(tmp_path):
    row, provenance = fixture()
    pin = write_bundle(tmp_path, [row], provenance)
    opts = dict(manifest_sha256=pin, expected_provenance=provenance)
    with pytest.raises(consumer.ReceiptError, match='stale_artifact'):
        consumer.load_bundle(tmp_path, **opts, now=NOW + timedelta(days=4))
    index = consumer.load_bundle(tmp_path, **opts, now=NOW + timedelta(days=4), recorded_mode=True)
    assert index.lookup(*row['key'].values())['mode'] == 'recorded'
    with pytest.raises(consumer.ReceiptError, match='future_cutoff'):
        consumer.load_bundle(tmp_path, **opts, now=NOW - timedelta(days=1), recorded_mode=True)


def test_live_receipt_cannot_keep_using_outdated_projection_source(tmp_path):
    row, provenance = fixture()
    provenance['source_sha256']['workspace_next/diagnostic_receipts.py'] = '0' * 64
    with pytest.raises(consumer.ReceiptError, match='source_binding_mismatch'):
        load(tmp_path, [row], provenance)


def test_configuration_never_enables_display_without_explicit_approval(tmp_path, monkeypatch):
    row, provenance = fixture()
    query = row['key']
    monkeypatch.setattr(consumer, 'load_bundle', lambda *a, **k: pytest.fail('Read artifact before approval'))
    out = consumer.configured_lookup({'directory': tmp_path}, approved=False, **query)
    assert out['status'] == 'unavailable' and out['risk_tier'] is None


def test_configured_lookup_only_uses_backend_selected_artifact(tmp_path):
    row, provenance = fixture()
    pin = write_bundle(tmp_path, [row], provenance)
    config = dict(directory=tmp_path, manifest_sha256=pin, expected_provenance=provenance)
    out = consumer.configured_lookup(config, approved=True, now=NOW, **row['key'])
    assert out['status'] == 'diagnostic' and out['receipt']['detectors']['C']['score_raw_mse'] == 1
    with pytest.raises(consumer.ReceiptError, match='invalid_configuration'):
        consumer.configured_lookup({**config, 'extra_option': True}, approved=True, now=NOW, **row['key'])


@pytest.mark.parametrize('raw', ['{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}'])
def test_ambiguous_json_is_not_accepted(raw):
    with pytest.raises(consumer.ReceiptError, match='invalid_json'):
        consumer.strict_json(raw)
