"""Live autoencoder v2 (L10): an "ML anomaly score" per lab persona account-day (the six AWS persona roles and the
six Cloudflare persona service tokens). Comparator only: it never raises alerts, never changes the baseline risk
score and never feeds a tier. v1 (8 raw counts, one population model) is kept as history in backend/live_ae_v1.py.

Inputs: nine account-relative features per (account, MYT day), computed by `features()` from that account's own
earlier active days only (the baseline scorer's history: active days inside the previous 28 calendar days, at least
5, otherwise Learning and not scored). The same function builds the training rows and scores live days.
  event_count_log            log1p(events today)
  unique_actions             distinct (source, action) today
  unique_resources           distinct non-empty resources today
  outside_usual_hours_share  share of today's events outside the account's usual MYT hours (baseline_scorer rule:
                             hours holding >= 5% of history events, widened +-1 h, circular)
  new_action_count           distinct (source, action) today absent from the history
  volume_log_ratio           log1p(today) - log1p(median events per prior active day)
  new_resource_share         share of today's distinct resources absent from the history; 0 when no resource today
                             (stored with no_resource_today = 1)
  action_mix_js_distance     base-2 Jensen-Shannon distance, event-weighted action mix today vs history
  hour_profile_js_distance   the same over the 24 MYT hours
JS distances use scripts/clue_v2_features.js_distance (pseudocount mass 1 per distribution), imported read-only.

Model: 9-6-3-6-9 autoencoder, Tanh after each hidden layer, linear output; inputs standardised with fit-only mean/std
(zero variance -> scale 1); CPU, seed 42, deterministic, one thread; full-batch Adam lr 0.001, weight decay 0.001,
grad-norm clip 5; up to 2000 epochs; checkpoint = earliest epoch with the minimum validation MSE (strict improvement);
stop after 200 epochs without improvement. Data: every scorable persona account-day up to and including 12 Nov 2026
MYT; fit <= 8 Nov, validation 9-10 Nov (checkpoint only), calibration 11-12 Nov (threshold only). Threshold:
scripts/live_daily_method.empirical_threshold on calibration scores; flagged = score strictly greater.
Score = mean squared reconstruction error in the standardised space; explanation = each feature's share of it.

Storage: ml_scores (backend/event_store.py), model_version 'v2'. Written by the ingest hook and the mirror pass
(on_event, best effort) when ARGUS_LIVE_AE_BUNDLE names a v2 bundle, and by the backfill command.

    python -m backend.live_ae train --events-db <events.db, opened read-only> --out <fresh bundle dir> [--synthetic]
    python -m backend.live_ae backfill --bundle <bundle dir> --db <marked sqlite workspace copy> [--allow-synthetic]
    python -m backend.live_ae repair-missing --bundle <bundle dir> [--db <sqlite>]   # only account-days with no row

Pinned comparator: config/live_ae_v2.json names the one bundle (manifest sha256) the live evaluation may use. load()
refuses any other real bundle, so the comparator is then not_evaluated and nothing is scored with another model.
Each load attempt by configured() is recorded in live-ae-loaded.json next to the SQLite database and in status().
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
from importlib.metadata import version
import json
import logging
import math
import os
from pathlib import Path
import re
import sqlite3
import statistics

from backend import baseline_scorer as bs
from scripts.clue_v2_features import js_distance
from scripts.live_daily_method import empirical_threshold
from scripts.simulation_lab import validate_scope

_log = logging.getLogger(__name__)


class Refusal(ValueError):
    """The bundle, data or request does not meet the v2 rules."""


PROFILE, MODEL_VERSION = 'argus_live_ae_v2', 'v2'
PURPOSE = 'product comparator, not alerting'
MYT = bs.MYT
FEATURES = ['event_count_log', 'unique_actions', 'unique_resources', 'outside_usual_hours_share', 'new_action_count',
            'volume_log_ratio', 'new_resource_share', 'action_mix_js_distance', 'hour_profile_js_distance']
LABELS = {'event_count_log': 'number of events', 'unique_actions': 'distinct actions',
          'unique_resources': 'distinct resources', 'outside_usual_hours_share': 'activity outside usual hours',
          'new_action_count': 'new actions', 'volume_log_ratio': 'volume against a usual day',
          'new_resource_share': 'new resources', 'action_mix_js_distance': 'change in action mix',
          'hour_profile_js_distance': 'change in hours of activity'}
DATA_END = date(2026, 11, 12)  # nothing dated 13 Nov 2026 MYT or later is used for training
SPLITS = {'fit': (date.min, date(2026, 11, 8)), 'validation': (date(2026, 11, 9), date(2026, 11, 10)),
          'calibration': (date(2026, 11, 11), DATA_END)}
PROVIDERS = ('aws', 'cloudflare')
METHOD = {'dimensions': [9, 6, 3, 6, 9], 'activation': 'Tanh after each hidden layer, linear output',
          'standardise': 'fit-only mean/std (ddof 0); constant fit column -> its value as mean, scale 1',
          'optimizer': 'Adam full batch', 'learning_rate': 0.001, 'weight_decay': 0.001, 'gradient_clip_norm': 5.0,
          'epochs_max': 2000, 'patience': 200, 'checkpoint': 'earliest minimum validation MSE (strict improvement)',
          'seed': 42, 'threads': 1, 'deterministic': True, 'device': 'cpu', 'loss': 'mean squared error',
          'threshold': 'live_daily_method.empirical_threshold on calibration scores; flagged = score > threshold'}
FEATURE_CONTRACT = {
    'profile': PROFILE, 'features': FEATURES, 'day': 'Asia/Kuala_Lumpur calendar day (UTC+08:00)',
    'history': f'the account\'s active days in the {bs.WINDOW_DAYS} calendar days before the day '
               '(baseline_scorer.prior_days); fewer than 5 -> Learning, not scored',
    'action': '(source, action)', 'resource': 'non-empty resource string',
    'usual_hours': 'baseline_scorer.usual_hours (>= 5% of history events, +-1 h, circular, MYT)',
    'volume_log_ratio': 'log1p(today) - log1p(statistics.median(prior active-day counts))',
    'new_resource_share': 'share of today distinct resources absent from history; 0 and no_resource_today when none',
    'js': 'clue_v2_features.js_distance: base-2, event-weighted, pseudocount mass 1 per distribution',
    'action_support': 'sorted union of today and history action kinds', 'hour_support': 'MYT hours 0-23',
    'accounts': 'AWS assumed-role argus-*-persona-0N (ARN account = source account); Cloudflare service tokens whose '
                'requests carry /workloads/persona-0N/',
}
SOURCES = ('backend/live_ae.py', 'backend/baseline_scorer.py', 'scripts/clue_v2_features.py', 'scripts/live_daily_method.py')
ARTIFACTS = ('weights.pt', 'scaler.json')
ROOT = Path(__file__).resolve().parent.parent
_PERSONA_ARN = re.compile(r'arn:aws:sts::(\d{12}):assumed-role/(argus-[a-z0-9-]+)-(persona-0[1-6])/[^/]+')
_CF_PERSONA = re.compile(r'/workloads/(persona-0[1-6])/')
_COLUMNS = 'timestamp,source,action,resource,metadata,source_account_id,account_kind'
PIN_FILE = ROOT / 'config' / 'live_ae_v2.json'
EXPECTED_MANIFEST_SHA256 = json.loads(PIN_FILE.read_text(encoding='utf-8'))['expected_manifest_sha256']
LOADED_FILE = 'live-ae-loaded.json'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


CONTRACT_SHA = digest(FEATURE_CONTRACT)


# --- accounts and features (shared by training and live scoring) ----------------------------------------

def _meta(event):
    meta = event.get('metadata') or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            return {}
    return meta if isinstance(meta, dict) else {}


def scope(events):
    """('aws' | 'cloudflare', persona) when the events belong to a lab persona account, else None.
    AWS: the assumed-role ARN, whose account must equal the event's source account. Cloudflare: a service token whose
    requests carry /workloads/persona-0N/ (the lab workload path). Everything else (monitoring infrastructure, the
    GitHub bot, people) is not applicable."""
    for event in events:
        if event.get('source') == 'aws_cloudtrail':
            arn = (_meta(event).get('userIdentity') or {}).get('arn')
            found = _PERSONA_ARN.fullmatch(arn) if isinstance(arn, str) else None
            if found and found.group(1) == event.get('source_account_id'):
                try:
                    validate_scope(found.group(1), found.group(2))
                except ValueError:
                    return None
                return 'aws', found.group(3)
        elif event.get('source') == 'cloudflare_access' and event.get('account_kind') == 'service_token':
            found = _CF_PERSONA.search(event.get('resource') or '')
            if found:
                return 'cloudflare', found.group(1)
    return None


def group(events):
    """Stored event rows -> {MYT date: [(hour, source, action, resource)]} (baseline_scorer.group_days)."""
    return bs.group_days([(e['timestamp'], e['source'], e['action'], e['resource']) for e in events])


def features(days, day):
    """The nine inputs for `day` from the account's own earlier active days only. days: group() output.
    Returns None when the account has fewer than 5 prior active days (Learning)."""
    prior = bs.prior_days(days, day)
    if len(prior) < bs.MIN_HISTORY:
        return None
    today = days[day]
    hist = [e for d in prior for e in days[d]]
    actions, hist_actions = Counter((e[1], e[2]) for e in today), Counter((e[1], e[2]) for e in hist)
    resources, hist_resources = {e[3] for e in today if e[3]}, {e[3] for e in hist if e[3]}
    hours, hist_hours = Counter(e[0] for e in today), Counter(e[0] for e in hist)
    usual = bs.usual_hours(hist)
    support = sorted(set(actions) | set(hist_actions))
    values = {
        'event_count_log': math.log1p(len(today)),
        'unique_actions': len(actions),
        'unique_resources': len(resources),
        'outside_usual_hours_share': sum(e[0] not in usual for e in today) / len(today),
        'new_action_count': len(set(actions) - set(hist_actions)),
        'volume_log_ratio': math.log1p(len(today)) - math.log1p(statistics.median(len(days[d]) for d in prior)),
        'new_resource_share': len(resources - hist_resources) / len(resources) if resources else 0.0,
        'action_mix_js_distance': js_distance([actions[k] for k in support], [hist_actions[k] for k in support]),
        'hour_profile_js_distance': js_distance([hours[h] for h in range(24)], [hist_hours[h] for h in range(24)]),
    }
    return {'features': {f: float(values[f]) for f in FEATURES}, 'no_resource_today': not resources,
            'history_days': len(prior)}


def split_of(day):
    for name, (lo, hi) in SPLITS.items():
        if lo <= day <= hi:
            return name
    raise Refusal('Account-day outside the training window')


def dataset(events_db, cutoff=DATA_END):
    """Every scorable persona account-day dated <= cutoff (MYT) from a SQLite events DB opened read-only. Events
    dated after the cutoff are dropped before any feature or history is computed. Returns (rows, info)."""
    uri = f'file:{Path(events_db).resolve(strict=True).as_posix()}?mode=ro'
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    try:
        accounts = defaultdict(list)
        for r in con.execute(f'SELECT account_key,{_COLUMNS} FROM events WHERE account_key IS NOT NULL ORDER BY id'):
            accounts[r['account_key']].append(dict(r))
    finally:
        con.close()
    rows, info = [], {'accounts': Counter(), 'learning_days': Counter(), 'events_after_cutoff': 0}
    for key in sorted(accounts):
        kept = [e for e in accounts[key] if (d := bs.myt_day(e['timestamp'])) is not None and d <= cutoff]
        found = scope(kept)
        if found is None:
            continue
        info['accounts'][found[0]] += 1
        info['events_after_cutoff'] += len(accounts[key]) - len(kept)
        days = group(kept)
        for day in sorted(days):
            values = features(days, day)
            if values is None:
                info['learning_days'][found[0]] += 1
                continue
            rows.append({'account_key': key, 'provider': found[0], 'persona': found[1], 'day': day.isoformat(),
                         'split': split_of(day), **values})
    rows.sort(key=lambda r: (r['day'], r['account_key']))
    return rows, {k: dict(v) if isinstance(v, Counter) else v for k, v in info.items()}


# --- model -----------------------------------------------------------------------------------------------

def build_model():
    import torch.nn as nn
    a, b, c, d, e = METHOD['dimensions']
    return nn.Sequential(nn.Linear(a, b), nn.Tanh(), nn.Linear(b, c), nn.Tanh(), nn.Linear(c, d), nn.Tanh(),
                         nn.Linear(d, e))


def checkpoint_step(best, selected, epoch, val, patience=METHOD['patience']):
    """Earliest-minimum rule for one epoch's validation MSE. Returns (best, selected epoch, improved, stop):
    only a strictly lower value moves the checkpoint; stop once `patience` epochs passed without one."""
    if val < best:
        return val, epoch, True, False
    return best, selected, False, epoch - selected >= patience


def _matrix(rows):
    import numpy as np
    return np.asarray([[r['features'][f] for f in FEATURES] for r in rows], dtype=np.float64)


def fit(parts):
    """parts: {'fit': rows, 'validation': rows}. Returns (model, scaler, report)."""
    import numpy as np
    import torch
    torch.manual_seed(METHOD['seed'])
    torch.set_num_threads(METHOD['threads'])
    torch.use_deterministic_algorithms(True)
    fit_x, val_x = _matrix(parts['fit']), _matrix(parts['validation'])
    constant = fit_x.max(axis=0) == fit_x.min(axis=0)
    mean, scale = fit_x.mean(axis=0), np.where(constant, 1.0, fit_x.std(axis=0))
    mean[constant] = fit_x[0, constant]  # summation rounding must not give a constant column a tiny std
    fit_t, val_t = (torch.tensor(((x - mean) / scale).astype(np.float32)) for x in (fit_x, val_x))
    if not (torch.isfinite(fit_t).all() and torch.isfinite(val_t).all()):
        raise Refusal('Nonfinite standardised features')
    model = build_model().cpu()
    opt = torch.optim.Adam(model.parameters(), lr=METHOD['learning_rate'], weight_decay=METHOD['weight_decay'])
    best, selected, state, epoch = math.inf, 0, None, 0
    for epoch in range(1, METHOD['epochs_max'] + 1):
        model.train()
        opt.zero_grad()
        loss = ((model(fit_t) - fit_t) ** 2).mean()
        if not torch.isfinite(loss):
            raise Refusal('Nonfinite fitting loss')
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), METHOD['gradient_clip_norm'], error_if_nonfinite=True)
        opt.step()
        model.eval()
        with torch.inference_mode():
            val = float(((model(val_t) - val_t) ** 2).mean())
        if not math.isfinite(val):
            raise Refusal('Nonfinite validation loss')
        best, selected, improved, stop = checkpoint_step(best, selected, epoch, val)
        if improved:
            state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        if stop:
            break
    model.load_state_dict(state, strict=True)
    model.eval()
    scaler = {'mean': mean.tolist(), 'scale': scale.tolist(), 'transform': 'standardise',
              'constant_features': [f for f, c in zip(FEATURES, constant) if c]}
    report = {'best_validation_mse': best, 'selected_epoch': selected, 'stop_epoch': epoch,
              'validation_mse_predict_fit_mean': float((val_t.double() ** 2).mean())}
    return model, scaler, report


def reconstruction(model, scaler, vectors):
    """[(score, {feature: share})] per feature dict: standardised MSE and each feature's share of the squared error."""
    import numpy as np
    import torch
    raw = np.asarray([[v[f] for f in FEATURES] for v in vectors], dtype=np.float64)
    tensor = torch.tensor(((raw - np.asarray(scaler['mean'])) / np.asarray(scaler['scale'])).astype(np.float32))
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


def _by(rows, split):
    return [r for r in rows if r['split'] == split]


def train(events_db, out_dir, now=None, *, synthetic=False):
    """Build the dataset (read-only), fit, calibrate and save a bundle into a fresh directory. Returns the manifest."""
    import torch
    now = now or datetime.now(timezone.utc)
    if now.astimezone(MYT).date() <= DATA_END:
        raise Refusal(f'Training waits until {DATA_END.isoformat()} MYT has closed')
    out = Path(out_dir).resolve()
    models = (ROOT / 'ml' / 'models').resolve()
    if out.exists() or out == models or models in out.parents:
        raise Refusal('Use a fresh private bundle path')
    rows, info = dataset(events_db)
    if not rows or max(r['day'] for r in rows) > DATA_END.isoformat():
        raise Refusal('No rows, or a row after the data cutoff')
    parts = {name: _by(rows, name) for name in SPLITS}
    if any(not part for part in parts.values()):
        raise Refusal('Fit, validation and calibration rows are all required')
    model, scaler, report = fit(parts)
    calibration_scores = [s for s, _ in reconstruction(model, scaler, [r['features'] for r in parts['calibration']])]
    calibration = empirical_threshold(calibration_scores)
    validation_scores = [s for s, _ in reconstruction(model, scaler, [r['features'] for r in parts['validation']])]
    out.mkdir(parents=True)
    torch.save({'profile': PROFILE, 'features': FEATURES, 'state_dict': model.state_dict()}, out / 'weights.pt')
    (out / 'scaler.json').write_bytes(canonical(scaler))
    manifest = {
        'profile': PROFILE, 'model_version': MODEL_VERSION, 'purpose': PURPOSE, 'alerting': False,
        'features': FEATURES, 'labels': LABELS, 'feature_contract': FEATURE_CONTRACT,
        'feature_contract_sha256': CONTRACT_SHA, 'method': METHOD,
        'splits': {k: [None if lo == date.min else lo.isoformat(), hi.isoformat()] for k, (lo, hi) in SPLITS.items()},
        'data_end_myt': DATA_END.isoformat(), 'rows': {k: len(v) for k, v in parts.items()},
        'rows_by_provider': {k: {p: sum(r['provider'] == p for r in v) for p in PROVIDERS} for k, v in parts.items()},
        'last_day_used': max(r['day'] for r in rows), **info, **report,
        'threshold': calibration['threshold'], 'calibration': calibration,
        'calibration_above_threshold': calibration['normal_alerts'],
        'validation_above_threshold': sum(s > calibration['threshold'] for s in validation_scores),
        'parameters': sum(p.numel() for p in model.parameters()),
        'dataset_sha256': digest([[r['account_key'], r['day'], r['features']] for r in rows]),
        'source_sha256': {name: sha(ROOT / name) for name in SOURCES},
        'artifact_sha256': {name: sha(out / name) for name in ARTIFACTS},
        'environment': {n: version(n) for n in ('torch', 'numpy')},
        'run_kind': 'synthetic_contract_test' if synthetic else 'controlled_lab',
        'created_at_utc': datetime.now(timezone.utc).isoformat()}
    (out / 'manifest.json').write_bytes(canonical(manifest))
    bundle = load(out, allow_synthetic=synthetic)
    again = [s for s, _ in reconstruction(bundle['model'], bundle['scaler'], [r['features'] for r in parts['calibration']])]
    if again != calibration_scores:
        (out / 'manifest.json').unlink()  # an unloadable bundle; keeps the weights for inspection
        raise Refusal('Reload score parity failed; bundle not usable')
    return manifest


def load(directory, *, allow_synthetic=False):
    """Verified v2 bundle: refuses another profile or feature contract, changed artifacts, a synthetic bundle, or a real
    bundle (run_kind controlled_lab) whose manifest sha256 is not the pinned one. Synthetic test bundles load only with
    allow_synthetic and are never pinned."""
    import torch
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    if (manifest.get('profile') != PROFILE or manifest.get('features') != FEATURES
            or manifest.get('feature_contract_sha256') != CONTRACT_SHA or manifest.get('method') != METHOD):
        raise Refusal('Bundle profile, feature contract or method differs')
    if manifest.get('run_kind') != 'controlled_lab' and not (allow_synthetic and manifest.get('run_kind') == 'synthetic_contract_test'):
        raise Refusal('Synthetic/unknown bundle refused')
    if manifest.get('run_kind') == 'controlled_lab' and sha(directory / 'manifest.json') != EXPECTED_MANIFEST_SHA256:
        raise Refusal('Bundle manifest sha256 is not the pinned comparator (config/live_ae_v2.json)')
    for name in ARTIFACTS:
        if sha(directory / name) != manifest['artifact_sha256'].get(name):
            raise Refusal('Bundle artifact changed')
    checkpoint = torch.load(directory / 'weights.pt', map_location='cpu', weights_only=True)
    if checkpoint.get('profile') != PROFILE or checkpoint.get('features') != FEATURES:
        raise Refusal('Checkpoint profile/order differs')
    model = build_model()
    model.load_state_dict(checkpoint['state_dict'], strict=True)
    if any(not torch.isfinite(p).all() for p in model.parameters()):
        raise Refusal('Nonfinite model parameters')
    model.eval()
    scaler = json.loads((directory / 'scaler.json').read_text())
    n = len(FEATURES)
    if (len(scaler.get('mean', ())) != n or len(scaler.get('scale', ())) != n
            or not all(math.isfinite(v) for v in scaler['mean']) or not all(math.isfinite(v) and v > 0 for v in scaler['scale'])
            or not math.isfinite(manifest.get('threshold', math.nan))):
        raise Refusal('Invalid scaler or threshold')
    return {'model': model, 'scaler': scaler, 'threshold': manifest['threshold'], 'manifest': manifest,
            'model_sha256': sha(directory / 'manifest.json')}


# --- scoring ---------------------------------------------------------------------------------------------

NOT_APPLICABLE = 'The autoencoder scores the lab persona accounts only (AWS roles and Cloudflare service tokens).'


def _score(bundle, account_key, found, days, day):
    out = {'account_key': account_key, 'day': day.isoformat(), 'provider': found[0],
           'threshold': bundle['threshold'], 'model_sha256': bundle['model_sha256']}
    if day not in days:
        return {**out, 'status': 'not_scored', 'reason': 'No activity on this day.'}
    values = features(days, day)
    if values is None:
        return {**out, 'status': 'not_scored',
                'reason': f'Learning: {len(bs.prior_days(days, day))} of {bs.MIN_HISTORY} days of history.'}
    (score, shares), = reconstruction(bundle['model'], bundle['scaler'], [values['features']])
    return {**out, 'status': 'scored', 'score': score, 'flagged': score > bundle['threshold'], 'shares': shares,
            'features': values['features'], 'no_resource_today': values['no_resource_today']}


def score_day(bundle, account_key, day, events):
    """Score one account-day from the account's stored event rows (timestamp, source, action, resource, metadata,
    source_account_id, account_kind); events of other days are its history. Never raises an alert."""
    found = scope(events)
    if found is None:
        return {'account_key': account_key, 'day': day.isoformat(), 'status': 'not_applicable', 'reason': NOT_APPLICABLE}
    return _score(bundle, account_key, found, group(events), day)


def describe(row):
    """Plain-words view of a stored v2 ml_scores row (workspace)."""
    shares = json.loads(row['shares_json'] or '{}')
    top = sorted(shares.items(), key=lambda kv: -kv[1])[:3]
    return {'status': 'scored' if row['score'] is not None else 'not_scored', 'day': row['day'], 'score': row['score'],
            'flagged': None if row['flagged'] is None else bool(row['flagged']), 'threshold': row['threshold'],
            'range': None if row['score'] is None else ('above' if row['flagged'] else 'below'),
            'top_features': [{'feature': f, 'label': LABELS[f], 'share': s} for f, s in top],
            'features': json.loads(row['features_json'] or '{}'), 'reason': row['note'],
            'model_version': row['model_version'], 'model_sha256': row['model_sha256'],
            'scored_mode': row['scored_mode'], 'computed_at': row['computed_at'], 'alerting': False}


# --- storage (event_store connection: SQLite or PostgreSQL) --------------------------------------------

def _store():
    from backend import event_store
    return event_store


def ensure_schema():
    store = _store()
    with store._db() as con:
        store.ensure_ml_scores(store._cursor(con))


def _upsert(cur, r, now, mode):
    ph = _store()._PH
    no_resource = r.get('no_resource_today')
    cur.execute(f'''INSERT INTO ml_scores (account_key,day,score,flagged,threshold,shares_json,features_json,
        excluded_events,note,model_sha256,scored_mode,computed_at,model_version,no_resource_today)
        VALUES ({','.join([ph] * 14)})
        ON CONFLICT (account_key,day) DO UPDATE SET score=excluded.score,flagged=excluded.flagged,
        threshold=excluded.threshold,shares_json=excluded.shares_json,features_json=excluded.features_json,
        excluded_events=excluded.excluded_events,note=excluded.note,model_sha256=excluded.model_sha256,
        scored_mode=excluded.scored_mode,computed_at=excluded.computed_at,model_version=excluded.model_version,
        no_resource_today=excluded.no_resource_today''',
                (r['account_key'], r['day'], r.get('score'), None if 'flagged' not in r else int(r['flagged']),
                 r['threshold'], json.dumps(r.get('shares', {})), json.dumps(r.get('features', {})), 0, r.get('reason'),
                 r['model_sha256'], mode, now.isoformat(), MODEL_VERSION,
                 None if no_resource is None else int(no_resource)))


def rescore_day(bundle, account_key, day, now=None, mode='ingest'):
    """Recompute and store one account-day plus any later stored day of the account whose 28-day history now includes
    it (late arrival). No row for accounts that are not applicable. Returns the day's result."""
    now = now or datetime.now(timezone.utc)
    store = _store()
    ph = store._PH
    with store._db() as con:
        cur = store._cursor(con)
        cur.execute(f'SELECT day FROM ml_scores WHERE account_key={ph} AND day>{ph} AND day<={ph}',
                    (account_key, day.isoformat(), (day + timedelta(days=bs.WINDOW_DAYS)).isoformat()))
        later = sorted(date.fromisoformat(r['day']) for r in store._rows(cur))
        last = later[-1] if later else day
        # text prefilter: MYT days [day-28, last] lie inside UTC [day-30, last+2); non-ISO stamps kept for exact parsing
        cur.execute(f"""SELECT {_COLUMNS} FROM events WHERE account_key={ph} AND (timestamp >= {ph} AND timestamp < {ph}
            OR timestamp NOT LIKE {ph}) ORDER BY id""",
                    (account_key, (day - timedelta(days=bs.WINDOW_DAYS + 2)).isoformat(), (last + timedelta(days=2)).isoformat(),
                     bs.NON_ISO_STAMP))
        events = store._rows(cur)
        found = scope(events)
        if found is None:
            return score_day(bundle, account_key, day, [])
        days = group(events)
        results = [_score(bundle, account_key, found, days, d) for d in [day, *later]]
        for r in results:
            _upsert(cur, r, now, mode)
    return results[0]


_CACHE = {}
_LOADED = {}  # the last load attempt by configured() or a CLI, for health/readiness


def status():
    """Comparator state for health/readiness: loaded (pinned manifest), not_evaluated (refused) or not_configured."""
    return dict(_LOADED) if _LOADED else {'comparator': 'not_configured', 'expected_manifest_sha256': EXPECTED_MANIFEST_SHA256}


def record_load(path, bundle, error=None):
    """Remember a load attempt (status()) and write it to live-ae-loaded.json next to the SQLite database."""
    _LOADED.clear()
    _LOADED.update({'comparator': 'loaded' if bundle else 'not_evaluated', 'bundle': Path(path).name,
                    'loaded_manifest_sha256': bundle['model_sha256'] if bundle else None,
                    'expected_manifest_sha256': EXPECTED_MANIFEST_SHA256,
                    'reason': None if bundle else f'{type(error).__name__}: {error}',
                    'at_utc': datetime.now(timezone.utc).isoformat()})
    store = _store()
    if not store._PG:
        try:
            (Path(store.DB_PATH).parent / LOADED_FILE).write_text(json.dumps(_LOADED, indent=2), encoding='utf-8')
        except OSError as failure:
            _log.warning('Could not write %s (%s)', LOADED_FILE, type(failure).__name__)


def configured():
    """The bundle named by ARGUS_LIVE_AE_BUNDLE (the pinned real v2 bundle only), cached per manifest version; None if
    unset or unusable (logged once per version; every attempt recorded by record_load)."""
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
            record_load(path, _CACHE[key])
        except Exception as error:  # noqa: BLE001  a bad bundle disables the comparator, never ingest
            _log.warning('Live AE bundle unusable (%s); ML scores not computed', type(error).__name__)
            _CACHE[key] = None
            record_load(path, None, error)
    return _CACHE[key]


def on_event(account_key, timestamp, now=None, bundle=None):
    """Ingest/mirror hook: rescore the event's account-day when a bundle is configured. Returns the result or None."""
    bundle = bundle or configured()
    day = bs.myt_day(timestamp)
    if bundle is None or not account_key or day is None:
        return None
    return rescore_day(bundle, account_key, day, now)


def backfill(bundle, now=None):
    """Recompute every persona account-day in the store; drop ml_scores rows no longer produced (including v1 rows).
    Returns counts by provider and status."""
    now = now or datetime.now(timezone.utc)
    store = _store()
    counts, live = Counter(), set()
    with store._db() as con:
        cur = store._cursor(con)
        cur.execute('SELECT DISTINCT account_key FROM events WHERE account_key IS NOT NULL')
        for key in sorted(r['account_key'] for r in store._rows(cur)):
            cur.execute(f'SELECT {_COLUMNS} FROM events WHERE account_key={store._PH} ORDER BY id', (key,))
            events = store._rows(cur)
            found = scope(events)
            if found is None:
                continue
            days = group(events)
            for day in sorted(days):
                r = _score(bundle, key, found, days, day)
                _upsert(cur, r, now, 'backfill')
                live.add((key, r['day']))
                counts[f"{found[0]}_{'flagged' if r.get('flagged') else r['status']}"] += 1
        cur.execute('SELECT account_key,day FROM ml_scores')
        for key, day in [(r['account_key'], r['day']) for r in store._rows(cur)]:
            if (key, day) not in live:
                cur.execute(f'DELETE FROM ml_scores WHERE account_key={store._PH} AND day={store._PH}', (key, day))
    return dict(sorted(counts.items()))


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


def repair_missing(bundle, since=None, now=None):
    """Score exactly the persona account-days with events but no v2 ml_scores row (backend.readiness.missing_scores).
    Returns the number of account-days scored."""
    from backend.readiness import missing_scores
    ensure_schema()
    todo = [m for m in missing_scores(None, since) if 'ml' in m['missing']]
    for m in todo:
        rescore_day(bundle, m['account_key'], date.fromisoformat(m['day']), now, 'repair')
    return len(todo)


def summary(manifest, bundle_dir):
    keys = ('run_kind', 'rows', 'rows_by_provider', 'accounts', 'learning_days', 'events_after_cutoff', 'last_day_used',
            'best_validation_mse', 'validation_mse_predict_fit_mean', 'selected_epoch', 'stop_epoch', 'threshold',
            'calibration_above_threshold', 'validation_above_threshold', 'parameters')
    return {**{k: manifest[k] for k in keys}, 'weights_sha256': manifest['artifact_sha256']['weights.pt'],
            'model_sha256': sha(Path(bundle_dir) / 'manifest.json'), 'bundle': str(bundle_dir)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)
    t = sub.add_parser('train')
    t.add_argument('--events-db', required=True)
    t.add_argument('--out', required=True)
    t.add_argument('--synthetic', action='store_true')
    b = sub.add_parser('backfill')
    b.add_argument('--bundle', required=True)
    b.add_argument('--db', required=True)
    b.add_argument('--allow-synthetic', action='store_true')
    r = sub.add_parser('repair-missing')
    r.add_argument('--bundle', required=True)
    r.add_argument('--db', help='SQLite file instead of the configured event store')
    args = ap.parse_args(argv)
    try:
        if args.command == 'train':
            result = summary(train(args.events_db, args.out, synthetic=args.synthetic), args.out)
        elif args.command == 'repair-missing':
            store = _store()
            if args.db:
                if store._PG:
                    raise Refusal('--db is for SQLite files; unset DATABASE_URL (use sqlite-local)')
                store.DB_PATH = Path(args.db).resolve(strict=True)
            try:
                bundle = load(args.bundle)
            except Refusal as error:
                record_load(args.bundle, None, error)
                raise
            record_load(args.bundle, bundle)
            result = {'loaded_manifest_sha256': bundle['model_sha256'], 'account_days_scored': repair_missing(bundle)}
        else:
            result = backfill_copy(args.bundle, args.db, allow_synthetic=args.allow_synthetic)
    except (Refusal, ValueError) as error:
        raise SystemExit(f'live_ae refused: {error}')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
