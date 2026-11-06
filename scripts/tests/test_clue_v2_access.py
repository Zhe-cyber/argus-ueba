"""W33 access tests use fixture bytes only, never the real archive."""
import hashlib
import json

import pytest

from scripts import clue_v2_access as access


@pytest.mark.parametrize('day,purpose', [
    ('2017-08-07', 'pretest'), ('2018-01-14', 'pretest'),
    ('2017-11-27', 'validation_report'), ('2017-12-03', 'validation_report'),
])
def test_permitted_date_bounds(day, purpose):
    assert access.check_day(day, purpose) == day


@pytest.mark.parametrize('day,purpose', [
    ('2018-01-15', 'pretest'), ('2018-01-28', 'pretest'), ('2017-08-06', 'pretest'),
    ('2017-11-26', 'validation_report'), ('2017-12-04', 'validation_report'),
    ('2018-01-15', 'reserved'), ('2017-11-27', 'anything'),
])
def test_no_reserved_or_other_partition_report_access(day, purpose):
    with pytest.raises(ValueError):
        access.check_day(day, purpose)


@pytest.fixture
def bound(tmp_path, monkeypatch):
    monkeypatch.setattr(access, 'ROOT', tmp_path)
    for name in access.SOURCES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('synthetic bound source\n')
    archive = tmp_path / 'fixture.zip'
    archive.write_bytes(b'not a zip: binding must never decode this')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setattr(access, 'ARCHIVE_SHA', digest)
    monkeypatch.setattr(access, 'ARCHIVE_BYTES', archive.stat().st_size)
    verification = tmp_path / 'verification.json'
    verification.write_text(json.dumps({'sha256': digest, 'download_bytes': archive.stat().st_size,
        'members': [{'name': 'clue.json', 'bytes': 14862210499, 'compressed_bytes': 635105368}]}))
    return archive, verification, tmp_path / 'data/access-plan.json'


def test_binding_and_verification_never_require_zip_decoding(bound):
    archive, verification, output = bound
    document = access.create_plan(archive, verification, output)
    assert access.verify_plan(output) == document
    assert document['record_access_performed'] is False
    assert document['policy']['reserved_access_authorised'] is False
    assert document['policy']['freeze_deadline_myt'] == '2026-11-15T23:59:00+08:00'
    assert document['policy']['split_shifts_allowed'] == 0
    with pytest.raises(ValueError):
        access.create_plan(archive, verification, output)


@pytest.mark.parametrize('change', ['source', 'archive', 'manifest', 'receipt', 'policy'])
def test_mutated_bindings_fail_closed(bound, change):
    archive, verification, output = bound
    access.create_plan(archive, verification, output)
    if change == 'source':
        (access.ROOT / access.SOURCES[0]).write_text('changed')
    elif change == 'archive':
        archive.write_bytes(b'changed')
    elif change == 'manifest':
        verification.write_text('{}')
    else:
        doc = json.loads(output.read_bytes())
        if change == 'policy':
            doc['policy']['reserved_access_authorised'] = True
            body = {k: v for k, v in doc.items() if k != 'receipt_sha256'}
            doc['receipt_sha256'] = hashlib.sha256(access.canonical(body)).hexdigest()
        else:
            doc['status'] = 'released'
        output.write_text(json.dumps(doc))
    with pytest.raises((ValueError, KeyError)):
        access.verify_plan(output)


def test_output_outside_private_data_refused_before_archive_access(bound, monkeypatch):
    archive, verification, _ = bound
    monkeypatch.setattr(access, 'archive_binding', lambda *_: pytest.fail('Archive touched'))
    with pytest.raises(ValueError):
        access.create_plan(archive, verification, access.ROOT / 'public.json')
