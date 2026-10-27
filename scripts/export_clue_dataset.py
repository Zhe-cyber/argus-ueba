"""Stream a bounded official CLUE ZIP prefix into a separate offline feature dataset."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.clue_features import FEATURES, PROFILE, Window, instant

MAX_COMPRESSED = 32 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024
MAX_EVENTS = 2_000_000


class Prefix:
    def __init__(self, path):
        self.path = Path(path)
        if not 30 <= self.path.stat().st_size <= MAX_COMPRESSED:
            raise ValueError('Prefix must be at most 32 MiB')
        self.expanded_bytes = self.records = 0
        self.stop_reason = 'prefix_end'
        self.backward_time_events = self.day_reversal_events = 0
        self.max_backward_seconds = 0.0
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def events(self):
        with self.path.open('rb') as source:
            header = struct.unpack('<4s5H3I2H', source.read(30))
            name = source.read(header[-2]).decode('utf-8')
            source.read(header[-1])
            if header[0] != b'PK\x03\x04' or header[2] & 1 or header[3] != 8 or name != 'clue.json':
                raise ValueError('Expected the official unencrypted clue.json first member')
            decoder, buffer = zlib.decompressobj(-15), b''
            previous_id, previous_time = 0, None
            while block := source.read(65536):
                pending = block
                while pending:
                    capacity = min(262144, MAX_EXPANDED - self.expanded_bytes)
                    if capacity <= 0:
                        self.stop_reason = 'expanded_limit'
                        return
                    data = decoder.decompress(pending, capacity)
                    pending = decoder.unconsumed_tail
                    self.expanded_bytes += len(data)
                    buffer += data
                    lines = buffer.split(b'\n')
                    buffer = lines.pop()
                    for line in lines:
                        if len(line) > 262144:
                            raise ValueError('Oversized JSON line')
                        row = json.loads(line)
                        if (not isinstance(row, dict) or type(row.get('id')) is not int
                                or row['id'] <= previous_id or not isinstance(row.get('uid'), str)
                                or not row['uid'] or len(row['uid']) > 256
                                or row.get('uidType') not in ('name', 'ipaddress')):
                            raise ValueError('Invalid/duplicate native identity or event ID')
                        timestamp = instant(row['time'])
                        if previous_time is not None and timestamp < previous_time:
                            self.backward_time_events += 1
                            self.day_reversal_events += timestamp.date() < previous_time.date()
                            self.max_backward_seconds = max(self.max_backward_seconds, (previous_time - timestamp).total_seconds())
                        previous_id = row['id']
                        previous_time = max(previous_time, timestamp) if previous_time else timestamp
                        self.records += 1
                        yield row
                        if self.records >= MAX_EVENTS:
                            self.stop_reason = 'event_limit'
                            return
                    if len(buffer) > 262144:
                        raise ValueError('Oversized partial JSON line')
                    if decoder.eof:
                        self.stop_reason = 'first_member_end'
                        if buffer.strip():
                            raise ValueError('Final JSON record lacks a line terminator')
                        return
            # The final incomplete line belongs to the truncated capture boundary.


def export(path, output):
    output = Path(output)
    if output.exists():
        raise ValueError('Use a new export path')
    prefix = Prefix(path)
    windows = defaultdict(dict)
    all_days, action_counts = Counter(), Counter()
    first, last, anonymous, window_count = None, None, 0, 0
    for row in prefix.events():
        current = instant(row['time']).date().isoformat()
        first = min(first, current) if first else current
        last = max(last, current) if last else current
        all_days[current] += 1
        action_counts[row['type']] += 1
        if row['uidType'] != 'name':
            anonymous += 1
            continue
        user = hashlib.sha256(('clue-7119953:' + row['uid']).encode()).hexdigest()
        if user not in windows and len(windows) >= 10_000:
            raise ValueError('Identity population exceeds export bound')
        if current not in windows[user]:
            window_count += 1
            if window_count > 200_000:
                raise ValueError('Identity-day state exceeds export bound')
            windows[user][current] = Window()
        windows[user][current].add(row)
    if not first or len(windows) > 10_000:
        raise ValueError('No usable bounded population')
    rows = []
    for user, by_day in sorted(windows.items()):
        prior, previous_days = set(), 0
        for current, window in sorted(by_day.items()):
            rows.append({'user': user, 'date': current, 'capture_boundary': current in (first, last),
                         'history_days': previous_days, 'coverage': {
                             'path_events': window.path_events, 'missing_required_paths': window.missing_required_paths,
                             'unknown_action_events': window.unknown_actions},
                         'features': window.finish(prior)})
            prior.update(window.actions)
            previous_days += 1
    document = {'schema_version': 1, 'profile': PROFILE, 'features': FEATURES, 'rows': rows,
                'provenance': {'doi': '10.5281/zenodo.7119953', 'license': 'CC-BY-4.0',
                               'attribution': 'Landauer, Skopik, Hoeld, Wurzenberger (AIT), CLUE-LDS (2022)',
                               'source_url': 'https://zenodo.org/records/7119953/files/clue.zip?download=1',
                               'prefix_sha256': prefix.sha256, 'compressed_bytes': prefix.path.stat().st_size,
                               'expanded_bytes': prefix.expanded_bytes, 'stop_reason': prefix.stop_reason,
                               'raw_records': prefix.records, 'excluded_ip_identity_events': anonymous,
                               'backward_time_events': prefix.backward_time_events,
                               'day_reversal_events': prefix.day_reversal_events,
                               'max_backward_seconds': prefix.max_backward_seconds,
                               'events_by_day': dict(sorted(all_days.items())), 'action_counts': dict(action_counts),
                               'feature_code_sha256': hashlib.sha256((ROOT / 'scripts/clue_features.py').read_bytes()).hexdigest(),
                               'export_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                               'first_capture_day': first, 'last_capture_day': last,
                               'source_integrity': 'Partial prefix SHA256 only; full archive MD5/CRC not verified',
                               'coverage_status': 'Interior observed days only; absence of unobserved source gaps is not proven',
                               'normality': 'Publisher-declared normal; not independently verified',
                               'limitations': 'Offline storage benchmark only. No AWS events, model training or live activation.'}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as target:
        json.dump(document, target, indent=2, allow_nan=False)
    return document


def readiness(document, cutoffs):
    if document.get('profile') != PROFILE or document.get('features') != FEATURES:
        raise ValueError('Wrong profile')
    for cutoff in cutoffs:
        if date.fromisoformat(cutoff).isoformat() != cutoff:
            raise ValueError('Use YYYY-MM-DD UTC cutoffs')
    if len(cutoffs) != 5 or any(a >= b for a, b in zip(cutoffs, cutoffs[1:])):
        raise ValueError('Require warmup < fit < validation < calibration < evaluation cutoffs')
    rows = [r for r in document['rows'] if not r['capture_boundary'] and r['date'] <= cutoffs[-1]]
    fit_days, warmup_users = defaultdict(set), set()
    for row in rows:
        if row['date'] <= cutoffs[0]:
            warmup_users.add(row['user'])
        if cutoffs[0] < row['date'] <= cutoffs[1]:
            fit_days[row['user']].add(row['date'])
    # Eligibility is fixed from fitting only, never future validation/test activity.
    eligible = {user for user, days in fit_days.items() if len(days) >= 5 and user in warmup_users}
    partitions = [[] for _ in cutoffs]
    excluded_population_rows = 0
    for row in rows:
        if row['user'] not in eligible:
            excluded_population_rows += 1
            continue
        partition = next(i for i, end in enumerate(cutoffs) if row['date'] <= end)
        partitions[partition].append(row)
    counts = [{'rows': len(p), 'users': len({r['user'] for r in p}),
               'days': len({r['date'] for r in p}),
               'missing_required_paths': sum(r['coverage']['missing_required_paths'] for r in p),
               'unknown_action_events': sum(r['coverage']['unknown_action_events'] for r in p)} for p in partitions]
    blockers = []
    capture_end = document.get('provenance', {}).get('last_capture_day')
    if capture_end and cutoffs[-1] >= capture_end:
        blockers.append('Evaluation cutoff must precede the excluded last capture day')
    if document.get('provenance', {}).get('day_reversal_events', 0):
        blockers.append('Cross-day timestamp reversals require source review')
    if len(eligible) < 6:
        blockers.append('Fewer than six fitting-eligible identities')
    for name, count, minimum in zip(('warmup', 'fit', 'validation', 'calibration', 'evaluation'), counts, (6, 30, 6, 6, 6)):
        if count['rows'] < minimum or count['users'] < 6:
            blockers.append(name + ' has insufficient observed rows/users')
        if count['missing_required_paths'] or count['unknown_action_events']:
            blockers.append(name + ' has unresolved field/action coverage')
    return {'profile': PROFILE, 'cutoffs_utc': cutoffs, 'eligible_fitting_users': len(eligible),
            'partitions': counts, 'excluded_population_rows': excluded_population_rows,
            'excluded_capture_boundary_rows': sum(r['capture_boundary'] for r in document['rows']),
            'operationally_ready': not blockers, 'blockers': blockers,
            'trained': False, 'limitations': 'Operational readiness is not statistical sufficiency, complete coverage or independently verified normality.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--cutoffs', nargs=5, help='Warmup, fit, validation, calibration, evaluation end dates (UTC)')
    args = parser.parse_args()
    try:
        document = export(args.prefix, args.out)
        dataset_sha256 = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()
        summary = {'profile': PROFILE, 'identity_days': len(document['rows']),
                   'capture_days': len(document['provenance']['events_by_day']),
                   'first_day': document['provenance']['first_capture_day'],
                   'last_day': document['provenance']['last_capture_day'], 'trained': False,
                   'dataset_sha256': dataset_sha256}
        if args.cutoffs:
            report = readiness(document, args.cutoffs)
            report['dataset_sha256'] = dataset_sha256
            with Path(args.out).with_suffix('.readiness.json').open('x', encoding='utf-8') as target:
                json.dump(report, target, indent=2)
            summary['readiness'] = report
        print(json.dumps(summary))
    except Exception:
        parser.exit(1, 'CLUE export refused/stopped; check prefix bounds, native chronology, coverage and new output paths. No raw records displayed.\n')
