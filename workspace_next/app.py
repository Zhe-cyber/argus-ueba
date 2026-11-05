"""Isolated API on an explicitly marked DB copy; never import the live main app."""
import json
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from fastapi.middleware.cors import CORSMiddleware
from backend import event_store as store
from workspace_next import case_store
from workspace_next.case_api import router
from workspace_next import operations
from workspace_next import diagnostic_receipts


class RetainDiagnostic(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: str = Field(max_length=64)
    scope: str = Field(min_length=1, max_length=256)
    account: str = Field(max_length=128)
    day: str = Field(max_length=10)
    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)
    request_key: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)
    receipt_id: str = Field(pattern='^[0-9a-f]{64}$')
    artifact_manifest_sha256: str = Field(pattern='^[0-9a-f]{64}$')


def create_app():
    if store._PG:
        raise RuntimeError('Workspace preview requires SQLite copy')
    path=Path(os.environ['ARGUS_WORKSPACE_COPY_DB']).resolve(strict=True)
    marker=path.parent/'workspace-copy.json'
    if path.name!='preview.db' or not marker.is_file():
        raise RuntimeError('Explicit workspace copy marker required')
    declaration=json.loads(marker.read_text(encoding='utf-8'))
    if declaration.get('copy_db')!=str(path) or declaration.get('not_live') is not True:
        raise RuntimeError('Invalid workspace copy marker')
    store.DB_PATH=path
    case_store.init_db()
    app=FastAPI(title='Argus workspace — isolated copy')
    app.state.diagnostic_receipt_config = None
    app.state.experimental_diagnostics_approved = False
    receipt_config = path.parent / 'diagnostic-receipts-config.json'
    if receipt_config.is_file():
        if receipt_config.stat().st_size > 64000:
            raise RuntimeError('Diagnostic configuration too large')
        app.state.diagnostic_receipt_config = diagnostic_receipts.strict_json(receipt_config.read_bytes())
    def current_receipt_config():
        # The trusted local job replaces this file atomically; no browser setter exists.
        if receipt_config.is_file():
            if receipt_config.stat().st_size > 64000:
                raise diagnostic_receipts.ReceiptError('invalid_configuration')
            return diagnostic_receipts.strict_json(receipt_config.read_bytes())
        return app.state.diagnostic_receipt_config
    app.add_middleware(CORSMiddleware,allow_origins=[os.environ.get('ARGUS_WORKSPACE_UI_ORIGIN','http://127.0.0.1:3011')],
                       allow_methods=['GET','POST','PATCH'],allow_headers=['Content-Type'])
    app.include_router(router)

    @app.get('/workspace/status')
    def status():
        return {'mode':'isolated_copy','live_cutover':False}

    @app.get('/workspace/connections')
    def connections():
        return operations.connections(path.parent/'operations-snapshot.json')

    @app.get('/workspace/overview')
    def overview():
        return operations.overview(path.parent/'operations-snapshot.json')

    @app.get('/workspace/diagnostics')
    def diagnostic(source: str, scope: str, account: str, day: str):
        try:
            return diagnostic_receipts.configured_lookup(
                current_receipt_config(),
                approved=app.state.experimental_diagnostics_approved,
                source=source, scope=scope, account=account, day=day)
        except diagnostic_receipts.ReceiptError as error:
            if error.code == 'invalid_query':
                raise HTTPException(422, 'Invalid diagnostic account-day query') from error
            return {'status': 'unavailable', 'reason': 'Diagnostic artifact unavailable.',
                    'reason_code': error.code, 'live_activation': False, 'risk_tier': None}

    @app.get('/workspace/diagnostic-availability')
    def availability(source: str, scope: str, account: str, day: str):
        try:
            config = current_receipt_config()
            result = diagnostic_receipts.availability_lookup(config,
                source=source, scope=scope, account=account, day=day)
            result['score_display_approved'] = app.state.experimental_diagnostics_approved
            if 'receipt' in result:
                result['artifact_manifest_sha256'] = config['manifest_sha256']
            return result
        except diagnostic_receipts.ReceiptError as error:
            if error.code == 'invalid_query':
                raise HTTPException(422, 'Invalid diagnostic account-day query') from error
            return {'status': 'unavailable', 'reason': 'Diagnostic artifact unavailable.',
                    'reason_code': error.code, 'live_activation': False, 'risk_tier': None, 'scores_visible': False}

    @app.post('/cases/{case_id}/diagnostics')
    def retain_diagnostic(case_id: str, body: RetainDiagnostic):
        from workspace_next.case_api import call
        def retain():
            config = current_receipt_config()
            if config is None or config.get('manifest_sha256') != body.artifact_manifest_sha256:
                raise case_store.CaseConflict('Diagnostic artifact changed; reload account-day context')
            query = body.model_dump(include={'source', 'scope', 'account', 'day'})
            if app.state.experimental_diagnostics_approved:
                result = diagnostic_receipts.configured_lookup(config, approved=True, **query)
            else:
                result = diagnostic_receipts.availability_lookup(config, **query)
            if 'receipt' not in result:
                raise ValueError('No validated account-day context to retain')
            if result['receipt']['receipt_id'] != body.receipt_id:
                raise case_store.CaseConflict('Diagnostic receipt changed; reload account-day context')
            snapshot = {**result, 'artifact_manifest_sha256': config['manifest_sha256'],
                        'association': 'account_day_context_not_trigger_attribution'}
            return case_store.retain_diagnostic(case_id, body.expected_version, body.actor,
                body.request_key, body.reason, snapshot)
        return call(retain)
    return app
