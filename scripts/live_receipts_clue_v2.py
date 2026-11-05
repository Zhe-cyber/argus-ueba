"""Versioned per-account/day live diagnostic receipts for W33 v2: experimental, not validated.

One receipt per closed live account-day. Each carries:
- the full source/scope/account/day key and the cut-off;
- model/scaler/profile/extractor/explainer/policy hashes;
- start-of-day history provenance (the prior accepted day keys);
- source timezone, feature names and raw values;
- eligibility, why-unscored and completeness status;
- raw detector scores, additive/share error terms, behaviour facts and limitations.

Rules:
- Scores and explanations come from one start-of-day state via `explain_clue_v2.explain`, called
  before the day is committed.
- Controlled AWS persona days follow the versioned live coverage policy: only `usable` days are
  scored or enter history, and other persona days carry an explicit reason and no score.
- No risk tier, alert, CLUE cut-off translation or live activation is produced.
- Read-only on the live store and ledger. The frozen W33 contract and release are untouched.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import (audit_clue_v2_live as audit, clue_v2_features as v2, clue_v2_reader as reader,
                     explain_clue_v2 as explain, live_coverage_policy as policy, train_clue_v2 as trainer)
from scripts.shared_core_features import HOURS, canonical, digest

SCHEMA = 'clue_v2_live_diagnostic_receipt_v2'  # v2: additive expanding/rolling history provenance (C9)
FEATURE_SCOPES = {**dict.fromkeys(v2.FEATURES[:4], 'current_day_only'),
                  'new_action_count': 'expanding_history_days',
                  **dict.fromkeys(v2.FEATURES[5:], 'rolling_window_days')}
LABEL = 'experimental model diagnostic — not validated for this live source'
RECEIPT_SOURCES = ['scripts/live_receipts_clue_v2.py', 'scripts/tests/test_live_receipts_clue_v2.py',
                   'scripts/audit_clue_v2_live.py', 'scripts/explain_clue_v2.py', 'scripts/live_coverage_policy.py',
                   'scripts/shared_core_live_guard.py',
                   # coverage-policy dependencies shared with the AWS study (V3-bound; not edited here)
                   'scripts/live_history_readiness.py', 'scripts/persona_history_plan.py',
                   'scripts/persona_profiles_v2.json', 'scripts/simulation_lab.py']
TRANSFORM = 'log1p on event_count/unique_actions/unique_resources/new_action_count; fit-only standardisation; float32'


def load_bundle(prereg_path, training_dir):
    """Verified frozen W33 B/C artifacts as an explain bundle, plus their provenance hashes."""
    record, _, _ = trainer.verify_preregistration(prereg_path)
    training_dir = Path(training_dir)
    manifest = json.loads((training_dir / 'manifest.json').read_bytes())
    sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    hashes = {}
    for name in ('B', 'C'):
        model_sha, scaler_sha = sha(training_dir / name / 'model.pt'), sha(training_dir / name / 'scaler.json')
        if (manifest['detectors'][name]['model_sha256'] != model_sha
                or manifest['detectors'][name]['scaler_sha256'] != scaler_sha):
            raise ValueError(f'W33 detector {name} differs from its training manifest')
        hashes[name] = {'model_sha256': model_sha, 'scaler_sha256': scaler_sha}
    if manifest.get('preregistration_sha256') != record['receipt_sha256'] or manifest.get('activated') is not False:
        raise ValueError('W33 training manifest binding differs')
    bundle = {}
    for name, columns in (('C', v2.FEATURES), ('B', v2.FEATURES[:5])):
        model, scaler = trainer._reload_detector(training_dir / name, trainer.METHOD['detectors'][name]['architecture'])
        bundle[name] = (model, scaler, columns)
    provenance = {'profile': v2.PROFILE, 'detectors': hashes, 'preregistration_sha256': record['receipt_sha256'],
                  'training_manifest_sha256': sha(training_dir / 'manifest.json'),
                  'feature_contract_sha256': v2.contract_sha256(), 'coverage_policy_sha256': policy.policy_sha256(),
                  'coverage_policy_version': policy.POLICY['version'], 'transform': TRANSFORM,
                  'projection': 'shared_core_live_guard.project_live',
                  'source_sha256': reader.source_hashes(RECEIPT_SOURCES)}
    return bundle, provenance


def build_receipts(days, at, bundle, provenance, coverage, persona_accounts, aws_scope=None):
    """`days` from audit.closed_days; `coverage` maps (account_key, day) -> policy cell for persona accounts.

    A closed persona day with planned actions but no observed events still gets a (never scored) receipt,
    so a total collection gap stays visible instead of silently having no account-day."""
    at = audit.utc_cutoff(at)
    history, accepted_days, receipts = v2.History(), defaultdict(list), []
    start = policy.POLICY['history_start_local']
    gaps = {('aws_cloudtrail', aws_scope, account, date): None for (account, date), cell in coverage.items()
            if cell['status'] not in ('planned_idle', 'not_closed', 'usable')
            and ('aws_cloudtrail', aws_scope, account, date) not in days}
    for key, day in sorted({**days, **gaps}.items(), key=lambda item: (item[0][3], item[0][:3])):
        source, scope, account, date = key
        persona = source == 'aws_cloudtrail' and account in persona_accounts
        cell = coverage.get((account, date)) if persona else None
        if persona and (date < start or cell is None):
            policy_status = 'excluded_before_history_start' if date < start else 'no_policy_cell'
        elif persona:
            policy_status = cell['status']
        else:
            policy_status = 'outside_policy_completeness_unknown'
        allowed = (not persona) or policy_status == 'usable'
        receipt = {'schema': SCHEMA, 'label': LABEL, 'live_activation': False, 'alert': False, 'risk_tier': None,
                   'key': {'source': source, 'scope': scope, 'account': account, 'day': date},
                   'cutoff_utc': at.isoformat(), 'source_timezone': HOURS[source][0], 'provenance': provenance,
                   'history': {'prior_accepted_days': list(accepted_days[key[:3]]),  # v1 field, kept
                               'expanding_history_days': list(accepted_days[key[:3]]),
                               'rolling_window_days': accepted_days[key[:3]][-v2.WINDOW:],
                               'feature_history_scope': FEATURE_SCOPES,
                               'window_usable_days': v2.WINDOW, 'min_prior_usable_days': v2.K},
                   'coverage': {'policy_status': policy_status,
                                'scope_note': 'planned controlled actions only; not proof that no other activity '
                                              'occurred or that every log was collected',
                                'observed_events': day.core.count if day else 0,
                                **({k: cell[k] for k in ('planned', 'verified', 'missing', 'missed', 'unresolved',
                                                        'not_yet_ingested', 'commissioning_actions', 'case_actions',
                                                        'verified_native_event_ids')}
                                   if cell else {})},
                   'completeness': 'policy_verified' if persona and policy_status == 'usable' else 'unknown'}
        if allowed:
            state = history.state.get(key[:3])
            if (state.usable_days if state else 0) != len(accepted_days[key[:3]]) or (
                    len(state.window) if state else 0) != len(receipt['history']['rolling_window_days']):
                raise ValueError('Receipt history provenance differs from the feature history state')
            snapshot = history.snapshot(day)
            explanation = explain.explain(snapshot, history, day, bundle)  # before commit, same state
            receipt['input'] = {'status': snapshot['status'], 'five_feature_eligible': snapshot['five_feature_eligible'],
                                'nine_feature_eligible': snapshot['nine_feature_eligible'],
                                'issues': snapshot['issues'], 'why_unscored': explanation['why_unscored']}
            receipt['features'] = ({'names': v2.FEATURES, 'raw_values': snapshot['features']}
                                   if snapshot['features'] else None)
            receipt['detectors'] = {name: {'score_raw_mse': d['score_raw_mse'], 'space': d['space'], 'terms': d['terms']}
                                    for name, d in explanation['detectors'].items()}
            receipt['facts'] = explanation['facts']
            receipt['limitations'] = explanation['limitations']
            history.commit_original(day)
            if day.usable:
                accepted_days[key[:3]].append(date)
        else:
            receipt['input'] = {'status': 'not_scored_by_coverage_policy',
                                'why_unscored': f'Collection incomplete or excluded under coverage policy '
                                                f'v{policy.POLICY["version"]}: {policy_status}.'}
            receipt['features'], receipt['detectors'], receipt['facts'] = None, {}, []
            receipt['limitations'] = explain.LIMITATIONS
        receipt['receipt_id'] = digest({'key': receipt['key'], 'cutoff_utc': receipt['cutoff_utc'],
                                        'provenance': provenance})
        receipts.append(receipt)
    return receipts


def run(db_path, config_path, prereg_path, training_dir, output, at=None):
    output = Path(output).resolve()
    if output.exists() or not output.is_relative_to((ROOT / 'data').resolve()):
        raise ValueError('New private output directory below checkout data required')
    at = audit.utc_cutoff(at or datetime.now(timezone.utc))
    config = json.loads(Path(config_path).read_bytes())
    account, stack = config['account_id'], config['stack']
    ledger = Path(config['ledger_dir']) / 'ledger.db'
    db = Path(db_path).resolve()
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        records = [dict(row) for row in con.execute(
            'SELECT source,source_account_id,account_key,event_id,payload_digest,timestamp,action,resource,metadata,'
            'ingested_at FROM events ORDER BY id LIMIT ?', (audit.SNAPSHOT_CAP + 1,))]
    if len(records) > audit.SNAPSHOT_CAP:
        raise ValueError('Snapshot cap exceeded; no silent truncation')
    days, exclusions, labels = audit.closed_days(records, at)
    last_closed = max((key[3] for key in days), default=policy.POLICY['history_start_local'])
    persona_keys, mapping_diagnostics = policy.persona_account_keys(db, account, stack, at)  # same cut-off
    coverage = {}
    if last_closed >= policy.POLICY['history_start_local']:
        coverage = policy.accepted(policy.persona_day_coverage(ledger, db, account, stack, last_closed, at), persona_keys)
    bundle, provenance = load_bundle(prereg_path, training_dir)
    receipts = build_receipts(days, at, bundle, provenance, coverage, set(persona_keys.values()), account)
    body = b''.join(canonical(receipt) + b'\n' for receipt in receipts)
    manifest = {'schema': SCHEMA + '_manifest', 'cutoff_utc': at.isoformat(), 'label': LABEL,
                'receipts': len(receipts), 'receipts_sha256': hashlib.sha256(body).hexdigest(),
                'scored_receipts': sum(bool(r['detectors']) for r in receipts),
                'by_source_and_status': {f"{s}|{st}": n for (s, st), n in sorted(_counts(receipts).items())},
                'exclusions': {k: dict(v) for k, v in exclusions.items()}, 'unknown_action_labels': {k: dict(v) for k, v in labels.items()},
                'persona_mapping': mapping_diagnostics,
                'snapshot_note': 'event store and ledger are read as separate snapshots, not one atomic multi-file snapshot',
                'snapshot_rows': len(records), 'snapshot_sha256': hashlib.sha256(canonical(records)).hexdigest(),
                'provenance': provenance, 'live_activation': False, 'alerts_created': False}
    output.mkdir(parents=True)
    with (output / 'receipts.jsonl').open('xb') as handle:
        handle.write(body)
    with (output / 'manifest.json').open('xb') as handle:
        handle.write(canonical(manifest) + b'\n')
    return manifest


def _counts(receipts):
    counts = defaultdict(int)
    for receipt in receipts:
        counts[receipt['key']['source'], receipt['input']['status']] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('db', 'config', 'prereg', 'training', 'out'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    manifest = run(args.db, args.config, args.prereg, args.training, args.out)
    print(json.dumps({key: manifest[key] for key in ('receipts', 'scored_receipts', 'by_source_and_status')}))


if __name__ == '__main__':
    main()
