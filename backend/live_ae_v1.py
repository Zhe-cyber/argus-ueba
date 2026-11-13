"""Live autoencoder v1 (L10) -- HISTORY ONLY since 13 Nov 2026. Replaced by backend/live_ae.py (v2) before any
evaluation scenario; kept so its bundle (bundle-20261113T003343) stays loadable and explainable. The running
scorer, the ingest hook, the mirror and the workspace use v2; nothing in the product calls this module.

v1: an "ML anomaly score" per AWS lab persona account-day. Comparator only: it never raises alerts, never changes
the baseline risk score and never feeds a tier.

Model and data are the V3 study's, imported read-only (those files are hash-bound to the closed study):
  - features: scripts/aws_lab_daily_features.extract (8 MYT-day counts, contract aws_lab_daily_v1)
  - training data: scripts/export_live_daily.export partitions as they are (fit 1-7 Nov, validation 8-9 Nov,
    normal calibration 10-12 Nov), all usable persona rows. Unlike V3 there is NO all-six-roles history gate;
    each persona still needs >= 5 fitting rows. Rows with missing/invalid source IPs are excluded (annex rule).
  - model: scripts/train_live_daily.fit_ae unchanged (8-4-2-4-8 Tanh AE, 98 parameters, log1p + fit-only
    standardisation, seed 42, full-batch Adam, earliest-minimum validation checkpoint)
  - threshold: scripts/live_daily_method.empirical_threshold on the calibration scores (k = floor(0.05 n) days
    may lie above it; a day is flagged when its score is STRICTLY greater)
Score = mean squared reconstruction error in the standardised space (the V3 'ae' score). Explanation = each
feature's share of that squared error (shares sum to 1).

Storage: table ml_scores (backend/event_store.py), one row per persona (account_key, MYT day). Written by the
ingest hook (on_event, best effort) when ARGUS_LIVE_AE_BUNDLE names a bundle, by the workspace mirror pass, and by
the backfill command. Accounts that are not AWS lab persona roles get no row (not_applicable).

    python -m backend.live_ae_v1 train --export <export dir> --out <fresh bundle dir> [--synthetic]
    python -m backend.live_ae_v1 backfill --bundle <bundle dir> --db <sqlite workspace copy> [--allow-synthetic]
    python -m backend.live_ae_v1 pipeline --pilot-config <config.json> --out-root <dir> [--demo-db <copy>]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.metadata import version
import json
import logging
import math
import os
from pathlib import Path
import re

from scripts import aws_study_v3 as protocol, export_live_daily as exporter
from scripts import live_daily_method as method, train_live_daily as v3
from scripts.aws_lab_daily_features import CONTRACT, FEATURES, extract
from scripts.simulation_lab import buckets, validate_scope

_log = logging.getLogger(__name__)
Refusal = v3.Refusal
MYT = timezone(timedelta(hours=8))
PROFILE = 'argus_live_ae_v1'
PURPOSE = 'product comparator, not alerting'
WINDOWS = protocol.WINDOWS
MIN_FIT_ROWS = 5
REAL_NOT_BEFORE = datetime(2026, 11, 13, 0, 30, tzinfo=MYT)  # owner rule: real training only after this
ARTIFACTS = ('weights.pt', 'scaler.json')
ROOT = Path(__file__).resolve().parent.parent
LABELS = {'event_count': 'total reads', 'get_object_count': 'object downloads', 'head_object_count': 'object checks',
          'get_bucket_location_count': 'bucket lookups', 'unique_resources': 'distinct buckets',
          'unique_valid_ips': 'distinct source IPs', 'off_hours_events': 'off-hours events',
          'confidential_bucket_reads': 'confidential reads'}
_PERSONA_ARN = re.compile(r'arn:aws:sts::(\d{12}):assumed-role/(argus-[a-z0-9-]+)-(persona-0[1-6])/[^/]+')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frozen_hashes():
    """sha256 of every imported frozen V3 source (feature extraction, export, fitting, threshold rule)."""
    return {**exporter.hashes(), **v3.source_hashes()}


# --- training --------------------------------------------------------------------------------------------

def load_export(directory, now=None):
    """Validated export partitions WITHOUT the V3 six-role gate. Returns (parts, excluded rows)."""
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    raw = (directory / 'dataset.json').read_bytes()
    data = json.loads(raw)
    try:
        protocol.require_binding(data)
        protocol.require_binding(manifest)
    except ValueError as exc:
        raise Refusal('Export study binding differs') from exc
    if (hashlib.sha256(raw).hexdigest() != manifest.get('dataset_sha256')
            or sha(directory / 'feature_contract.json') != v3.CONTRACT_SHA
            or data.get('feature_contract_sha256') != v3.CONTRACT_SHA or data.get('profile') != CONTRACT['profile']
            or data.get('provenance', {}).get('source_sha256') != exporter.hashes()):
        raise Refusal('Export dataset/contract/source binding differs')
    today = (now or datetime.now(timezone.utc)).astimezone(MYT).date().isoformat()
    usable = {(r['day'], r['persona']) for r in data['readiness']['days'] if r['status'] == 'usable'}
    parts, excluded, seen = {p: [] for p in WINDOWS}, [], set()
    for row in data['rows']:
        key = row['date_local'], row['persona']
        if key in seen or row['persona'] not in method.ROLES or key not in usable:
            raise Refusal('Duplicate, unknown or unaudited account-day')
        seen.add(key)
        start, end = WINDOWS.get(row['partition'], ('~', ''))
        if not start <= key[0] <= end or key[0] >= today or row.get('complete_day') is not True:
            raise Refusal('Wrong partition or open date')
        values = row['features']
        if set(values) != set(FEATURES) or any(type(v) is not int or v < 0 for v in values.values()) or values['event_count'] < 1:
            raise Refusal('Invalid count vector')
        ip = row['ip_observability']
        if ip['missing_events'] or ip['invalid_events']:
            excluded.append({'persona': key[1], 'date_local': key[0], 'reason': 'incomplete_ip_observability'})
            continue
        parts[row['partition']].append(row)
    if seen != usable:
        raise Refusal('Missing usable rows from export')
    for rows in parts.values():
        rows.sort(key=lambda r: (r['date_local'], r['persona']))
    return parts, excluded


def per_persona(parts):
    return {role: {p: sum(r['persona'] == role for r in rows) for p, rows in parts.items()} for role in method.ROLES}


def reconstruction(model, scaler, vectors):
    """[(score, {feature: share})] per count vector. Same arithmetic as the frozen score_rows 'ae' value."""
    import numpy as np
    import torch
    raw = np.asarray([[v[f] for f in FEATURES] for v in vectors], dtype=float)
    tensor = torch.tensor(((np.log1p(raw) - scaler['mean']) / scaler['scale']).astype(np.float32))
    if not torch.isfinite(tensor).all():
        raise Refusal('Nonfinite scoring input')
    with torch.inference_mode():
        squared = (model(tensor) - tensor) ** 2
    out = []
    for score, errors in zip(squared.mean(dim=1).tolist(), squared.tolist()):
        if not math.isfinite(score):
            raise Refusal('Nonfinite reconstruction error')
        total = math.fsum(errors)
        # ponytail: a perfect reconstruction (total 0) has no culprit; equal shares keep "sums to 1" true
        out.append((score, {f: (e / total if total else 1 / len(FEATURES)) for f, e in zip(FEATURES, errors)}))
    return out


def train(export_dir, out_dir, now=None, *, synthetic=False):
    """Fit, calibrate and save a bundle into a fresh directory. Returns the manifest."""
    import torch
    out = Path(out_dir).resolve()
    models = (ROOT / 'ml' / 'models').resolve()
    if out.exists() or out == models or models in out.parents:
        raise Refusal('Use a fresh private bundle path')
    before = frozen_hashes()
    parts, excluded = load_export(export_dir, now)
    counts = per_persona(parts)
    short = sorted(role for role, c in counts.items() if c['fit'] < MIN_FIT_ROWS)
    if short:
        raise Refusal(f'Persona(s) with fewer than {MIN_FIT_ROWS} fitting rows: {", ".join(short)}')
    if not parts['validation'] or not parts['normal_calibration']:
        raise Refusal('Validation and normal calibration rows required')
    model, scaler, best, epoch = v3.fit_ae(parts)
    calibration_scores = [s for s, _ in reconstruction(model, scaler, [r['features'] for r in parts['normal_calibration']])]
    calibration = method.empirical_threshold(calibration_scores)
    validation_scores = [s for s, _ in reconstruction(model, scaler, [r['features'] for r in parts['validation']])]
    if frozen_hashes() != before:
        raise Refusal('Frozen source changed during training')
    out.mkdir(parents=True)
    torch.save({'profile': PROFILE, 'features': FEATURES, 'state_dict': model.state_dict()}, out / 'weights.pt')
    (out / 'scaler.json').write_bytes(exporter.canonical(scaler))
    export_manifest = json.loads((Path(export_dir) / 'manifest.json').read_text())
    manifest = {
        'profile': PROFILE, 'purpose': PURPOSE, 'alerting': False, 'features': FEATURES,
        'method': {k: method.METHOD[k] for k in ('ae_dimensions', 'epochs', 'seed', 'learning_rate', 'weight_decay',
                                                  'gradient_clip', 'alpha')},
        'score': 'mean squared reconstruction error of log1p counts standardised on the fitting rows',
        'threshold_rule': 'live_daily_method.empirical_threshold on normal calibration scores; flagged = score > threshold',
        'threshold': calibration['threshold'], 'calibration': calibration,
        'validation_above_threshold': sum(s > calibration['threshold'] for s in validation_scores),
        'best_validation_mse': best, 'selected_epoch': epoch,
        'ae_parameters': sum(p.numel() for p in model.parameters()),
        'partition_rows': {p: len(rows) for p, rows in parts.items()}, 'persona_rows': counts,
        'excluded_rows': excluded, 'gate': f'no six-role gate; each persona >= {MIN_FIT_ROWS} fitting rows',
        'export_dataset_sha256': export_manifest['dataset_sha256'], 'export_status': export_manifest.get('status'),
        'feature_contract_sha256': v3.CONTRACT_SHA, 'frozen_source_sha256': before,
        'live_ae_sha256': sha(Path(__file__)), 'artifact_sha256': {n: sha(out / n) for n in ARTIFACTS},
        'environment': {n: version(n) for n in ('torch', 'numpy')}, 'device': 'cpu',
        'run_kind': 'synthetic_contract_test' if synthetic else 'controlled_aws_lab',
        'created_at_utc': datetime.now(timezone.utc).isoformat()}
    (out / 'manifest.json').write_bytes(exporter.canonical(manifest))
    bundle = load(out, allow_synthetic=synthetic)
    again = [s for s, _ in reconstruction(bundle['model'], bundle['scaler'], [r['features'] for r in parts['normal_calibration']])]
    if again != calibration_scores:
        (out / 'manifest.json').unlink()  # an unloadable bundle; keeps the weights for inspection
        raise Refusal('Reload score parity failed; bundle not usable')
    return manifest


def load(directory, *, allow_synthetic=False):
    """Verified bundle: refuses changed artifacts, a different frozen source or a synthetic bundle (unless allowed)."""
    import torch
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('profile') != PROFILE or manifest.get('features') != FEATURES:
        raise Refusal('Bundle profile differs')
    if manifest.get('run_kind') != 'controlled_aws_lab' and not (allow_synthetic and manifest.get('run_kind') == 'synthetic_contract_test'):
        raise Refusal('Synthetic/unknown bundle refused')
    if manifest.get('frozen_source_sha256') != frozen_hashes() or manifest.get('feature_contract_sha256') != v3.CONTRACT_SHA:
        raise Refusal('Bundle method/source contract differs')
    for name in ARTIFACTS:
        if sha(directory / name) != manifest['artifact_sha256'].get(name):
            raise Refusal('Bundle artifact changed')
    checkpoint = torch.load(directory / 'weights.pt', map_location='cpu', weights_only=True)
    if checkpoint.get('profile') != PROFILE or checkpoint.get('features') != FEATURES:
        raise Refusal('Checkpoint profile/order differs')
    model = method.build_ae()
    model.load_state_dict(checkpoint['state_dict'], strict=True)
    if any(not torch.isfinite(p).all() for p in model.parameters()):
        raise Refusal('Nonfinite model parameters')
    model.eval()
    scaler = json.loads((directory / 'scaler.json').read_text())
    if (scaler.get('transform') != 'log1p_then_standardize' or len(scaler['mean']) != 8 or len(scaler['scale']) != 8
            or not all(math.isfinite(v) for v in scaler['mean']) or not all(math.isfinite(v) and v > 0 for v in scaler['scale'])
            or not math.isfinite(manifest['threshold'])):
        raise Refusal('Invalid scaler or threshold')
    return {'model': model, 'scaler': scaler, 'threshold': manifest['threshold'], 'manifest': manifest,
            'model_sha256': sha(directory / 'manifest.json')}


# --- scoring ---------------------------------------------------------------------------------------------

def _meta(event):
    meta = event.get('metadata') or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            return {}
    return meta if isinstance(meta, dict) else {}


def persona_scope(events):
    """(account, stack, persona) when the events belong to an AWS lab persona role, else None.
    Native evidence only: the assumed-role ARN, whose account must equal the event's source account."""
    for event in events:
        if event.get('source') != 'aws_cloudtrail':
            continue
        arn = (_meta(event).get('userIdentity') or {}).get('arn')
        found = _PERSONA_ARN.fullmatch(arn) if isinstance(arn, str) else None
        if found and found.group(1) == event.get('source_account_id'):
            try:
                validate_scope(found.group(1), found.group(2))
            except ValueError:
                return None
            return found.groups()
    return None


def _local_day(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return stamp.astimezone(MYT).date() if stamp.tzinfo else None


def score_day(bundle, account_key, day, events):
    """Score one account-day. `events`: the account's stored event rows (timestamp, source, action, resource,
    ip_address, metadata, source_account_id); rows of other MYT days are ignored. Only in-contract events are
    counted (successful GetObject/HeadObject/GetBucketLocation on the seven lab buckets, as in the export); the
    rest are reported as excluded_events. Never raises an alert."""
    out = {'account_key': account_key, 'day': day.isoformat()}
    scope = persona_scope(events)
    if scope is None:
        return {**out, 'status': 'not_applicable', 'reason': 'The autoencoder scores AWS lab persona roles only.'}
    account, stack, persona = scope
    resources = dict(zip(buckets(account, stack), CONTRACT['resource_domain']))
    kept, excluded = [], 0
    for e in events:
        if _local_day(e['timestamp']) != day:
            continue
        if (e['action'] in CONTRACT['allowed_operations'] and e['resource'] in resources
                and _meta(e).get('errorCode') is None):
            kept.append({'timestamp': e['timestamp'], 'persona': persona, 'day': day.isoformat(), 'action': e['action'],
                         'resource': e['resource'], 'ip_address': e.get('ip_address')})
        else:
            excluded += 1
    out.update(excluded_events=excluded, threshold=bundle['threshold'], model_sha256=bundle['model_sha256'])
    if not kept:
        return {**out, 'status': 'not_scored', 'reason': 'No in-contract lab reads on this day.', 'features': {}}
    counts = extract(kept, resources)
    ip = counts['ip_observability']
    if ip['missing_events'] or ip['invalid_events']:
        return {**out, 'status': 'not_scored', 'features': counts['features'],
                'reason': 'Some reads have no valid source IP; such days are unscored, as in training.'}
    (score, shares), = reconstruction(bundle['model'], bundle['scaler'], [counts['features']])
    return {**out, 'status': 'scored', 'score': score, 'flagged': score > bundle['threshold'],
            'shares': shares, 'features': counts['features']}


def describe(row):
    """Plain-words view of a stored ml_scores row (workspace)."""
    shares = json.loads(row['shares_json'] or '{}')
    top = sorted(shares.items(), key=lambda kv: -kv[1])[:3]
    return {'status': 'scored' if row['score'] is not None else 'not_scored', 'day': row['day'], 'score': row['score'],
            'flagged': None if row['flagged'] is None else bool(row['flagged']), 'threshold': row['threshold'],
            'range': None if row['score'] is None else ('above' if row['flagged'] else 'below'),
            'top_features': [{'feature': f, 'label': LABELS[f], 'share': s} for f, s in top],
            'features': json.loads(row['features_json'] or '{}'), 'excluded_events': row['excluded_events'],
            'reason': row['note'], 'model_sha256': row['model_sha256'], 'scored_mode': row['scored_mode'],
            'computed_at': row['computed_at'], 'alerting': False}


# --- storage (event_store connection: SQLite or PostgreSQL) --------------------------------------------

def _store():
    from backend import event_store
    return event_store


def ensure_schema():
    store = _store()
    with store._db() as con:
        store._cursor(con).execute(store._DDL_ML_SCORES)


def _upsert(cur, r, now, mode):
    ph = _store()._PH
    cur.execute(f'''INSERT INTO ml_scores (account_key,day,score,flagged,threshold,shares_json,features_json,
        excluded_events,note,model_sha256,scored_mode,computed_at) VALUES ({','.join([ph] * 12)})
        ON CONFLICT (account_key,day) DO UPDATE SET score=excluded.score,flagged=excluded.flagged,
        threshold=excluded.threshold,shares_json=excluded.shares_json,features_json=excluded.features_json,
        excluded_events=excluded.excluded_events,note=excluded.note,model_sha256=excluded.model_sha256,
        scored_mode=excluded.scored_mode,computed_at=excluded.computed_at''',
                (r['account_key'], r['day'], r.get('score'), None if 'flagged' not in r else int(r['flagged']),
                 r['threshold'], json.dumps(r.get('shares', {})), json.dumps(r.get('features', {})),
                 r['excluded_events'], r.get('reason'), r['model_sha256'], mode, now.isoformat()))


_COLUMNS = 'timestamp,source,action,resource,ip_address,metadata,source_account_id'


def rescore_day(bundle, account_key, day, now=None, mode='ingest'):
    """Recompute and store one account-day (no row for not_applicable accounts). Returns the result."""
    now = now or datetime.now(timezone.utc)
    store = _store()
    ph = store._PH
    with store._db() as con:
        cur = store._cursor(con)
        # text prefilter: the MYT day lies inside UTC [day-1, day+1]; non-ISO stamps are kept for exact parsing
        cur.execute(f"""SELECT {_COLUMNS} FROM events WHERE account_key={ph} AND (timestamp >= {ph} AND timestamp < {ph}
            OR timestamp NOT LIKE {ph}) ORDER BY id""",
                    (account_key, (day - timedelta(days=1)).isoformat(), (day + timedelta(days=2)).isoformat(), '____-__-__%'))
        result = score_day(bundle, account_key, day, store._rows(cur))
        if result['status'] != 'not_applicable':
            _upsert(cur, result, now, mode)
    return result


_CACHE = {}


def configured():
    """The bundle named by ARGUS_LIVE_AE_BUNDLE (real bundles only), cached per manifest version; None if unset or
    unusable (logged once per version)."""
    path = os.getenv('ARGUS_LIVE_AE_BUNDLE')
    if not path:
        return None
    try:
        key = (path, (Path(path) / 'manifest.json').stat().st_mtime_ns)
    except OSError:
        return None
    if key not in _CACHE:
        _CACHE.clear()
        try:
            _CACHE[key] = load(path)
        except Exception as error:  # noqa: BLE001  a bad bundle disables the comparator, never ingest
            _log.warning('Live AE bundle unusable (%s); ML scores not computed', type(error).__name__)
            _CACHE[key] = None
    return _CACHE[key]


def on_event(account_key, timestamp, now=None, bundle=None):
    """Ingest/mirror hook: rescore the event's account-day when a bundle is configured. Returns the result or None."""
    bundle = bundle or configured()
    day = _local_day(timestamp)
    if bundle is None or not account_key or day is None:
        return None
    return rescore_day(bundle, account_key, day, now)


def backfill(bundle, now=None):
    """Recompute every AWS account-day in the store; drop ml_scores rows that are no longer produced. Counts."""
    now = now or datetime.now(timezone.utc)
    store = _store()
    counts, live = Counter(), set()
    with store._db() as con:
        cur = store._cursor(con)
        cur.execute("SELECT DISTINCT account_key FROM events WHERE account_key IS NOT NULL AND source='aws_cloudtrail'")
        for key in sorted(r['account_key'] for r in store._rows(cur)):
            cur.execute(f'SELECT {_COLUMNS} FROM events WHERE account_key={store._PH} ORDER BY id', (key,))
            rows = store._rows(cur)
            if persona_scope(rows) is None:
                continue
            days = defaultdict(list)
            for row in rows:
                if (d := _local_day(row['timestamp'])) is not None:
                    days[d].append(row)
            for day, events in sorted(days.items()):
                r = score_day(bundle, key, day, events)
                _upsert(cur, r, now, 'backfill')
                live.add((key, r['day']))
                counts['flagged' if r.get('flagged') else r['status']] += 1
        cur.execute('SELECT account_key,day FROM ml_scores')
        for key, day in [(r['account_key'], r['day']) for r in store._rows(cur)]:
            if (key, day) not in live:
                cur.execute(f'DELETE FROM ml_scores WHERE account_key={store._PH} AND day={store._PH}', (key, day))
    return dict(counts)


def backfill_copy(bundle_dir, db, *, allow_synthetic=False, now=None):
    """Backfill a marked SQLite workspace copy (workspace-copy.json with not_live: true) only."""
    store = _store()
    db = Path(db).resolve(strict=True)
    try:
        marker = json.loads((db.parent / 'workspace-copy.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        marker = {}
    if store._PG or marker.get('not_live') is not True or Path(marker.get('copy_db', '')).resolve() != db:
        raise Refusal('Backfill only a marked SQLite workspace copy (DATABASE_URL=sqlite-local)')
    bundle = load(bundle_dir, allow_synthetic=allow_synthetic)
    saved, store.DB_PATH = store.DB_PATH, db
    try:
        ensure_schema()
        return backfill(bundle, now)
    finally:
        store.DB_PATH = saved


# --- one-shot pipeline (scripts/train_live_ae.ps1) -----------------------------------------------------

def summary(manifest, bundle_dir):
    return {'run_kind': manifest['run_kind'], 'partition_rows': manifest['partition_rows'],
            'persona_rows': manifest['persona_rows'], 'excluded_rows': len(manifest['excluded_rows']),
            'best_validation_mse': manifest['best_validation_mse'], 'selected_epoch': manifest['selected_epoch'],
            'threshold': manifest['threshold'], 'normal_calibration_above_threshold': manifest['calibration']['normal_alerts'],
            'validation_above_threshold': manifest['validation_above_threshold'], 'ae_parameters': manifest['ae_parameters'],
            'weights_sha256': manifest['artifact_sha256']['weights.pt'],
            'model_sha256': sha(Path(bundle_dir) / 'manifest.json'), 'bundle': str(bundle_dir)}


def pipeline(pilot_config, out_root, *, demo_db=None, now=None, synthetic=False):
    """(a) export from the pilot config (sources read-only) into a fresh folder, (b) train, (c) summary,
    (d) optional backfill of a marked demo copy."""
    now = now or datetime.now(timezone.utc)
    if now < REAL_NOT_BEFORE:
        raise Refusal(f'Training waits until {REAL_NOT_BEFORE.isoformat()} (normal calibration closes 12 Nov MYT)')
    cfg = json.loads(Path(pilot_config).read_text())
    stamp = now.astimezone(MYT).strftime('%Y%m%dT%H%M%S')
    out_root = Path(out_root)
    export_dir, bundle_dir = out_root / f'export-{stamp}', out_root / f'bundle-{stamp}'
    exporter.export(Path(cfg['ledger_dir']) / 'ledger.db', Path(cfg['connected_dir']) / 'events.db',
                    cfg['account_id'], cfg['stack'], export_dir, now)
    result = summary(train(export_dir, bundle_dir, now, synthetic=synthetic), bundle_dir)
    if demo_db:
        result['demo_backfill'] = backfill_copy(bundle_dir, demo_db, allow_synthetic=synthetic, now=now)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)
    t = sub.add_parser('train')
    t.add_argument('--export', required=True)
    t.add_argument('--out', required=True)
    t.add_argument('--synthetic', action='store_true')
    b = sub.add_parser('backfill')
    b.add_argument('--bundle', required=True)
    b.add_argument('--db', required=True)
    b.add_argument('--allow-synthetic', action='store_true')
    p = sub.add_parser('pipeline')
    p.add_argument('--pilot-config', required=True)
    p.add_argument('--out-root', required=True)
    p.add_argument('--demo-db')
    args = ap.parse_args(argv)
    try:
        if args.command == 'train':
            result = summary(train(args.export, args.out, synthetic=args.synthetic), args.out)
        elif args.command == 'backfill':
            result = backfill_copy(args.bundle, args.db, allow_synthetic=args.allow_synthetic)
        else:
            result = pipeline(args.pilot_config, args.out_root, demo_db=args.demo_db)
    except (Refusal, ValueError) as error:
        raise SystemExit(f'live_ae refused: {error}')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
