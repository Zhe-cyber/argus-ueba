"""C11: independent producer -> consumer round trip.

Claude's real receipt generator writes a synthetic artifact (random-weight models, synthetic events); Codex's
consumer must accept it unchanged and reject each single, re-sealed corruption with its stable code. No real
store, model, archive or provider is touched, and production validation is never weakened.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3

import pytest

from scripts import clue_v2_reader as reader, live_receipts_clue_v2 as receipts
from scripts.tests.test_live_receipts_clue_v2 import AT, PERSONA, aws, bundle, cell, dates
from workspace_next import diagnostic_receipts as consumer

H = lambda c: c * 64
SCOPE = 'aws-acct'
NOW = AT + timedelta(hours=1)
SCORED_DAY, COLD_DAY, GAP_DAY = '2026-11-07', '2026-11-03', '2026-11-09'


def provenance():
    return {'profile': 'clue_ae_v2', 'detectors': {'B': {'model_sha256': H('1'), 'scaler_sha256': H('2')},
                                                  'C': {'model_sha256': H('3'), 'scaler_sha256': H('4')}},
            'preregistration_sha256': H('5'), 'training_manifest_sha256': H('6'), 'feature_contract_sha256': H('7'),
            'coverage_policy_sha256': H('8'), 'coverage_policy_version': 2, 'transform': receipts.TRANSFORM,
            'projection': 'shared_core_live_guard.project_live',
            'source_sha256': reader.source_hashes(receipts.RECEIPT_SOURCES)}  # current files: live mode verifies them


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    """Persona usable 1-8 Nov (scored from 6 Nov), plus a zero-event incomplete gap day on 9 Nov."""
    monkeypatch.setattr(receipts, 'ROOT', tmp_path)
    db = tmp_path / 'events.db'
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, source, source_account_id, account_key, event_id, '
                    'payload_digest, timestamp, action, resource, metadata, ingested_at)')
        for row in [aws(PERSONA, d) for d in dates('2026-11-01', 8)]:
            con.execute('INSERT INTO events (source,source_account_id,account_key,event_id,payload_digest,timestamp,'
                        'action,resource,metadata,ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?)', tuple(row.values()))
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'account_id': SCOPE, 'stack': 'argus-ueba-actors', 'ledger_dir': str(tmp_path)}))
    cells = [dict(cell(d, 'usable'), persona='persona-01') for d in dates('2026-10-30', 10)]
    cells.append(dict(cell(GAP_DAY, 'incomplete'), persona='persona-01', verified=0, missed=3))
    monkeypatch.setattr(receipts.policy, 'persona_account_keys', lambda *a: (
        {'persona-01': PERSONA}, {'unavailable_personas': [], 'invalid_key_rows': {}, 'late_or_unparseable_rows': {}}))
    monkeypatch.setattr(receipts.policy, 'persona_day_coverage', lambda *a: cells)
    monkeypatch.setattr(receipts, 'load_bundle', lambda *a: (bundle(), provenance()))
    out = tmp_path / 'data/receipts'
    receipts.run(db, config, 'prereg', 'training', out, at=AT)
    return out


def pin(folder):
    return hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest()


def load(folder, **options):
    return consumer.load_bundle(folder, manifest_sha256=options.pop('pin', None) or pin(folder),
                                expected_provenance=options.pop('expected', None) or provenance(),
                                now=options.pop('now', NOW), **options)


def rows_of(folder):
    return [json.loads(line) for line in (folder / 'receipts.jsonl').read_text(encoding='utf-8').splitlines()]


def reseal(folder, rows=None, raw=None, manifest_change=None, rehash_ids=True):
    """Rewrite receipts and re-seal manifest hash/counts, so a corruption reaches the check it targets."""
    if rows is not None:
        if rehash_ids:
            for row in rows:
                row['receipt_id'] = consumer.digest({k: row[k] for k in ('key', 'cutoff_utc', 'provenance')})
        raw = b''.join(receipts.canonical(row) + b'\n' for row in rows)
    manifest = json.loads((folder / 'manifest.json').read_bytes())
    if raw is not None:
        (folder / 'receipts.jsonl').write_bytes(raw)
        manifest.update(receipts_sha256=hashlib.sha256(raw).hexdigest(), receipts=len(raw.splitlines()))
        if rows is not None:
            manifest['scored_receipts'] = sum(bool(r['detectors']) for r in rows)
    if manifest_change:
        manifest_change(manifest)
    (folder / 'manifest.json').write_bytes(receipts.canonical(manifest) + b'\n')


def find(rows, day):
    return next(r for r in rows if r['key']['day'] == day)


# --- positive round trip ---------------------------------------------------------------------------

def test_generator_output_loads_unchanged_with_exact_lookup(artifact):
    index = load(artifact)
    scored = index.lookup('aws_cloudtrail', SCOPE, PERSONA, SCORED_DAY)
    assert scored['status'] == 'diagnostic' and scored['mode'] == 'live_diagnostic' and scored['risk_tier'] is None
    assert scored['history_scopes']['rolling_window_days'] == dates('2026-11-01', 6)
    assert index.lookup('aws_cloudtrail', SCOPE, PERSONA, COLD_DAY)['status'] == 'unscored'
    gap = index.lookup('aws_cloudtrail', SCOPE, PERSONA, GAP_DAY)
    assert gap['status'] == 'unscored' and gap['receipt']['coverage']['observed_events'] == 0
    missing = index.lookup('aws_cloudtrail', SCOPE, 'acct_' + 'e' * 64, SCORED_DAY)  # never another account's score
    assert missing['status'] == 'unavailable' and 'receipt' not in missing and missing['risk_tier'] is None
    assert index.lookup('github_events', SCOPE, PERSONA, SCORED_DAY)['status'] == 'unavailable'
    with pytest.raises(consumer.ReceiptError) as error:
        index.lookup('aws_cloudtrail', SCOPE, 'not-a-key', SCORED_DAY)
    assert error.value.code == 'invalid_query'


def test_stale_output_needs_explicit_recorded_mode(artifact):
    late = AT + timedelta(hours=49)
    with pytest.raises(consumer.ReceiptError, match='stale_artifact'):
        load(artifact, now=late)
    assert load(artifact, now=late, recorded_mode=True).lookup(
        'aws_cloudtrail', SCOPE, PERSONA, SCORED_DAY)['mode'] == 'recorded'
    with pytest.raises(consumer.ReceiptError, match='future_cutoff'):
        load(artifact, now=AT - timedelta(minutes=1))


def test_legacy_v1_loads_as_v1_and_v2_fields_are_checked(artifact):
    rows = rows_of(artifact)
    for row in rows:
        row['schema'] = 'clue_v2_live_diagnostic_receipt_v1'
        for name in ('expanding_history_days', 'rolling_window_days', 'feature_history_scope'):
            row['history'].pop(name)
    reseal(artifact, rows, manifest_change=lambda m: m.update(schema='clue_v2_live_diagnostic_receipt_v1_manifest'))
    result = load(artifact).lookup('aws_cloudtrail', SCOPE, PERSONA, SCORED_DAY)
    assert result['receipt']['schema'].endswith('_v1') and 'rolling_window_days' not in result['receipt']['history']


# --- single corruptions, each re-sealed to reach its own check -----------------------------------

def mutate_row(day, change):
    def apply(rows):
        change(find(rows, day))
        return rows
    return apply


def nan_term(rows):
    raw = b''.join(receipts.canonical(r) + b'\n' for r in rows)
    return raw.replace(b'"squared_residual":', b'"squared_residual":NaN,"x":', 1)


CASES = {
    'risk_tier_set': (mutate_row(SCORED_DAY, lambda r: r.update(risk_tier='High')), 'activation_not_allowed'),
    'alert_set': (mutate_row(SCORED_DAY, lambda r: r.update(alert=True)), 'activation_not_allowed'),
    'cold_start_forged_score': (lambda rows: find(rows, COLD_DAY).update(
        detectors=find(rows, SCORED_DAY)['detectors'], input=find(rows, SCORED_DAY)['input']) or rows, 'ineligible_score'),
    'incomplete_coverage_forged_score': (lambda rows: find(rows, GAP_DAY).update(
        detectors=find(rows, SCORED_DAY)['detectors'], input=find(rows, SCORED_DAY)['input'],
        features=find(rows, SCORED_DAY)['features']) or rows, 'ineligible_score'),
    'negative_term': (mutate_row(SCORED_DAY, lambda r: r['detectors']['C']['terms'][0].update(squared_residual=-1.0)),
                      'invalid_terms'),
    'additive_mismatch': (mutate_row(SCORED_DAY, lambda r: r['detectors']['C'].update(
        score_raw_mse=r['detectors']['C']['score_raw_mse'] * 1.5 + 0.01)), 'invalid_terms'),
    'share_mismatch': (mutate_row(SCORED_DAY, lambda r: r['detectors']['B']['terms'][0].update(
        share_of_reconstruction_error=0.999)), 'invalid_terms'),
    'rolling_not_last_28': (mutate_row(SCORED_DAY, lambda r: r['history'].update(rolling_window_days=[])),
                            'invalid_history'),
    'history_after_day': (mutate_row(COLD_DAY, lambda r: r['history'].update(
        prior_accepted_days=['2026-11-05'], expanding_history_days=['2026-11-05'],
        rolling_window_days=['2026-11-05'])), 'invalid_history'),
    'missing_why_unscored': (mutate_row(GAP_DAY, lambda r: r['input'].pop('why_unscored')), 'missing_reason'),
    'altered_cutoff': (mutate_row(SCORED_DAY, lambda r: r.update(cutoff_utc='2026-11-09T04:00:00+00:00')),
                       'receipt_binding_mismatch'),
    'wrong_source': (mutate_row(SCORED_DAY, lambda r: r['key'].update(source='okta_logs')), 'invalid_key'),
    'malformed_account': (mutate_row(SCORED_DAY, lambda r: r['key'].update(account='acct_persona-01')), 'invalid_key'),
    'open_day': (mutate_row(SCORED_DAY, lambda r: r['key'].update(day='2026-11-10')), 'open_day'),
}


@pytest.mark.parametrize('case', sorted(CASES))
def test_single_corruption_is_rejected_with_its_code(artifact, case):
    change, code = CASES[case]
    reseal(artifact, change(rows_of(artifact)))
    with pytest.raises(consumer.ReceiptError) as error:
        load(artifact)
    assert error.value.code == code


def test_nonfinite_and_duplicate_key_json_are_rejected(artifact):
    reseal(artifact, raw=nan_term(rows_of(artifact)))
    with pytest.raises(consumer.ReceiptError, match='invalid_json'):
        load(artifact)


def test_duplicate_account_day_is_rejected(artifact):
    rows = rows_of(artifact)
    reseal(artifact, rows + [find(rows, SCORED_DAY)])
    with pytest.raises(consumer.ReceiptError, match='duplicate_key'):
        load(artifact)


def test_changed_key_without_new_receipt_id_is_rejected(artifact):
    rows = rows_of(artifact)
    find(rows, SCORED_DAY)['key']['scope'] = 'other-scope'
    reseal(artifact, rows, rehash_ids=False)
    with pytest.raises(consumer.ReceiptError, match='receipt_id_mismatch'):
        load(artifact)


def test_body_and_manifest_tampering_fail_the_pins(artifact):
    original_pin = pin(artifact)
    body = (artifact / 'receipts.jsonl').read_bytes()
    (artifact / 'receipts.jsonl').write_bytes(body.replace(b'"alert":false', b'"alert":false ', 1))
    with pytest.raises(consumer.ReceiptError, match='receipts_hash_mismatch'):
        load(artifact)
    (artifact / 'receipts.jsonl').write_bytes(body)
    reseal(artifact, manifest_change=lambda m: m.update(scored_receipts=m['scored_receipts']))  # bytes may differ
    (artifact / 'manifest.json').write_bytes((artifact / 'manifest.json').read_bytes() + b' ')
    with pytest.raises(consumer.ReceiptError, match='manifest_hash_mismatch'):
        load(artifact, pin=original_pin)


def test_count_and_schema_mismatches_are_rejected(artifact):
    reseal(artifact, manifest_change=lambda m: m.update(scored_receipts=m['scored_receipts'] + 1))
    with pytest.raises(consumer.ReceiptError, match='receipt_count_mismatch'):
        load(artifact)
    reseal(artifact, manifest_change=lambda m: m.update(scored_receipts=m['scored_receipts'] - 1,
                                                        schema='clue_v2_live_diagnostic_receipt_v3_manifest'))
    with pytest.raises(consumer.ReceiptError, match='unsupported_schema'):
        load(artifact)


@pytest.mark.parametrize('field', ['model', 'policy', 'projection'])
def test_trust_pin_disagreement_is_rejected(artifact, field):
    expected = provenance()
    if field == 'model':
        expected['detectors']['C']['model_sha256'] = H('9')
    elif field == 'policy':
        expected['coverage_policy_sha256'] = H('9')
    else:
        expected['projection'] = 'some_other_projection'
    with pytest.raises(consumer.ReceiptError, match='provenance_mismatch'):
        load(artifact, expected=expected)


def test_stale_code_binding_fails_live_mode_but_loads_as_recorded(artifact):
    stale = provenance()
    stale['source_sha256']['scripts/explain_clue_v2.py'] = H('0')
    rows = rows_of(artifact)
    for row in rows:
        row['provenance'] = stale
    reseal(artifact, rows, manifest_change=lambda m: m.update(provenance=stale))
    with pytest.raises(consumer.ReceiptError, match='source_binding_mismatch'):
        load(artifact, expected=stale)
    assert load(artifact, expected=stale, recorded_mode=True).recorded is True


def test_escaping_source_path_fails_closed(artifact):
    escaping = provenance()
    escaping['source_sha256'] = {'../outside.py': H('0')}
    rows = rows_of(artifact)
    for row in rows:
        row['provenance'] = escaping
    reseal(artifact, rows, manifest_change=lambda m: m.update(provenance=escaping))
    with pytest.raises(consumer.ReceiptError, match='source_binding_mismatch'):
        load(artifact, expected=escaping)


def test_more_than_28_accepted_days_round_trip(tmp_path, monkeypatch):
    persona_days = dates('2026-10-30', 35)
    at = datetime(2026, 12, 10, 4, 0, tzinfo=timezone.utc)
    days, _, _ = receipts.audit.closed_days([aws(PERSONA, d) for d in persona_days], at)
    built = receipts.build_receipts(days, at, bundle(), provenance(), {(PERSONA, d): cell(d, 'usable') for d in persona_days},
                                    {PERSONA}, SCOPE)
    folder = tmp_path / 'artifact'
    folder.mkdir()
    body = b''.join(receipts.canonical(r) + b'\n' for r in built)
    (folder / 'receipts.jsonl').write_bytes(body)
    manifest = {'schema': receipts.SCHEMA + '_manifest', 'cutoff_utc': at.isoformat(), 'label': receipts.LABEL,
                'receipts': len(built), 'receipts_sha256': hashlib.sha256(body).hexdigest(),
                'scored_receipts': sum(bool(r['detectors']) for r in built), 'provenance': provenance(),
                'live_activation': False, 'alerts_created': False}
    (folder / 'manifest.json').write_bytes(receipts.canonical(manifest) + b'\n')
    result = load(folder, now=at + timedelta(hours=1)).lookup('aws_cloudtrail', SCOPE, PERSONA, persona_days[-1])
    assert result['status'] == 'diagnostic'
    assert result['history_scopes']['expanding_history_days'] == persona_days[:34]
    assert result['history_scopes']['rolling_window_days'] == persona_days[6:34]
