"""Versioned MY-time counts and categorical context for audited toy AWS reads."""
from collections import Counter
from datetime import datetime
import ipaddress

from scripts.persona_history_plan import MALAYSIA

FEATURES = ['event_count', 'get_object_count', 'head_object_count', 'get_bucket_location_count',
            'unique_resources', 'unique_valid_ips', 'off_hours_events', 'confidential_bucket_reads']
CONTRACT = {
    'profile': 'aws_lab_daily_v1', 'features': FEATURES, 'units': 'nonnegative_integer_counts',
    'timezone': 'Asia/Kuala_Lumpur', 'normal_hours': 'Mon-Fri 08:00 inclusive to 20:00 exclusive',
    'window': 'one closed MY calendar date per restricted lab role',
    'allowed_operations': ['GetObject', 'HeadObject', 'GetBucketLocation'],
    'resource_domain': ['p01', 'p02', 'p03', 'p04', 'p05', 'p06', 'confidential'],
    'history': 'none in extraction; fit account-conditioned reference on fitting partition only',
    'missing_ip': 'excluded from distinct valid IP count; missing/invalid counts reported separately',
    'empty_window': 'refuse; never impute missing activity as zero normal observations',
    'categorical_context': 'action_counts, resource_counts, local_hour_counts; descriptive counts only',
    'compatibility': 'new profile; incompatible with legacy12, CERT71 and CLUE10 weights/scalers/thresholds',
}


def extract(events, resources):
    if not events:
        raise ValueError('Empty window is not an observation')
    if set(resources.values()) != set(CONTRACT['resource_domain']) or len(resources) != 7:
        raise ValueError('Exact toy resource mapping required')
    actions, buckets, hours = Counter(), Counter(), Counter()
    ips = set()
    missing, invalid, off_hours = 0, 0, 0
    dates, roles = set(), set()
    for event in events:
        stamp = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('Zoned native timestamp required')
        local = stamp.astimezone(MALAYSIA)
        dates.add(local.date().isoformat())
        roles.add(event['persona'])
        if event['day'] != local.date().isoformat():
            raise ValueError('Native local day differs from audited day')
        if event['action'] not in CONTRACT['allowed_operations'] or event['resource'] not in resources:
            raise ValueError('Unexpected operation or resource')
        actions[event['action']] += 1
        buckets[resources[event['resource']]] += 1
        hours[f'{local.hour:02d}'] += 1
        off_hours += int(local.weekday() >= 5 or not 8 <= local.hour < 20)
        ip = event.get('ip_address')
        if ip is None or ip == '':
            missing += 1
        elif isinstance(ip, str):
            try:
                ips.add(str(ipaddress.ip_address(ip)))
            except ValueError:
                invalid += 1
        else:
            invalid += 1
    if len(dates) != 1 or len(roles) != 1:
        raise ValueError('One role and local day per window required')
    return {'features': dict(zip(FEATURES, [len(events), actions['GetObject'], actions['HeadObject'],
                actions['GetBucketLocation'], len(buckets), len(ips), off_hours, buckets['confidential']])),
            'action_counts': dict(sorted(actions.items())), 'resource_counts': dict(sorted(buckets.items())),
            'local_hour_counts': dict(sorted(hours.items())),
            'ip_observability': {'valid_events': len(events) - missing - invalid,
                                 'missing_events': missing, 'invalid_events': invalid}}
