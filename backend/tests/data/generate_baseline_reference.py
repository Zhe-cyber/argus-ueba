"""One-off generator for baseline_reference_v1_1.json (L8 step 1, run on the pre-move code on 2026-11-12).

Synthetic account-day cases only (no live data). Each case stores its inputs (event rows, scored day, extra
sensitive regexes) and the scorer's output at generation time. test_baseline_reference.py replays them.
Refuses to overwrite an existing file: the vectors are the algorithm-identity record, not a moving target.

    python -m backend.tests.data.generate_baseline_reference
"""
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

from backend.tests.test_baseline_reference import OUT, compute

MYT = timezone(timedelta(hours=8))
DAY = date(2026, 10, 20)
AWS, GH, CF = 'aws_cloudtrail', 'github_events', 'cloudflare_access'


def at(offset, hh, mm=0, day=DAY):
    """UTC 'Z' stamp for hh:mm MYT on day - offset."""
    local = datetime.combine(day - timedelta(days=offset), datetime.min.time(), tzinfo=MYT) + timedelta(hours=hh, minutes=mm)
    return local.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def ev(offset, hh, action='GetObject', resource='lab-p01', source=AWS, n=1, mm=0):
    return [[at(offset, hh, mm), source, action, resource]] * n


def hist(days=6, hh=10, per_day=4, action='GetObject', resource='lab-p01', source=AWS, start=1):
    return [r for o in range(start, start + days) for r in ev(o, hh, action, resource, source, per_day)]


def case(name, rows, day=DAY, extra=()):
    return {'name': name, 'day': day.isoformat(), 'extra_sensitive_regex': list(extra), 'rows': rows}


CASES = [
    case('learning_no_history', ev(0, 10, n=3)),
    case('learning_four_days', hist(4) + ev(0, 10, n=4)),
    case('exactly_five_days_scored', hist(5) + ev(0, 10, n=4)),
    case('quiet_normal_low', hist() + ev(0, 10, n=4)),
    case('one_new_action', hist() + ev(0, 10, n=3) + ev(0, 10, 'PutObject')),
    case('two_new_actions', hist() + ev(0, 10, n=2) + ev(0, 10, 'PutObject') + ev(0, 10, 'DeleteObject')),
    case('one_new_resource', hist() + ev(0, 10, n=3) + ev(0, 10, resource='lab-p02')),
    case('five_new_resources_more_suffix', hist() + [r for i in range(2, 7) for r in ev(0, 10, resource=f'lab-p0{i}')]),
    case('no_resource_today_unavailable', hist() + ev(0, 10, 'ListBuckets', '', n=4)),
    case('mixed_empty_and_resource_today', hist() + ev(0, 10, 'ListBuckets', '', n=2) + ev(0, 10, n=2)),
    case('unusual_hours_all_outside', hist() + ev(0, 3, n=4)),
    case('unusual_hours_quarter_outside', hist() + ev(0, 10, n=3) + ev(0, 3)),
    case('usual_widening_lower_edge', hist() + ev(0, 9, n=4)),
    case('usual_widening_upper_edge', hist() + ev(0, 11, n=4)),
    case('two_hours_off_is_outside', hist() + ev(0, 12, n=4)),
    case('midnight_wrap_history_23_today_00', hist(hh=23) + ev(0, 0, n=4)),
    case('midnight_wrap_history_00_today_23', hist(hh=0) + ev(0, 23, n=4)),
    case('core_hour_below_five_percent_not_usual',
         [r for o in range(1, 7) for r in ev(o, 10, n=20) + (ev(o, 15) if o == 1 else [])] + ev(0, 15, n=4)),
    case('volume_8x', hist() + ev(0, 10, n=32)),
    case('volume_2x', hist() + ev(0, 10, n=8)),
    case('volume_drop_zero', hist(per_day=8) + ev(0, 10, n=1)),
    case('volume_even_median',
         [r for o, k in zip(range(1, 7), (2, 4, 6, 8, 10, 12)) for r in ev(o, 10, n=k)] + ev(0, 10, n=28)),
    case('sensitive_new_builtin', hist() + ev(0, 10, n=3) + ev(0, 10, resource='secretsmanager/prod-key')),
    case('sensitive_seen_before_is_zero', hist() + ev(2, 10, resource='secretsmanager/prod-key') + ev(0, 10, resource='secretsmanager/prod-key')),
    case('sensitive_list_confidential_bucket', hist() + ev(0, 10, n=3) + ev(0, 10, resource='lab-confidential'),
         extra=['confidential']),
    case('confidential_github_repo_builtin_only', hist(source=GH, action='PushEvent', resource='org/app')
         + ev(0, 10, 'PushEvent', 'org/confidential-notes', GH)),
    case('novelty_discount_actions_crawler', [r for o in range(1, 8) for r in ev(o, 10, f'Act{o}')] + ev(0, 10, 'NewAct')),
    case('novelty_discount_resources_crawler', [r for o in range(1, 8) for r in ev(o, 10, resource=f'tbl-{o}')]
         + ev(0, 10, resource='tbl-new') + ev(0, 10, resource='tbl-new2')),
    case('novelty_rate_half', [r for o in range(1, 9) for r in ev(o, 10, f'Act{o}' if o % 2 else 'GetObject')] + ev(0, 10, 'PutObject')),
    case('novelty_rate_below_quarter_no_fact', hist(8) + ev(5, 10, 'Rare') + ev(0, 10, 'PutObject')),
    case('sensitive_with_resource_discount', [r for o in range(1, 8) for r in ev(o, 10, resource=f'tbl-{o}')]
         + ev(0, 10, resource='kms/key-1')),
    case('myt_boundary_1630_utc_next_day', hist() + [['2026-10-19T16:30:00Z', AWS, 'GetObject', 'lab-p01']] * 4),
    case('myt_boundary_1559_utc_same_day', hist(start=2) + [['2026-10-19T15:59:00Z', AWS, 'GetObject', 'lab-p01']] * 4,
         day=date(2026, 10, 19)),
    case('window_28_days_included', hist(4, start=1) + ev(28, 10, 'OldAct') + ev(0, 10, 'OldAct', n=4)),
    case('window_29_days_excluded', hist(4, start=1) + ev(29, 10, 'OldAct') + ev(0, 10, 'OldAct', n=4)),
    case('unparseable_and_naive_timestamps_skipped', hist() + ev(0, 10, n=4)
         + [['not-a-time', AWS, 'Weird', 'x'], ['2026-10-20T10:00:00', AWS, 'Naive', 'y']]),
    case('offset_and_fraction_timestamps', hist() + [['2026-10-20T10:15:30.123+08:00', AWS, 'GetObject', 'lab-p01']] * 4),
    case('mixed_sources_action_identity', hist() + ev(0, 10, 'GetObject', 'lab-p01', CF) + ev(0, 10, n=3)),
    case('request_parameter_blob_names', hist() + ev(0, 10, resource='{"bucketName": "lab-p09", "key": "k"}')),
    case('twelve_digit_masked_in_facts', hist() + ev(0, 10, resource='arn:aws:s3:::lab-123456789012-p09')),
    case('long_name_cut_at_60', hist() + ev(0, 10, resource='r' * 90)),
    case('high_combination', hist() + ev(0, 21, 'PutObject', 'lab-confidential-x', n=12) + ev(0, 21, 'DeleteObject', 'iam/role', n=12)),
    case('medium_combination', hist() + ev(0, 10, n=2) + ev(0, 10, 'PutObject', 'lab-p02')),
    case('sparse_history_with_gaps', [r for o in (1, 4, 9, 15, 27) for r in ev(o, 10, n=2)] + ev(0, 10, n=2)),
    case('today_spans_two_hours_partly_outside', hist() + ev(0, 11, n=2) + ev(0, 14, n=2)),
    case('github_account_scored', hist(source=GH, action='PushEvent', resource='org/app') + ev(0, 22, 'CreateEvent', 'org/app', GH)),
    case('cloudflare_token_scored', hist(source=CF, action='GET', resource='host/workloads/persona-02/a')
         + ev(0, 21, 'GET', 'host/workloads/persona-02/demo-1', CF, n=8)),
]


def main():
    if OUT.exists():
        raise SystemExit(f'{OUT.name} exists; the reference vectors are never regenerated in place')
    for c in CASES:
        c['expected'] = compute(c)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'version': 'baseline v1.1', 'generated': '2026-11-12', 'cases': CASES}, indent=1) + '\n', encoding='utf-8')
    print(f'wrote {len(CASES)} cases')


if __name__ == '__main__':
    main()
