"""W33 prospective access binding. No ZIP decoding, feature extraction or training.

This receipt authorises only the declared availability/pre-test reader bounds.
It is not a reserved-evaluator release. Downstream readers must verify it and
their own bindings before opening records.
"""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PROFILE = 'clue_ae_v2'
ARCHIVE_SHA = '0c9eadb104acf1da6de738ba9babe957c83cd8602a01fa6d846a6ea4a6611d96'
ARCHIVE_BYTES = 635105552
SOURCES = ['specs/W33-clue-ae-v2.md', 'scripts/clue_v2_access.py',
           'scripts/tests/test_clue_v2_access.py']
POLICY = {
    'warmup': ['2017-08-07', '2017-09-03'],
    'fit': ['2017-09-04', '2017-11-26'],
    'validation': ['2017-11-27', '2017-12-03'],
    'calibration': ['2017-12-04', '2017-12-17'],
    'gap_history_only': ['2017-12-18', '2018-01-14'],
    'reserved': ['2018-01-15', '2018-01-28'],
    'availability_months': ['2017-08', '2017-09', '2017-10', '2017-11', '2017-12', '2018-01'],
    'availability_output': ['monthly_total_event_counts', 'parse_error_total'],
    'split_shifts_allowed': 0,
    'freeze_deadline_myt': '2026-11-15T23:59:00+08:00',
    'test_execution_dates_myt': ['2026-11-16', '2026-11-17'],
    'report_deadline_myt': '2026-11-17T23:59:00+08:00',
    'reserved_access_authorised': False,
    'model_activation_authorised': False,
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def check_day(day, purpose):
    """Pure date barrier; does not authorise archive I/O by itself."""
    if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
        raise ValueError('Canonical UTC date required')
    if purpose == 'pretest':
        if not POLICY['warmup'][0] <= day <= POLICY['gap_history_only'][1]:
            raise ValueError('Date outside pre-test access; reserved release required')
    elif purpose == 'validation_report':
        if not POLICY['validation'][0] <= day <= POLICY['validation'][1]:
            raise ValueError('Validation-only report date required')
    elif purpose == 'reserved':
        raise ValueError('W33 access plan never authorises reserved evaluation')
    else:
        raise ValueError('Unknown access purpose')
    return day


def sources():
    return {name: sha(ROOT / name) for name in SOURCES}


def archive_binding(archive, verification):
    archive, verification = Path(archive).resolve(), Path(verification).resolve()
    evidence = json.loads(verification.read_bytes())
    if (evidence.get('sha256') != ARCHIVE_SHA or evidence.get('download_bytes') != ARCHIVE_BYTES
            or archive.stat().st_size != ARCHIVE_BYTES or sha(archive) != ARCHIVE_SHA):
        raise ValueError('Existing verified archive binding differs')
    if evidence.get('members') != [{'name': 'clue.json', 'bytes': 14862210499, 'compressed_bytes': 635105368}]:
        raise ValueError('Existing archive member manifest differs')
    # Hash raw compressed bytes only; no archive member or event is decoded.
    return {'archive_path': str(archive), 'archive_bytes': ARCHIVE_BYTES,
            'archive_sha256': ARCHIVE_SHA, 'verification_path': str(verification),
            'verification_sha256': sha(verification)}


def create_plan(archive, verification, output):
    output = Path(output).resolve()
    if output.exists() or not output.is_relative_to((ROOT / 'data').resolve()):
        raise ValueError('New private receipt below checkout data required')
    document = {'schema': 'w33_access_plan_v1', 'profile': PROFILE,
                'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'policy': POLICY, 'source_sha256': sources(),
                'archive': archive_binding(archive, verification),
                'record_access_performed': False, 'status': 'access_plan_not_test_release'}
    document['receipt_sha256'] = hashlib.sha256(canonical(document)).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(canonical(document) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    return document


def verify_plan(path):
    document = json.loads(Path(path).read_bytes())
    if not isinstance(document, dict):
        raise ValueError('Invalid access receipt')
    bound = dict(document)
    receipt_sha = bound.pop('receipt_sha256', None)
    if (receipt_sha != hashlib.sha256(canonical(bound)).hexdigest()
            or document.get('schema') != 'w33_access_plan_v1' or document.get('profile') != PROFILE
            or document.get('policy') != POLICY or document.get('source_sha256') != sources()
            or document.get('status') != 'access_plan_not_test_release'
            or document.get('record_access_performed') is not False):
        raise ValueError('W33 access binding changed')
    binding = document['archive']
    if archive_binding(binding['archive_path'], binding['verification_path']) != binding:
        raise ValueError('Archive binding changed')
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    create = sub.add_parser('bind')
    create.add_argument('--archive', required=True)
    create.add_argument('--verification', required=True)
    create.add_argument('--out', required=True)
    verify = sub.add_parser('verify')
    verify.add_argument('--receipt', required=True)
    args = parser.parse_args()
    try:
        result = (create_plan(args.archive, args.verification, args.out) if args.mode == 'bind'
                  else verify_plan(args.receipt))
        print(json.dumps({'status': result['status'], 'receipt_sha256': result['receipt_sha256'],
                          'reserved_access_authorised': False, 'records_decoded': 0}))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print('W33 binding failed; no record reader was invoked.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
