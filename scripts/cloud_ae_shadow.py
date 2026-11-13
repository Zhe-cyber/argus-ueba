"""Local, finite, read-only AWS engineering inference. Never assigns risk tiers."""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import html
import json
import math
from pathlib import Path
import re
import secrets
import sqlite3
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.cloud_feature_extractor import CLOUD_FEATURES, aggregate_window

END = datetime(2026, 11, 14, 16, tzinfo=timezone.utc)  # 15 Nov midnight MY
MAX_EVENTS = 100000
ARTIFACTS = ('cloud_ae_v1.pt', 'cloud_scaler_v1.pkl', 'cloud_ae_metrics.json')
SOURCES = ('scripts/cloud_ae_shadow.py', 'backend/cloud_feature_extractor.py', 'scripts/train_cloud_ae.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temp.write_bytes(value.encode('utf-8'))
    temp.replace(path)


def json_text(value):
    return json.dumps(value, indent=2, allow_nan=False) + '\n'


def source_hashes():
    return {name: sha(ROOT / name) for name in SOURCES}


def validate(cfg):
    if (cfg.get('schema') != 'argus_cloud_ae_shadow_v1'
            or cfg.get('end_utc') != END.isoformat()
            or re.fullmatch('[0-9]{12}', cfg.get('account_id', '')) is None
            or re.fullmatch('[0-9a-f]{64}', cfg.get('alias_key', '')) is None
            or cfg.get('source_sha256') != source_hashes()):
        raise ValueError('Shadow config/source contract changed')
    if set(cfg.get('artifacts', {})) != set(ARTIFACTS):
        raise ValueError('Pinned local artifacts required')
    for name, entry in cfg['artifacts'].items():
        path = Path(entry['path'])
        if path.name != name or sha(path) != entry['sha256']:
            raise ValueError('Model artifact changed')
    if Path(cfg['database']).resolve().parent == Path(cfg['output_dir']).resolve():
        raise ValueError('Keep outputs separate from connected store')
    return cfg


def read_snapshot(database, account, now, limit=MAX_EVENTS):
    """One bounded snapshot; no environment-driven event_store connection."""
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        rows = db.execute('''SELECT timestamp,user,source,action,resource,ip_address,metadata,source_account_id,event_id
            FROM events WHERE source='aws_cloudtrail' AND source_account_id=?
            ORDER BY timestamp,id LIMIT ?''', (account, limit + 1)).fetchall()
        db.rollback()
    if len(rows) > limit:
        raise ValueError('Snapshot limit exceeded; refusing truncated history')
    if not rows:
        raise ValueError('No observed AWS data in configured account')
    events = []
    for row in rows:
        event = dict(row)
        stamp = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp > now:
            raise ValueError('Unzoned or future event timestamp')
        event['_utc_day'] = stamp.astimezone(timezone.utc).date().isoformat()
        metadata = json.loads(event['metadata']) if event['metadata'] else {}
        if not isinstance(metadata, dict):
            raise ValueError('Stored metadata must be an object')
        event['metadata'] = metadata
        events.append(event)
    return events


def prepare(events, key, now):
    grouped = defaultdict(list)
    excluded = 0
    for event in events:
        if not isinstance(event['user'], str) or not event['user'].strip():
            excluded += 1
            continue
        grouped[(event['source_account_id'], event['user'])].append(event)
    rows, matrix = [], []
    for identity, own in sorted(grouped.items()):
        day = max(e['_utc_day'] for e in own)
        window = [e for e in own if e['_utc_day'] == day]
        history = [e for e in own if e['_utc_day'] < day]
        features = aggregate_window(window, history=history)
        vector = [features[name] for name in CLOUD_FEATURES]
        if any(not math.isfinite(v) or v < 0 for v in vector):
            raise ValueError('Invalid feature counts')
        alias = hmac.new(bytes.fromhex(key), json.dumps(identity).encode(), hashlib.sha256).hexdigest()[:16]
        rows.append({'account_alias': 'aws-' + alias, 'latest_utc_day': day,
                     'partial_current_utc_day': day == now.date().isoformat(),
                     'observed_window_events': len(window), 'observed_prior_events': len(history),
                     'history_days_observed': len({e['_utc_day'] for e in history}),
                     'window_completeness': 'unverified', 'risk_level': 'Unknown', 'review_priority': None})
        matrix.append(vector)
    if not rows:
        raise ValueError('No attributable principals; no inference performed')
    return rows, matrix, excluded


def infer(cfg, matrix):
    import joblib
    import numpy as np
    import torch
    from sklearn.preprocessing import StandardScaler
    from scripts.train_cloud_ae import _build_cloud_ae
    paths = {name: Path(entry['path']) for name, entry in cfg['artifacts'].items()}
    # Only locally trusted, explicitly hash-pinned artifacts. Never fetch a pickle.
    checkpoint = torch.load(paths['cloud_ae_v1.pt'], map_location='cpu', weights_only=True)
    if checkpoint.get('input_dim') != 12 or checkpoint.get('features') != CLOUD_FEATURES:
        raise ValueError('Checkpoint feature contract differs')
    scaler = joblib.load(paths['cloud_scaler_v1.pkl'])
    if (type(scaler) is not StandardScaler or scaler.n_features_in_ != 12
            or scaler.mean_.shape != (12,) or scaler.scale_.shape != (12,)
            or not np.isfinite(scaler.mean_).all() or not np.isfinite(scaler.scale_).all()
            or (scaler.scale_ <= 0).any()):
        raise ValueError('Unsupported scaler contract')
    model = _build_cloud_ae(12)
    model.load_state_dict(checkpoint['state_dict'], strict=True)
    model.eval()
    values = np.asarray(matrix, dtype=np.float32)
    if values.ndim != 2 or values.shape[1] != 12 or not np.isfinite(values).all():
        raise ValueError('Invalid input matrix')
    scaled = scaler.transform(values).astype(np.float32)
    if not np.isfinite(scaled).all():
        raise ValueError('Nonfinite scaled features')
    tensor = torch.tensor(scaled)
    with torch.inference_mode():
        residuals = ((model(tensor) - tensor) ** 2).numpy()
    if residuals.shape != scaled.shape or not np.isfinite(residuals).all():
        raise ValueError('Invalid model residuals')
    return [{'raw_reconstruction_mse': float(r.mean()),
             'maximum_absolute_standardized_feature': float(np.abs(scaled[i]).max()),
             'largest_residual_features': [CLOUD_FEATURES[j] for j in np.argsort(r)[-3:][::-1]]}
            for i, r in enumerate(residuals)]


def render(report, attempt_status=None):
    esc = lambda value: html.escape(str(value), quote=True)
    body = ''.join('<tr>' + ''.join(f'<td>{esc(value)}</td>' for value in (
        row['account_alias'], row['latest_utc_day'],
        'Partial UTC day' if row['partial_current_utc_day'] else 'Historical observed day',
        row['observed_window_events'], row['history_days_observed'],
        f"{row['raw_reconstruction_mse']:.7g}", ', '.join(row['largest_residual_features']))) + '</tr>'
        for row in sorted(report['accounts'], key=lambda r: r['raw_reconstruction_mse'], reverse=True))
    notice = ('<p class="label">' + esc(attempt_status) + '</p>') if attempt_status else ''
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="refresh" content="60">
<title>Argus | Live AWS shadow scores</title><style>
body{font:16px system-ui;background:#101a28;color:#edf3fb;margin:36px}h1{font-size:30px;margin-bottom:8px}
p{max-width:1050px;line-height:1.55}.label{color:#78d6d0}table{width:100%;border-collapse:collapse;margin:24px 0;font-size:14px}
th,td{text-align:left;padding:13px;border-bottom:1px solid #324258}th{color:#8bc4ef}small{color:#b9c8da}
</style><h1>Argus · Live AWS shadow scores</h1><p class="label">Real inference · Provisional engineering output</p>
<p>The legacy cloud autoencoder is processing collected AWS activity. These numbers measure reconstruction error;
they are not compromise probabilities or validated review priorities. All account risk remains Unknown.</p>
''' + notice + '''<p id="freshness">Last successful snapshot: ''' + esc(report['computed_at_utc']) + '''</p>
<p>''' + esc(report['observed_snapshot_events']) + ''' observed events · ''' + esc(len(report['accounts'])) + ''' attributable principals · ''' + esc(report['unattributable_events_excluded']) + ''' events without an attributable identity, excluded from scoring.</p>
<table><thead><tr><th>Principal alias</th><th>UTC activity date</th><th>Window</th><th>Events</th><th>Prior observed days</th><th>Raw AE MSE</th><th>Largest residual features</th></tr></thead><tbody>''' + body + '''</tbody></table>
<p>Model: legacy flaws.cloud AWS benchmark AE (12 → 32 → 16 → 8 → 16 → 32 → 12), StandardScaler.
No live threshold is applied. Only AWS is scored. Cloudflare and GitHub collection is separate.</p>
<p>Coverage is unverified. Setup and collector activity may be present. A closed date does not establish complete collection or a normal baseline.
Residual features are reconstruction differences, not SHAP explanations. UTC windows preserve the legacy extractor contract.</p>
<small>Local private view · no raw identities, IP addresses or resources · refreshes this page every minute; scoring scheduled every 30 minutes while the laptop is awake.</small>
<script>const stamp=''' + json.dumps(report['computed_at_utc']) + ''';
const age=(Date.now()-Date.parse(stamp))/60000;
if(age>60){document.getElementById('freshness').textContent='STALE — last successful snapshot '+stamp+'; inspect last_attempt.json for failures or expiry.';}
</script></html>'''


def run(cfg, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if now >= END:
        return {'status': 'shadow_expired', 'model_activated': False}
    validate(cfg)  # before deserialisation or database access
    events = read_snapshot(cfg['database'], cfg['account_id'], now)
    rows, matrix, excluded = prepare(events, cfg['alias_key'], now)
    scores = infer(cfg, matrix)
    if len(scores) != len(rows):
        raise ValueError('Inference row mismatch')
    for row, score in zip(rows, scores):
        if not math.isfinite(score['raw_reconstruction_mse']) or score['raw_reconstruction_mse'] < 0:
            raise ValueError('Invalid score')
        row.update(score)
    validate(cfg)  # refuse drift during inference
    report = {'schema': 'argus_cloud_ae_shadow_report_v1', 'status': 'provisional_engineering_inference',
              'computed_at_utc': now.isoformat(), 'activated': False, 'risk_thresholds_applied': False,
              'source': 'aws_cloudtrail', 'window_timezone': 'UTC', 'window_completeness': 'unverified',
              'observed_snapshot_events': len(events), 'unattributable_events_excluded': excluded,
              'snapshot_sha256': hashlib.sha256(json.dumps(events, sort_keys=True).encode()).hexdigest(),
              'artifact_sha256': {name: entry['sha256'] for name, entry in cfg['artifacts'].items()},
              'source_sha256': cfg['source_sha256'], 'accounts': rows,
              'limitations': ['Legacy benchmark transfer unvalidated; training feature-code provenance unauthenticated.',
                              'Setup/collector traffic is not a verified normal user baseline.',
                              'Partial current UTC days and incomplete historical coverage are not calibrated risk.',
                              'No cross-cloud identity fusion, SHAP or detection-performance claim.']}
    output = Path(cfg['output_dir'])
    atomic(output / 'latest.json', json_text(report))
    atomic(output / 'latest.html', render(report))
    return {'status': 'success', 'computed_at_utc': now.isoformat(), 'principals': len(rows),
            'events': len(events), 'model_activated': False}


def initialize(config, pilot_config, artifacts, output):
    config, output = Path(config).resolve(), Path(output).resolve()
    if config.exists() or output.exists() or config.parent != output:
        raise ValueError('Require a new dedicated shadow output directory and config')
    pilot = json.loads(Path(pilot_config).read_text())
    cfg = {'schema': 'argus_cloud_ae_shadow_v1', 'account_id': pilot['account_id'],
           'database': str(Path(pilot['connected_dir']) / 'events.db'), 'output_dir': str(output),
           'alias_key': secrets.token_hex(32), 'end_utc': END.isoformat(), 'pythonw': pilot['pythonw'],
           'source_sha256': source_hashes(), 'artifacts': {
               name: {'path': str((Path(artifacts) / name).resolve()), 'sha256': sha(Path(artifacts) / name)}
               for name in ARTIFACTS}}
    validate(cfg)
    output.mkdir(parents=True)
    atomic(config, json_text(cfg))
    return {'configured': True, 'model_activated': False}


def mark_attempt(attempt, result):
    record = {**result, 'attempted_at_utc': datetime.now(timezone.utc).isoformat()}
    atomic(attempt, json_text(record))
    if result['status'] != 'success':
        previous = attempt.parent / 'latest.json'
        if previous.exists():
            report = json.loads(previous.read_text())
            atomic(attempt.parent / 'latest.html', render(report,
                   'Latest attempt: ' + result['status'] + ' at ' + record['attempted_at_utc']
                   + '. Showing previous successful output only.'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['init', 'tick'])
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--pilot-config', type=Path)
    parser.add_argument('--artifacts', type=Path)
    args = parser.parse_args()
    if args.mode == 'init':
        if args.pilot_config is None or args.artifacts is None:
            parser.error('init requires --pilot-config and --artifacts (trusted local files only)')
        print(json.dumps(initialize(args.config, args.pilot_config, args.artifacts, args.config.parent)))
        return 0
    # Attempt marker lives beside known config, never follows an unchecked output path.
    attempt = args.config.resolve().parent / 'last_attempt.json'
    try:
        cfg = json.loads(args.config.read_text())
        if Path(cfg['output_dir']).resolve() != args.config.resolve().parent:
            raise ValueError('Output/config directories differ')
        result = run(cfg)
    except Exception as error:
        # Keep raw provider identities/paths and exception messages out of public output.
        result = {'status': 'failed', 'error_type': type(error).__name__, 'model_activated': False}
        mark_attempt(attempt, result)
        print(json.dumps(result))
        return 1
    mark_attempt(attempt, result)
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
