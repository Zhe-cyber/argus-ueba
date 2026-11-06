"""Bounded CLUE ZIP streaming, currently restricted to inspected development dates."""
from datetime import date
import json
from pathlib import Path
from zipfile import ZipFile
from scripts.shared_core_features import instant

MAX_COMPRESSED = 700 * 1024 * 1024
MAX_EXPANDED = 16 * 1024 * 1024 * 1024
MAX_LINE = 256 * 1024
MAX_EVENTS = 60_000_000
DEVELOPMENT_END_EXCLUSIVE = '2017-08-10'


def development_events(path, end_exclusive=DEVELOPMENT_END_EXCLUSIVE):
    if date.fromisoformat(end_exclusive).isoformat() != end_exclusive or end_exclusive > DEVELOPMENT_END_EXCLUSIVE:
        raise ValueError('Reserved dates require a separately released evaluator; development access only')
    path = Path(path)
    if not 30 <= path.stat().st_size <= MAX_COMPRESSED:
        raise ValueError('Archive size outside bounds')
    with ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != 'clue.json' or members[0].file_size > MAX_EXPANDED or members[0].flag_bits & 1:
            raise ValueError('Expected one bounded unencrypted clue.json member')
        expanded = count = last_id = 0
        last_day = None
        with archive.open(members[0]) as source:
            while line := source.readline(MAX_LINE + 1):
                expanded += len(line); count += 1
                if len(line) > MAX_LINE or expanded > MAX_EXPANDED or count > MAX_EVENTS:
                    raise ValueError('Streaming safety bound exceeded')
                if not line.endswith(b'\n'):
                    raise ValueError('Incomplete native JSON line')
                row = json.loads(line)
                if not isinstance(row, dict) or type(row.get('id')) is not int or row['id'] <= last_id:
                    raise ValueError('Native ID order/conflict')
                day = instant(row['time']).date().isoformat()
                if last_day is not None and day < last_day:
                    raise ValueError('Cross-day reversal needs separate review')
                last_id, last_day = row['id'], day
                if day >= end_exclusive:
                    return
                yield row
