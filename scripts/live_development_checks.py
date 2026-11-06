"""Normal development data only: prediction, not calibration or case evaluation."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import export_live_daily as exporter, live_daily_method as method, train_live_daily as trainer
from scripts import reserved_study
from scripts.persona_history_plan import make_plan, MALAYSIA

DEADLINE = reserved_study.protocol.SOURCE_COMMIT_BEFORE


def read_development(directory, now):
    if now >= DEADLINE:
        raise ValueError('Development diagnostic closes before calibration on 10 November')
    directory = Path(directory)
    raw = (directory / 'dataset.json').read_bytes()
    manifest = json.loads((directory / 'manifest.json').read_text())
    data = json.loads(raw)
    reserved_study.protocol.require_binding(data)
    reserved_study.protocol.require_binding(manifest)
    if (trainer.sha(directory / 'dataset.json') != manifest.get('dataset_sha256')
            or trainer.sha(directory / 'feature_contract.json') != trainer.CONTRACT_SHA
            or data.get('profile') != 'aws_lab_daily_v1'
            or data.get('dataset_kind') != 'audited_aws_daily_workloads'
            or data.get('provenance', {}).get('source_sha256') != exporter.hashes()
            or data.get('provenance', {}).get('profile_sha256') != exporter.readiness.PROFILE_SHA
            or trainer.sha(ROOT / 'scripts/persona_profiles_v2.json') != exporter.readiness.PROFILE_SHA):
        raise ValueError('Audited development export binding differs')
    if any(r.get('partition') not in ('fit', 'validation') for r in data['rows']):
        raise ValueError('Calibration/case data forbidden in development diagnostic')
    coverage = {(r['day'], r['persona']): r for r in data['readiness']['days'] if r['status'] == 'usable'}
    seen, rows, excluded = set(), [], []
    for row in data['rows']:
        day, role, part = row['date_local'], row['persona'], row['partition']
        key = day, role
        start, end = exporter.readiness.WINDOWS[part]
        if (key in seen or role not in method.ROLES or not start <= day <= end
                or day >= now.astimezone(MALAYSIA).date().isoformat()
                or row.get('complete_day') is not True or key not in coverage):
            raise ValueError('Wrong/duplicate/open development row')
        seen.add(key)
        values, cv = row['features'], row['coverage']
        if (set(values) != set(trainer.FEATURES)
                or any(type(v) is not int or not 0 <= v <= 5 for v in values.values())
                or not 1 <= values['event_count'] <= 5
                or cv['verified'] != values['event_count'] or cv['unresolved'] != 0
                or cv['verified'] * 10 < cv['planned'] * 9
                or any(cv[k] != coverage[key][k] for k in cv)):
            raise ValueError('Invalid audited counts')
        for name, domain in [('resource_counts', method.DOMAIN),
                             ('action_counts', exporter.CONTRACT['allowed_operations']),
                             ('local_hour_counts', [f'{h:02d}' for h in range(24)])]:
            if not trainer.positive_counts(row[name], domain) or sum(row[name].values()) != values['event_count']:
                raise ValueError('Invalid categorical context')
        ip = row['ip_observability']
        if (any(type(v) is not int or v < 0 for v in ip.values())
                or sum(ip.values()) != values['event_count']):
            raise ValueError('Invalid IP observability')
        if ip['missing_events'] or ip['invalid_events']:
            excluded.append({'date_local': day, 'persona': role, 'reason': 'incomplete_ip_context'})
            continue
        rows.append(deepcopy(row))
    return data, manifest, rows, excluded


def fitting_ready(rows):
    for role in method.ROLES:
        dates = sorted(r['date_local'] for r in rows if r['partition'] == 'fit' and r['persona'] == role)
        if len(dates) < 5 or (datetime.fromisoformat(dates[-1]) - datetime.fromisoformat(dates[0])).days < 6:
            return False
    return True


def sensitivity(directory, now=None):
    now = now or datetime.now(timezone.utc)
    data, manifest, rows, excluded = read_development(directory, now)
    report = {'schema': 'argus_expected_sensitivity_v1', 'computed_at_utc': now.isoformat(),
              'input_dataset_sha256': manifest['dataset_sha256'], 'excluded': excluded,
              'diagnostic_source_sha256': trainer.sha(__file__),
              'status': 'pending_fitting_history', 'prediction_only': True, 'activated': False,
              'limitations': ['Development counterfactuals are not held-out cases or detection results.',
                              'Fitting scores are in-sample; validation is limited to available closed days.',
                              'No calibration threshold estimated or inspected. No method/scenario change allowed.']}
    profiles = json.loads((ROOT / 'scripts/persona_profiles_v2.json').read_text())
    slots = []
    for day in reserved_study.CASES:
        planned = make_plan(profiles, datetime.fromisoformat(day).date())
        for role in reserved_study.TARGETS:
            own = [r for r in planned['actions'] if r['persona'] == role]
            reads = [r for r in own if r['operation'] == 'GetObject']
            if not reads:
                slots.append({'date_local': day, 'persona': role, 'planned_event_count': len(own),
                              'status': 'unavailable_no_planned_target_read', 'predicted_delta': None,
                              'basis': 'frozen_schedule_only_not_native_outcomes'})
                continue
            first = min(reads, key=lambda r: (r['planned_utc'], r['ordinal']))
            counts = Counter(r['symbolic_bucket'] for r in own)
            changed = counts.copy()
            changed[first['symbolic_bucket']] -= 1
            changed['p06'] += 1
            slots.append({'date_local': day, 'persona': role, 'planned_event_count': len(own),
                          'old_resource': first['symbolic_bucket'], 'new_resource': 'p06',
                          'ae_unique_resource_delta_if_all_other_context_matches': len(+changed) - len(counts),
                          'basis': 'frozen_schedule_only_not_native_outcomes', 'predicted_delta': None})
    report['reserved_slot_predictions'] = slots
    if not fitting_ready(rows):
        return report
    fit = [r for r in rows if r['partition'] == 'fit']
    refs = method.fit_references(fit)
    normal = [method.context_scores(refs, r)['personal'] for r in rows]
    for slot in slots:
        if slot.get('status') == 'unavailable_no_planned_target_read':
            continue
        prob = refs['personal'][slot['persona']]
        slot['predicted_delta'] = math.log(prob[slot['old_resource']] / prob['p06']) / slot['planned_event_count']
        slot['reference_basis'] = 'fitting_rows_only'
    samples = []
    for row in rows:
        if row['persona'] not in ('persona-01', 'persona-02'):
            continue
        plan = make_plan(profiles, datetime.fromisoformat(row['date_local']).date())
        own = [r for r in plan['actions'] if r['persona'] == row['persona']]
        if (Counter(r['symbolic_bucket'] for r in own) != Counter(row['resource_counts'])
                or Counter(r['operation'] for r in own) != Counter(row['action_counts'])):
            raise ValueError('Development histogram differs from frozen planned receipts')
        eligible = [r for r in own if r['operation'] == 'GetObject']
        if not eligible:
            samples.append({'date_local': row['date_local'], 'persona': row['persona'],
                            'status': 'no_planned_GetObject'})
            continue
        first = min(eligible, key=lambda r: (r['planned_utc'], r['ordinal']))
        old = first['symbolic_bucket']
        counts = Counter(row['resource_counts'])
        counts[old] -= 1
        counts['p06'] += 1
        counts = {k: v for k, v in counts.items() if v}
        before = method.excess(refs['personal'][row['persona']], row['resource_counts'])
        after = method.excess(refs['personal'][row['persona']], counts)
        exact = math.log(refs['personal'][row['persona']][old] / refs['personal'][row['persona']]['p06']) / row['features']['event_count']
        samples.append({'date_local': row['date_local'], 'persona': row['persona'], 'partition': row['partition'],
                        'event_count': row['features']['event_count'], 'old_resource': old,
                        'normal_score': before, 'hypothetical_score': after, 'exact_delta': exact,
                        'above_observed_development_max': after > max(normal),
                        'ae_unique_resource_delta': len(counts) - len(row['resource_counts']),
                        'status': 'development_counterfactual'})
    report.update({'status': 'development_prediction_computed', 'normal_development_range': [min(normal), max(normal)],
                   'normal_account_days': len(rows), 'validation_account_days': sum(r['partition'] == 'validation' for r in rows),
                   'fitting_events_per_role': {role: sum(r['features']['event_count'] for r in fit if r['persona'] == role)
                                               for role in method.ROLES},
                   'samples': samples, 'future_calibration_threshold': 'unknown'})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        result = sensitivity(args.data)
        with Path(args.out).open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
        print(json.dumps({'status': result['status'], 'prediction_only': True}))
        return 0
    except Exception:
        print('Development diagnostic refused; check date, normal-only inputs and fresh output.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
