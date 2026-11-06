"""POC readiness → diagnostic context → case decision on synthetic copied stores."""
from copy import deepcopy
from datetime import datetime
import json
import shutil

import pytest
from fastapi import HTTPException

from backend import event_store
from backend.tests.test_case_workspace import db, create
from backend.tests.test_diagnostic_receipts import fixture, write_bundle, NOW
from workspace_next import app as workspace_app, case_store, diagnostic_receipts as consumer


@pytest.fixture
def context(db, tmp_path, monkeypatch):
    preview = tmp_path / 'preview.db'
    shutil.copyfile(db, preview)
    (tmp_path / 'workspace-copy.json').write_text(json.dumps({'copy_db': str(preview), 'not_live': True}))
    monkeypatch.setenv('ARGUS_WORKSPACE_COPY_DB', str(preview))
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(consumer, 'datetime', Clock)
    row, provenance = fixture()
    artifact = tmp_path / 'receipt-artifact'
    pin = write_bundle(artifact, [row], provenance)
    config = dict(directory=str(artifact), manifest_sha256=pin, expected_provenance=provenance)
    app = workspace_app.create_app()
    app.state.diagnostic_receipt_config = config
    routes = {route.path: route.endpoint for route in app.routes}
    return app, routes, row, pin


def test_readiness_exposes_history_and_never_scores_before_display_approval(context):
    app, routes, row, pin = context
    out = routes['/workspace/diagnostic-availability'](**row['key'])
    assert out['status'] == 'unscored' and not out['score_display_approved']
    assert out['receipt']['detectors'] == {} and out['receipt']['features'] is None
    assert out['history_scopes']['rolling_window_days'] == row['history']['rolling_window_days']
    assert 'pending approval' in out['receipt']['input']['why_unscored']
    assert out['artifact_manifest_sha256'] == pin
    assert routes['/workspace/diagnostics'](**row['key'])['status'] == 'unavailable'


def command(row, pin, version=1, key='retain-one'):
    return workspace_app.RetainDiagnostic(**row['key'], actor='Test analyst', reason='Review account-day context',
        request_key=key, expected_version=version, receipt_id=row['receipt_id'], artifact_manifest_sha256=pin)


def test_case_retains_validated_context_with_exact_retry_and_decision(context):
    app, routes, row, pin = context
    case = create()
    body = command(row, pin)
    retained = routes['/cases/{case_id}/diagnostics'](case['id'], body)
    assert retained['version'] == 2 and len(retained['links']) == 1
    link = retained['links'][0]
    assert link['kind'] == 'diagnostic'
    assert link['snapshot']['association'] == 'account_day_context_not_trigger_attribution'
    assert link['snapshot']['receipt']['detectors'] == {}
    assert link['snapshot']['artifact_manifest_sha256'] == pin
    assert routes['/cases/{case_id}/diagnostics'](case['id'], body) == retained
    finished = case_store.update(case['id'], 2, 'Test analyst', 'decision', {
        'status': 'Closed', 'resolution': 'Insufficient evidence', 'closing_reason': 'Context retained; no compromise inferred.'})
    assert finished['status'] == 'Closed' and finished['links'] == retained['links']
    assert len(finished['history']) == 3


def test_stale_version_and_changed_artifact_cannot_overwrite_case(context):
    app, routes, row, pin = context
    case = create()
    retained = routes['/cases/{case_id}/diagnostics'](case['id'], command(row, pin))
    with pytest.raises(HTTPException) as conflict:
        routes['/cases/{case_id}/diagnostics'](case['id'], command(row, pin, key='different-request'))
    assert conflict.value.status_code == 409
    with pytest.raises(HTTPException) as changed:
        routes['/cases/{case_id}/diagnostics'](case['id'], command(row, 'f' * 64, version=2, key='changed-artifact'))
    assert changed.value.status_code == 409
    assert case_store.get(case['id']) == retained


def test_browser_cannot_supply_its_own_score_or_receipt_payload(context):
    app, routes, row, pin = context
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        workspace_app.RetainDiagnostic(**command(row, pin).model_dump(), score_raw_mse=999)
    missing = dict(row['key'], day='2026-10-30')
    assert routes['/workspace/diagnostic-availability'](**missing)['status'] == 'unavailable'


def test_atomic_artifact_pointer_refresh_is_visible_without_restart(context, tmp_path):
    app, routes, row, pin = context
    newer = deepcopy(row)
    newer['key']['day'] = '2026-10-29'
    newer['history'].update(prior_accepted_days=[], expanding_history_days=[], rolling_window_days=[])
    newer['input'] = {'status': 'cold_start', 'five_feature_eligible': False, 'nine_feature_eligible': False,
                      'why_unscored': 'Insufficient history: 0 of 5 usable prior days.'}
    newer['detectors'], newer['features'] = {}, None
    artifact = tmp_path / 'new-receipt-artifact'
    new_pin = write_bundle(artifact, [newer], newer['provenance'])
    pointer = {'directory': str(artifact), 'manifest_sha256': new_pin, 'expected_provenance': newer['provenance']}
    (tmp_path / 'diagnostic-receipts-config.json').write_bytes(consumer.canonical(pointer))
    refreshed = routes['/workspace/diagnostic-availability'](**newer['key'])
    assert refreshed['artifact_manifest_sha256'] == new_pin
    assert refreshed['receipt']['input']['why_unscored'].startswith('Insufficient history: 0')
    assert not refreshed['score_display_approved']
    assert routes['/workspace/diagnostic-availability'](**row['key'])['status'] == 'unavailable'
