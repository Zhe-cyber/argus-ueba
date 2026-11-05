"""W33 reader tests on synthetic ZIP fixtures only, never the real archive."""
import hashlib
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from scripts import clue_v2_access as access, clue_v2_reader as reader

SECRET = 'RESERVED-SENTINEL-7f3a'
_ids = iter(range(1, 10**9))


def row(day, hour=10, **extra):
    return {'id': next(_ids), 'uid': 'u1', 'uidType': 'name', 'type': 'file_accessed',
            'time': f'{day}T{hour:02d}:00:00Z', 'params': {'path': '/ns/f'}, **extra}


def reserved(day='2018-01-15'):
    return row(day, uid=SECRET, type=SECRET, params={'path': '/' + SECRET})


def archive(tmp_path, items, name='archive.zip', member='clue.json'):
    payload = b''.join(item if isinstance(item, bytes) else json.dumps(item).encode() + b'\n' for item in items)
    path = tmp_path / name
    with ZipFile(path, 'w', ZIP_DEFLATED) as zipped:
        zipped.writestr(member, payload)
    return path


def test_availability_outputs_only_monthly_totals_and_parse_errors(tmp_path):
    path = archive(tmp_path, [row('2017-07-30'), row('2017-08-07'), row('2017-08-31'), b'{not json\n',
                              row('2017-09-01'), reserved('2018-01-15'), reserved('2018-01-31'),
                              row('2018-02-01'), b'{"incomplete final line'])
    result = reader.availability(path)
    assert set(result) == {'schema', 'monthly_total_event_counts', 'parse_error_total'}
    assert result['monthly_total_event_counts'] == {'2017-08': 2, '2017-09': 1, '2017-10': 0,
                                                    '2017-11': 0, '2017-12': 0, '2018-01': 2}
    assert result['parse_error_total'] == 1
    assert SECRET not in json.dumps(result)  # reading stopped at 1 Feb; the truncated line was never read


def test_availability_requires_a_row_closing_january(tmp_path):
    with pytest.raises(ValueError, match='January'):
        reader.availability(archive(tmp_path, [row('2017-08-07'), reserved('2018-01-20')]))


def test_availability_rejects_cross_day_reversal(tmp_path):
    with pytest.raises(ValueError, match='reversal'):
        reader.availability(archive(tmp_path, [row('2017-09-02'), row('2017-09-01'), row('2018-02-01')]))


def test_pretest_boundary_only_consumes_date_and_never_yields_reserved_rows(tmp_path, monkeypatch):
    path = archive(tmp_path, [row('2017-08-06'), row('2017-08-07'), row('2017-12-01'), row('2018-01-14', hour=23),
                              reserved(), b'{"never read'])
    seen_by_date_probe, full_decodes = [], []
    probe, loads = reader._timestamp_day, json.loads

    def spy_probe(line):
        seen_by_date_probe.append(line)
        return probe(line)

    class SpyJson:
        @staticmethod
        def loads(data):
            full_decodes.append(data)
            return loads(data)

    monkeypatch.setattr(reader, '_timestamp_day', spy_probe)
    monkeypatch.setattr(reader, 'json', SpyJson)
    rows = list(reader.pretest_events(path))
    assert [r['time'][:10] for r in rows] == ['2017-08-07', '2017-12-01', '2018-01-14']
    assert SECRET not in json.dumps(rows)
    secret_lines = [line for line in full_decodes if SECRET.encode() in line]
    assert len(secret_lines) == 1 and secret_lines[0] in seen_by_date_probe  # date probe only


@pytest.mark.parametrize('end,expected', [('2017-11-26', ['2017-08-07', '2017-11-26']), ('2018-01-14', None)])
def test_pretest_end_stops_at_first_later_row(tmp_path, end, expected):
    items = [row('2017-08-07'), row('2017-11-26'), row('2017-11-27'), reserved()]
    days = [r['time'][:10] for r in reader.pretest_events(archive(tmp_path, items), end)]
    assert days == (expected or ['2017-08-07', '2017-11-26', '2017-11-27'])


@pytest.mark.parametrize('end', ['2018-01-15', '2018-01-28', '2017-08-06', 'not-a-date'])
def test_pretest_end_cannot_reach_reserved_or_outside_dates(tmp_path, end):
    with pytest.raises(ValueError):
        list(reader.pretest_events(archive(tmp_path, [row('2017-08-07'), reserved()]), end))


def test_pretest_without_boundary_row_fails_closed(tmp_path):
    with pytest.raises(ValueError, match='boundary'):
        list(reader.pretest_events(archive(tmp_path, [row('2017-08-07'), row('2018-01-14')])))


@pytest.mark.parametrize('items', [
    [row('2017-09-02'), row('2017-09-01'), reserved()],
    [{**row('2017-09-01'), 'id': 50}, {**row('2017-09-01'), 'id': 50}, reserved()],
    [row('2017-09-01'), b'{"bad json\n', reserved()],
])
def test_pretest_rejects_reversal_id_conflict_and_malformed_rows(tmp_path, items):
    with pytest.raises(ValueError):
        list(reader.pretest_events(archive(tmp_path, items)))


def test_archive_shape_and_stream_bounds(tmp_path, monkeypatch):
    good = [row('2017-08-07'), reserved()]
    with pytest.raises(ValueError, match='member'):
        list(reader.pretest_events(archive(tmp_path, good, 'other.zip', member='other.json')))
    two = tmp_path / 'two.zip'
    with ZipFile(two, 'w') as zipped:
        zipped.writestr('clue.json', b'{}\n'); zipped.writestr('extra.json', b'{}\n')
    with pytest.raises(ValueError, match='member'):
        list(reader.availability(two))
    with pytest.raises(ValueError, match='Incomplete'):
        list(reader.pretest_events(archive(tmp_path, [row('2017-08-07'), b'{"partial'], 'partial.zip')))
    path = archive(tmp_path, good, 'bounded.zip')
    for name, value in [('MAX_LINE', 32), ('MAX_EVENTS', 1), ('MAX_EXPANDED', 64), ('MAX_COMPRESSED', 31)]:
        with monkeypatch.context() as patch:
            patch.setattr(reader, name, value)
            with pytest.raises(ValueError):
                list(reader.pretest_events(path))


def test_dependency_closure_covers_transitive_project_imports():
    closure = reader.dependency_closure(reader.READER_SOURCES)
    for required in ['scripts/clue_v2_reader.py', 'scripts/clue_v2_access.py', 'scripts/shared_core_features.py',
                     'scripts/shared_core_reader.py', 'scripts/clue_features.py', 'specs/W33-clue-ae-v2.md']:
        assert required in closure


@pytest.fixture
def bound(tmp_path, monkeypatch):
    monkeypatch.setattr(access, 'ROOT', tmp_path)
    monkeypatch.setattr(reader, 'ROOT', tmp_path)
    for name in set(access.SOURCES + reader.READER_SOURCES):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('# synthetic bound source\n')
    zipped = archive(tmp_path, [row('2017-08-07'), reserved()])
    digest = hashlib.sha256(zipped.read_bytes()).hexdigest()
    monkeypatch.setattr(access, 'ARCHIVE_SHA', digest)
    monkeypatch.setattr(access, 'ARCHIVE_BYTES', zipped.stat().st_size)
    verification = tmp_path / 'verification.json'
    verification.write_text(json.dumps({'sha256': digest, 'download_bytes': zipped.stat().st_size,
        'members': [{'name': 'clue.json', 'bytes': 14862210499, 'compressed_bytes': 635105368}]}))
    foundation = tmp_path / 'data/access-plan.json'
    access.create_plan(zipped, verification, foundation)
    return zipped, foundation, tmp_path / 'data/reader-receipt.json'


def test_reader_receipt_binds_sources_bounds_and_foundation(bound):
    zipped, foundation, output = bound
    document = reader.bind_reader(foundation, output)
    verified, archive_path = reader.verify_reader(output)
    assert verified == document and archive_path == str(zipped.resolve())
    assert document['record_access_performed'] is False and document['bounds']['reserved_rows_yielded'] is False
    assert set(document['source_sha256']) >= set(reader.READER_SOURCES)
    with pytest.raises(ValueError):
        reader.bind_reader(foundation, output)
    with pytest.raises(ValueError):
        reader.bind_reader(foundation, reader.ROOT / 'outside.json')


@pytest.mark.parametrize('change', ['reader_source', 'foundation', 'bounds', 'receipt', 'archive'])
def test_reader_receipt_mutation_fails_closed(bound, change, monkeypatch):
    zipped, foundation, output = bound
    reader.bind_reader(foundation, output)
    if change == 'reader_source':
        (reader.ROOT / 'scripts/clue_v2_reader.py').write_text('changed\n')
    elif change == 'foundation':
        foundation.write_bytes(foundation.read_bytes() + b' ')
    elif change == 'bounds':
        monkeypatch.setattr(reader, 'MAX_LINE', reader.MAX_LINE - 1)
    elif change == 'receipt':
        doc = json.loads(output.read_bytes()); doc['status'] = 'released'
        output.write_text(json.dumps(doc))
    else:
        zipped.write_bytes(zipped.read_bytes() + b'x')
    with pytest.raises((ValueError, KeyError)):
        reader.verify_reader(output)


def test_open_pretest_verifies_before_any_read(monkeypatch):
    monkeypatch.setattr(reader, 'verify_reader', lambda _: (_ for _ in ()).throw(ValueError('unbound')))
    monkeypatch.setattr(reader, '_lines', lambda *_: pytest.fail('Archive read before verification'))
    with pytest.raises(ValueError, match='unbound'):
        reader.open_pretest('receipt.json')


@pytest.mark.parametrize('change', ['none', 'empty_month', 'wrong_reader', 'extra_data', 'bool_count', 'bad_errors'])
def test_availability_proof_is_required_and_bound(tmp_path, change):
    import hashlib
    document = {'schema': 'w33_availability_v1', 'monthly_total_event_counts': dict.fromkeys(reader.MONTHS, 10),
                'parse_error_total': 0, 'reader_receipt_sha256': 'reader-proof'}
    if change == 'empty_month':document['monthly_total_event_counts'][reader.MONTHS[0]] = 0
    elif change == 'wrong_reader':document['reader_receipt_sha256'] = 'other-reader'
    elif change == 'extra_data':document['account_ids'] = ['not-allowed']
    elif change == 'bool_count':document['monthly_total_event_counts'][reader.MONTHS[0]] = True
    elif change == 'bad_errors':document['parse_error_total'] = -1
    path = tmp_path/'availability.json';path.write_text(json.dumps(document))
    if change == 'none':
        assert reader.verify_availability(path, {'receipt_sha256': 'reader-proof'}) == hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        with pytest.raises(ValueError):reader.verify_availability(path, {'receipt_sha256': 'reader-proof'})
