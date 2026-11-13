"""W33 bounded CLUE reader: timestamp-only availability and pre-test streaming.

Inert on import. Every archive read requires a verified reader-access receipt,
which itself re-verifies the W33 access foundation. Reserved rows are never
yielded: the first out-of-range row is JSON-parsed inside `_timestamp_day`, but
only its timestamp is consumed to close the last permitted day, then reading stops.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import clue_v2_access as access
from scripts.shared_core_features import instant
from scripts.shared_core_reader import MAX_COMPRESSED, MAX_EXPANDED, MAX_LINE, MAX_EVENTS

SCHEMA = 'w33_reader_access_v1'
STATUS = 'reader_bound_not_test_release'
MONTHS = tuple(access.POLICY['availability_months'])
AVAILABILITY_END_EXCLUSIVE = '2018-02-01'  # its first row closes January; only its date is decoded
PRETEST_START = access.POLICY['warmup'][0]
PRETEST_END = access.POLICY['gap_history_only'][1]
READER_SOURCES = ['specs/W33-clue-ae-v2.md', 'scripts/clue_v2_access.py', 'scripts/tests/test_clue_v2_access.py',
                  'scripts/clue_v2_reader.py', 'scripts/tests/test_clue_v2_reader.py']


def dependency_closure(names, root=None):
    """Bound sources plus every transitively imported `scripts` module, by static import analysis."""
    root = Path(root or ROOT)
    pending, seen = list(names), set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        if not name.endswith('.py'):
            continue
        tree = ast.parse((root / name).read_bytes())
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                if node.module == 'scripts':
                    modules = ['scripts.' + alias.name for alias in node.names]
                elif node.module.startswith('scripts.'):
                    modules = [node.module]
            elif isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names if alias.name.startswith('scripts.')]
            for module in modules:
                path = module.replace('.', '/') + '.py'
                if (root / path).is_file():
                    pending.append(path)
    return sorted(seen)


def source_hashes(names, root=None):
    root = Path(root or ROOT)
    return {name: access.sha(root / name) for name in dependency_closure(names, root)}


def _receipt_digest(document):
    body = {key: value for key, value in document.items() if key != 'receipt_sha256'}
    return hashlib.sha256(access.canonical(body)).hexdigest()


def bounds():
    return {'max_compressed_bytes': MAX_COMPRESSED, 'max_expanded_bytes': MAX_EXPANDED,
            'max_line_bytes': MAX_LINE, 'max_events': MAX_EVENTS, 'member': 'clue.json',
            'availability_months': list(MONTHS), 'availability_end_exclusive': AVAILABILITY_END_EXCLUSIVE,
            'availability_output': list(access.POLICY['availability_output']),
            'pretest_dates': [PRETEST_START, PRETEST_END], 'reserved_rows_yielded': False}


def bind_reader(foundation, output):
    """Exclusive private receipt; verifies the foundation (archive rehash) but decodes no records."""
    output = Path(output).resolve()
    if output.exists() or not output.is_relative_to((ROOT / 'data').resolve()):
        raise ValueError('New private receipt below checkout data required')
    plan = access.verify_plan(foundation)
    document = {'schema': SCHEMA, 'profile': access.PROFILE,
                'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'foundation': {'path': str(Path(foundation).resolve()), 'file_sha256': access.sha(foundation),
                               'receipt_sha256': plan['receipt_sha256']},
                'source_sha256': source_hashes(READER_SOURCES), 'bounds': bounds(),
                'record_access_performed': False, 'status': STATUS}
    document['receipt_sha256'] = _receipt_digest(document)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(access.canonical(document) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    return document


def verify_reader(path):
    """Fail closed on any changed reader source, bound, foundation or archive. Returns the archive path."""
    document = json.loads(Path(path).read_bytes())
    if (not isinstance(document, dict) or document.get('receipt_sha256') != _receipt_digest(document)
            or document.get('schema') != SCHEMA or document.get('profile') != access.PROFILE
            or document.get('status') != STATUS or document.get('record_access_performed') is not False
            or document.get('bounds') != bounds()
            or document.get('source_sha256') != source_hashes(READER_SOURCES)):
        raise ValueError('W33 reader binding changed')
    foundation = document['foundation']
    if access.sha(foundation['path']) != foundation['file_sha256']:
        raise ValueError('Foundation receipt file changed')
    plan = access.verify_plan(foundation['path'])
    if plan['receipt_sha256'] != foundation['receipt_sha256']:
        raise ValueError('Foundation receipt binding changed')
    return document, plan['archive']['archive_path']


def _lines(archive_path):
    """Complete raw lines under fixed bounds; callers decide what may be decoded."""
    path = Path(archive_path)
    if not 30 <= path.stat().st_size <= MAX_COMPRESSED:
        raise ValueError('Archive size outside bounds')
    with ZipFile(path) as archive:
        members = archive.infolist()
        if (len(members) != 1 or members[0].filename != 'clue.json' or members[0].file_size > MAX_EXPANDED
                or members[0].flag_bits & 1 or members[0].compress_type not in (ZIP_DEFLATED, ZIP_STORED)):
            raise ValueError('Expected one bounded unencrypted clue.json member')
        expanded = count = 0
        with archive.open(members[0]) as source:
            while line := source.readline(MAX_LINE + 1):
                expanded += len(line); count += 1
                if len(line) > MAX_LINE or expanded > MAX_EXPANDED or count > MAX_EVENTS:
                    raise ValueError('Streaming safety bound exceeded')
                if not line.endswith(b'\n'):
                    raise ValueError('Incomplete native JSON line')
                yield line


def _timestamp_day(line):
    """JSON-parse a line, consume only its time field, and return only its UTC date."""
    row = json.loads(line)
    if not isinstance(row, dict):
        raise ValueError('Native JSON object required')
    return instant(row.get('time')).date().isoformat()


def availability(archive_path):
    """Monthly event totals for the six W33 months plus one parse/error total. No other data output."""
    counts, errors, previous = dict.fromkeys(MONTHS, 0), 0, None
    lines = _lines(archive_path)
    try:
        for line in lines:
            try:
                day = _timestamp_day(line)
            except (ValueError, TypeError, KeyError):
                errors += 1
                continue
            if previous is not None and day < previous:
                raise ValueError('Cross-day reversal; unsupported archive shape')
            previous = day
            if day >= AVAILABILITY_END_EXCLUSIVE:
                return {'schema': 'w33_availability_v1', 'monthly_total_event_counts': counts,
                        'parse_error_total': errors}
            if day[:7] in counts:
                counts[day[:7]] += 1
    finally:
        lines.close()
    raise ValueError('Archive ended before January 2018 was closed by a later row')


def pretest_events(archive_path, end=PRETEST_END):
    """Yield native rows dated PRETEST_START..end inclusive. Malformed rows fail closed."""
    access.check_day(end, 'pretest')
    previous_day, previous_id = None, 0
    lines = _lines(archive_path)
    try:
        for line in lines:
            day = _timestamp_day(line)
            if previous_day is not None and day < previous_day:
                raise ValueError('Cross-day reversal; unsupported archive shape')
            previous_day = day
            if day > end:
                return  # Boundary row was parsed, but only its date consumed; later lines are never read.
            row = json.loads(line)
            if type(row.get('id')) is not int or row['id'] <= previous_id:
                raise ValueError('Native ID order/conflict')
            previous_id = row['id']
            if day < PRETEST_START:
                continue
            access.check_day(day, 'pretest')
            yield row
    finally:
        lines.close()
    raise ValueError('No post-window boundary row: the final permitted day may be partial')


def open_pretest(receipt, end=PRETEST_END):
    _, archive = verify_reader(receipt)
    return pretest_events(archive, end)


def verify_availability(path, reader_document):
    """Require the declared coverage check before actual export, without shifting dates."""
    raw = Path(path).read_bytes()
    document = json.loads(raw)
    if (not isinstance(document, dict)
            or set(document) != {'schema', 'monthly_total_event_counts', 'parse_error_total', 'reader_receipt_sha256'}
            or document['schema'] != 'w33_availability_v1'
            or document['reader_receipt_sha256'] != reader_document['receipt_sha256']
            or type(document['parse_error_total']) is not int or document['parse_error_total'] < 0):
        raise ValueError('Availability proof binding differs')
    counts = document['monthly_total_event_counts']
    if (not isinstance(counts, dict) or set(counts) != set(MONTHS)
            or any(type(count) is not int or count <= 0 for count in counts.values())):
        raise ValueError('Required monthly coverage absent; W33 no-go, no date shifts')
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    bind = sub.add_parser('bind')
    bind.add_argument('--foundation', required=True)
    bind.add_argument('--out', required=True)
    verify = sub.add_parser('verify')
    verify.add_argument('--receipt', required=True)
    check = sub.add_parser('availability')
    check.add_argument('--receipt', required=True)
    check.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        if args.mode == 'bind':
            result = bind_reader(args.foundation, args.out)
            print(json.dumps({'status': result['status'], 'receipt_sha256': result['receipt_sha256'], 'records_decoded': 0}))
        elif args.mode == 'verify':
            result, _ = verify_reader(args.receipt)
            print(json.dumps({'status': result['status'], 'receipt_sha256': result['receipt_sha256']}))
        else:
            out = Path(args.out).resolve()
            if out.exists() or not out.is_relative_to((ROOT / 'data').resolve()):
                raise ValueError('New private output below checkout data required')
            document, archive = verify_reader(args.receipt)
            result = availability(archive)
            result['reader_receipt_sha256'] = document['receipt_sha256']
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open('xb') as stream:
                stream.write(access.canonical(result) + b'\n')
            print(json.dumps(result))
            verify_availability(out, document)
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print('W33 reader step failed closed; no reserved rows were yielded.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
