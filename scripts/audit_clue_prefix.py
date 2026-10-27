"""Bounded structural audit of an official CLUE-LDS ZIP prefix, not a training export."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import zlib


def inspect(path):
    path = Path(path)
    if not 30 <= path.stat().st_size <= 8 * 1024 * 1024:
        raise ValueError('Expected a ZIP prefix of at most 8 MiB')
    payload = path.read_bytes()
    header = struct.unpack('<4s5H3I2H', payload[:30])
    signature, flags, method = header[0], header[2], header[3]
    name_length, extra_length = header[-2:]
    name = payload[30:30 + name_length].decode('utf-8')
    if signature != b'PK\x03\x04' or flags & 1 or method != 8 or name != 'clue.json':
        raise ValueError('Unexpected CLUE first member')
    # Never extract a path; cap expanded data even if ZIP64 metadata advertises more.
    data = zlib.decompressobj(-15).decompress(payload[30 + name_length + extra_length:], 64 * 1024 * 1024)
    lines = data.splitlines()
    if not data.endswith(b'\n'):
        lines = lines[:-1]  # Ignore the final incomplete JSON line.
    dates, actions, kinds, named_days = Counter(), Counter(), Counter(), Counter()
    ids, named_users, fields = set(), set(), Counter()
    first, last, count = None, None, 0
    for line in lines[:100_000]:
        if len(line) > 256 * 1024:
            raise ValueError('Oversized JSON line')
        event = json.loads(line)
        if not isinstance(event, dict) or not all(k in event for k in ('id', 'time', 'uid', 'uidType', 'type')):
            raise ValueError('Unexpected CLUE event schema')
        instant = datetime.fromisoformat(event['time'].replace('Z', '+00:00'))
        if instant.tzinfo is None:
            raise ValueError('Timestamp lacks timezone')
        timestamp = instant.astimezone(timezone.utc).isoformat()
        if last is not None and timestamp < last:
            raise ValueError('Sample is not chronologically ordered')
        first = first or timestamp
        last = timestamp
        ids.add(event['id'])
        dates[timestamp[:10]] += 1
        actions[event['type']] += 1
        kinds[event['uidType']] += 1
        fields.update(event.keys())
        if event['uidType'] == 'name':
            named_users.add(event['uid'])
            named_days[(event['uid'], timestamp[:10])] += 1
        count += 1
    if not count:
        raise ValueError('No complete sample events')
    return {'schema_version': 1, 'dataset': 'CLUE-LDS', 'doi': '10.5281/zenodo.7119953',
            'source_url': 'https://zenodo.org/records/7119953/files/clue.zip?download=1',
            'official_metadata_license': 'CC-BY-4.0', 'compressed_prefix_bytes': len(payload),
            'prefix_sha256': hashlib.sha256(payload).hexdigest(), 'expanded_prefix_bytes': len(data),
            'sample_event_limit': 100_000, 'sample_records': count, 'unique_sample_ids': len(ids),
            'first_sample_utc': first, 'last_sample_utc': last, 'events_by_day': dict(sorted(dates.items())),
            'named_users': len(named_users), 'named_identity_days': len(named_days),
            'uid_types': dict(kinds), 'action_counts': dict(actions), 'field_occurrences': dict(fields),
            'training_ready': False,
            'limitations': ['Partial chronological prefix, not a representative or complete dataset audit.',
                            'Full-archive published MD5 cannot verify a partial download; only prefix SHA256 is recorded.',
                            'Named pseudonyms are not verified cross-provider persons; ipaddress identities are excluded from named counts.',
                            'Native Nextcloud/hBOX events need a source-specific feature/adapter review; never relabel as AWS.',
                            'No features exported, model trained, or events sent to live ingestion.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        report = inspect(args.prefix)
        with Path(args.out).open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2)
        print(json.dumps({k: report[k] for k in ('sample_records', 'named_users', 'named_identity_days', 'first_sample_utc', 'last_sample_utc', 'training_ready')}))
    except Exception:
        parser.exit(1, 'CLUE inspection stopped. Check bounded official ZIP prefix and a new report path. No raw events displayed.\n')
