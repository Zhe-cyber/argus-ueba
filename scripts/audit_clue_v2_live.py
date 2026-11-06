"""W33 v2 live compatibility diagnostics: v2 features and frozen B/C/BL scores on closed live days.

Read-only (SQLite mode=ro). Diagnostics only, per the W33 live section: projection-valid and
invalid days, eligibility, missingness, constant features, transformed values outside the
observed CLUE fitting range, and raw score distributions with coverage. Nothing here alerts,
writes to the live store, changes a model or threshold, or activates live scoring.

- A projection-valid day is not a complete normal day: scheduled activity may be missing, and
  five such days permit mechanical input construction, not a reliable baseline. This does not
  replace the AWS study's own coverage gates.
- CLUE-calibrated cut-offs are descriptive reference points only, never live alert rates.
- C-norm is unavailable for live accounts by design (references exist only for the CLUE cohort).
- Accounts whose activity this feature contract cannot represent (service roles, infrastructure,
  some bots) remain legitimate security entities; they are reported as unsupported by this
  contract, not as out of scope for security.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import clue_v2_features as v2, train_clue_v2 as trainer, clue_v2_reader as reader
from scripts.shared_core_features import HOURS, canonical, instant
from scripts.shared_core_live_guard import project_live

SOURCES = ('aws_cloudtrail', 'cloudflare_access', 'github_events')
Z_LARGE = 4.0  # descriptive "large standardised magnitude"; not a tuning or gating statistic
AUDIT_SOURCES = ['scripts/audit_clue_v2_live.py', 'scripts/tests/test_clue_v2_live_audit.py']
SNAPSHOT_CAP = 200_000


def utc_cutoff(at):
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError('Zoned cut-off required')
    return at.astimezone(timezone.utc)


def closed_days(records, at):
    """Group projectable live events into closed local days; count every exclusion by reason.

    Ingestion times are compared as UTC instants; future or malformed ingestion times are excluded."""
    at = utc_cutoff(at)
    days, exclusions, labels = {}, defaultdict(Counter), defaultdict(Counter)
    for row in records:
        source = row.get('source')
        if source not in SOURCES:
            exclusions['unsupported_source'][str(source)] += 1
            continue
        try:
            ingested = instant(row.get('ingested_at'))
        except (ValueError, TypeError):
            exclusions[source]['malformed_ingestion_time'] += 1
            continue
        if ingested > at:
            exclusions[source]['ingested_after_cutoff'] += 1
            continue
        try:
            event = project_live(row)
        except (ValueError, TypeError, KeyError):
            exclusions[source]['projection_rejected'] += 1
            continue
        if event.timestamp > at:
            exclusions[source]['future_event'] += 1
            continue
        if event.day >= at.astimezone(ZoneInfo(HOURS[source][0])).date().isoformat():
            exclusions[source]['current_day_partial'] += 1
            continue
        if event.issue == 'unknown_action':
            labels[source][row.get('action')] += 1
        days.setdefault((event.source, event.scope, event.account, event.day), v2.V2Day()).add(event)
    return days, exclusions, labels


def snapshots(days):
    """W33 history per (source, scope, account): start-of-day snapshot, then commit the original."""
    history, out = v2.History(), []
    for key, day in sorted(days.items(), key=lambda item: (item[0][3], item[0][:3])):
        out.append({'source': key[0], 'scope': key[1], 'account': key[2], 'day': key[3], **history.snapshot(day)})
        history.commit_original(day)
    return out


def load_live_scorer(prereg_path, training_dir):
    """Verified frozen W33 B/C artifacts; BL from C's scaled inputs. No C-norm for live accounts."""
    record, _, rows = trainer.verify_preregistration(prereg_path)
    training_dir = Path(training_dir)
    manifest = json.loads((training_dir / 'manifest.json').read_bytes())
    sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if (manifest.get('preregistration_sha256') != record['receipt_sha256'] or manifest.get('activated') is not False
            or any(manifest['detectors'][d]['model_sha256'] != sha(training_dir / d / 'model.pt')
                   or manifest['detectors'][d]['scaler_sha256'] != sha(training_dir / d / 'scaler.json') for d in ('B', 'C'))
            or manifest['thresholds_sha256'] != sha(training_dir / 'thresholds.json')):
        raise ValueError('W33 training artifacts differ from their manifest')
    b_model, b_scaler = trainer._reload_detector(training_dir / 'B', trainer.METHOD['detectors']['B']['architecture'])
    c_model, c_scaler = trainer._reload_detector(training_dir / 'C', trainer.METHOD['detectors']['C']['architecture'])
    stored = json.loads((training_dir / 'thresholds.json').read_bytes())
    cutoffs = {name: {b: stored[name][b]['threshold'] for b in ('0.01', '0.05')} for name in ('B', 'C', 'BL')}
    fit = c_scaler.transform(trainer.matrix(trainer.nine_rows(rows['fit']), v2.FEATURES))
    fit_range = {'min': [float(v) for v in fit.min(axis=0)], 'max': [float(v) for v in fit.max(axis=0)]}

    def score(snapshot):
        result = {'B': None, 'C': None, 'BL': None, 'z': None}
        if not snapshot['five_feature_eligible']:
            return result
        features = snapshot['features']
        five = dict(features, new_resource_share=0.0 if features['new_resource_share'] is None else features['new_resource_share'])
        result['B'] = trainer.score_rows(b_model, b_scaler.transform(trainer.matrix([{'features': five}], v2.FEATURES[:5])))[0]
        if snapshot['nine_feature_eligible']:
            x = c_scaler.transform(trainer.matrix([{'features': features}], v2.FEATURES))
            result['C'] = trainer.score_rows(c_model, x)[0]
            result['BL'] = float(max(0.0, float(x[0].max())))
            result['z'] = [float(value) for value in x[0]]
        return result

    return score, cutoffs, fit_range, {'preregistration_sha256': record['receipt_sha256'],
                                       'training_manifest_sha256': sha(training_dir / 'manifest.json')}


def _distribution(values):
    if not values:
        return None
    ordered = sorted(values)
    return {'n': len(values), 'min': ordered[0], 'median': statistics.median(ordered), 'max': ordered[-1]}


def summarise(rows, score, cutoffs, fit_range, exclusions, labels):
    result = {}
    for source in SOURCES:
        items = [row for row in rows if row['source'] == source]
        scored = [(row, score(row)) for row in items]
        nine = [(row, s) for row, s in scored if s['C'] is not None]
        features = {name: [row['features'][name] for row, _ in nine] for name in v2.FEATURES}
        large = {name: sum(abs(s['z'][i]) > Z_LARGE for _, s in nine) for i, name in enumerate(v2.FEATURES)}
        outside = {name: sum(not fit_range['min'][i] <= s['z'][i] <= fit_range['max'][i] for _, s in nine)
                   for i, name in enumerate(v2.FEATURES)}
        accounts = defaultdict(Counter)
        for row in items:
            accounts[(row['scope'], row['account'])][row['status']] += 1
        status = Counter(row['status'] for row in items)
        issues = Counter()
        for row in items:
            issues.update(row['issues'])
        entry = {'observed_closed_account_days': len(items), 'observed_accounts': len({r['account'] for r in items}),
                 'status_counts': dict(sorted(status.items())),
                 'projection_valid_days': sum(r['status'] != 'invalid_input' for r in items),
                 'per_account_status': [{'scope': scope, 'account': account, **dict(sorted(counts.items()))}
                                        for (scope, account), counts in sorted(accounts.items())],
                 'five_feature_eligible_days': sum(r['five_feature_eligible'] for r in items),
                 'nine_feature_eligible_days': len(nine),
                 'accounts_with_nine_feature_days': len({row['account'] for row, _ in nine}),
                 'invalid_day_issue_events': dict(sorted(issues.items())),
                 'unknown_action_labels': dict(sorted(labels.get(source, {}).items())),
                 'exclusions': dict(sorted(exclusions.get(source, {}).items())),
                 'constant_features_on_nine_feature_days': [n for n, v in features.items() if len(v) > 1 and len(set(v)) == 1],
                 'outside_observed_clue_fit_range': {n: c for n, c in outside.items() if c},
                 'large_standardised_magnitude_abs_z_gt_4': {n: c for n, c in large.items() if c},
                 'raw_scores': {name: _distribution([s[name] for _, s in scored if s[name] is not None])
                                for name in ('B', 'C', 'BL')},
                 'above_clue_cutoff_descriptive_only': {
                     name: {b: sum(s[name] is not None and s[name] > cutoffs[name][b] for _, s in scored) for b in ('0.01', '0.05')}
                     for name in ('B', 'C', 'BL')},
                 'c_norm': 'unavailable_by_design_no_live_reference'}
        if not items:
            entry['decision'] = 'no_observed_closed_days'
        elif not nine:
            entry['decision'] = 'extractor_runs_no_nine_feature_input_yet'
        elif entry['constant_features_on_nine_feature_days'] or entry['outside_observed_clue_fit_range']:
            entry['decision'] = 'model_input_available_with_representation_warnings'
        else:
            entry['decision'] = 'model_input_available_not_validated'
        result[source] = entry
    return result


def audit(db_path, prereg_path, training_dir, at=None):
    at = utc_cutoff(at or datetime.now(timezone.utc))
    db = Path(db_path).resolve()
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        # No SQL text comparison of timestamps: the cut-off is applied to parsed UTC instants in closed_days.
        records = [dict(row) for row in con.execute(
            'SELECT source,source_account_id,account_key,event_id,payload_digest,timestamp,action,resource,metadata,'
            'ingested_at FROM events ORDER BY id LIMIT ?', (SNAPSHOT_CAP + 1,))]
    if len(records) > SNAPSHOT_CAP:
        raise ValueError('Snapshot cap exceeded; no silent truncation')
    score, cutoffs, fit_range, bindings = load_live_scorer(prereg_path, training_dir)
    days, exclusions, labels = closed_days(records, at)
    rows = snapshots(days)
    return {'profile': v2.PROFILE, 'status': 'live_compatibility_diagnostics_only', 'cutoff_utc': at.isoformat(),
            'sources': summarise(rows, score, cutoffs, fit_range, exclusions, labels),
            'live_activation': False, 'alerts_created': False,
            'interpretation': ['Observed activity, not verified normal; collection completeness unknown.',
                               'Projection-valid days are not complete normal days; five permit input construction, '
                               'not a reliable baseline, and do not replace the AWS study coverage gates.',
                               'CLUE cut-offs are reference points from CLUE normal days, not live alert rates.',
                               'A nine-feature input that scores is not evidence of live detection accuracy.',
                               'Accounts unsupported by this feature contract remain legitimate security entities.'],
            'bindings': {**bindings, 'snapshot_rows': len(records),
                         'snapshot_sha256': hashlib.sha256(canonical(records)).hexdigest(),
                         'source_sha256': reader.source_hashes(AUDIT_SOURCES)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('db', 'prereg', 'training', 'out'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    if out.exists() or not out.is_relative_to((ROOT / 'data').resolve()) or not Path(args.db).is_file():
        parser.error('Require an existing SQLite store and a new private output below checkout data')
    result = audit(args.db, args.prereg, args.training)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    print(json.dumps({s: {k: v[k] for k in ('observed_closed_account_days', 'nine_feature_eligible_days', 'decision')}
                      for s, v in result['sources'].items()}))


if __name__ == '__main__':
    main()
