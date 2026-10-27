"""Offline, non-executing draft sampler. Outputs plans, never provider events."""
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
import argparse, hashlib, json, random

HERE = Path(__file__).resolve().parent
OPERATIONS = {'GetObject', 'HeadObject', 'GetBucketLocation'}
RESOURCES = {f'p{i:02d}' for i in range(1, 7)} | {'confidential'}
MALAYSIA = timezone(timedelta(hours=8))

def weighted(rng, values):
    if not values or any(not isinstance(v, (int, float)) or v < 0 for v in values.values()):
        raise ValueError('Invalid weight')
    if abs(sum(values.values()) - 1) > 1e-9:
        raise ValueError('Weights must sum to one')
    return rng.choices(list(values), weights=list(values.values()), k=1)[0]

def make_plan(profiles, day):
    if profiles['automated_cloudflare'] or profiles['automated_github']:
        raise ValueError('Only AWS symbolic offline plans are supported')
    rows, idle = [], []
    for profile in profiles['personas']:
        seed = hashlib.sha256(f"{profiles['global_seed']}|{profile['id']}|{day.isoformat()}".encode()).hexdigest()
        rng = random.Random(int(seed, 16))
        probability = profile['weekend_active_probability' if day.weekday() >= 5 else 'weekday_active_probability']
        if not 0 <= probability <= 1:
            raise ValueError('Invalid probability')
        if rng.random() >= probability:
            idle.append({'persona': profile['id'], 'status': 'planned_idle_not_observed'})
            continue
        low, high = profile['action_count_range']
        if not 1 <= low <= high <= profiles['max_actions_per_persona_day']:
            raise ValueError('Per-persona budget exceeded')
        for index in range(rng.randint(low, high)):
            operation = weighted(rng, profile['operation_weights'])
            resource = weighted(rng, profile['resource_weights'])
            if operation not in OPERATIONS or resource not in RESOURCES:
                raise ValueError('Unsupported symbolic action or target')
            start, end = rng.choice(profile['local_session_windows'])
            if not 0 <= start < end <= 24:
                raise ValueError('Invalid local window')
            minute = rng.randrange(start * 60, end * 60)
            planned = datetime(day.year, day.month, day.day, tzinfo=MALAYSIA) + timedelta(minutes=minute)
            rows.append({'persona': profile['id'], 'ordinal': index,
                         'planned_local': planned.isoformat(), 'planned_utc': planned.astimezone(timezone.utc).isoformat(),
                         'operation': operation, 'symbolic_bucket': resource, 'key': 'fixture.txt',
                         'status': 'planned_not_executed'})
    rows.sort(key=lambda row: (row['planned_utc'], row['persona'], row['ordinal']))
    reserved = profiles['reserved_preflight_and_role_calls']
    if len(rows) + reserved > min(profiles['max_sdk_calls_per_run'], 64):
        raise ValueError('Total request budget exceeded')
    return {'schema': 'argus_offline_plan_draft_v1', 'date_local': day.isoformat(),
            'parameter_provenance': profiles['parameter_provenance'], 'executed': False,
            'provider_events_created': 0, 'planned_actions': len(rows),
            'reserved_sdk_calls': reserved, 'actions': rows, 'planned_idle': idle,
            'limitations': 'Independent time draws, illustrative weights. Session burstiness and correlated provider jobs not implemented. Not training data.'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', required=True, type=date.fromisoformat)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    raw = (HERE / 'persona_profiles_v1.json').read_bytes()
    profiles = json.loads(raw)
    plan = make_plan(profiles, args.date)
    assert plan == make_plan(profiles, args.date), 'Sampler must reproduce exactly'
    plan['profile_sha256'] = hashlib.sha256(raw).hexdigest()
    args.out.write_text(json.dumps(plan, indent=2), encoding='utf-8')
    print(json.dumps({'date_local': plan['date_local'], 'planned_actions': plan['planned_actions'],
                      'personas': len(profiles['personas']), 'executed': False, 'provider_events_created': 0}))

if __name__ == '__main__':
    main()
