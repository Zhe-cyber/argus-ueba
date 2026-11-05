"""Prospective AWS V3 calendar and artifact identity; no cloud calls or overrides."""
from datetime import datetime, timezone, timedelta
import hashlib
import json

MALAYSIA = timezone(timedelta(hours=8))
PROTOCOL = 'aws_controlled_study_v3'
WINDOWS = {'fit': ('2026-11-01', '2026-11-07'),
           'validation': ('2026-11-08', '2026-11-09'),
           'normal_calibration': ('2026-11-10', '2026-11-12')}
CASES = {'2026-11-14': 'unannounced_controlled_change',
         '2026-11-15': 'approved_legitimate_change'}
FREEZE_DAY = '2026-11-13'
SOURCE_COMMIT_BEFORE = datetime(2026, 11, 10, tzinfo=MALAYSIA)
RECEIPT_CUTOFF = datetime(2026, 11, 15, 20, tzinfo=MALAYSIA)
EVALUATE_FROM = datetime(2026, 11, 16, tzinfo=MALAYSIA)
ACTOR_END = '2026-11-15'
SERVICE_END_LOCAL = '2026-11-16'  # Inclusive service date; expires next midnight.
SERVICE_EXPIRES = datetime(2026, 11, 17, tzinfo=MALAYSIA)
RELEASE_NAME = 'reserved-release-v3.json'
RELEASE_SCHEMA = 'argus_reserved_release_v3'
DATASET_SCHEMA = 'argus_live_daily_dataset_v3'


def binding():
    return {'protocol': PROTOCOL, 'windows': {k: list(v) for k, v in WINDOWS.items()},
            'cases': dict(CASES), 'freeze_day': FREEZE_DAY,
            'source_commit_before_my': SOURCE_COMMIT_BEFORE.isoformat(),
            'receipt_cutoff_my': RECEIPT_CUTOFF.isoformat(),
            'evaluate_from_my': EVALUATE_FROM.isoformat(),
            'actor_end': ACTOR_END, 'service_expires_my': SERVICE_EXPIRES.isoformat()}


def binding_sha256():
    return hashlib.sha256(json.dumps(binding(), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def require_binding(value):
    if value.get('study') != binding() or value.get('study_sha256') != binding_sha256():
        raise ValueError('AWS V3 study binding differs; V2 artifacts cannot be reused')
