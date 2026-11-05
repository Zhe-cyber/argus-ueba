"""W33 export orchestration tests with an injected synthetic pre-test stream."""
from datetime import date, timedelta
import hashlib
import json

import pytest

from scripts import clue_v2_reader as reader, export_clue_v2 as export
from scripts.shared_core_features import project_clue

_ids = iter(range(1, 10**9))


def native(uid, day, path='/ns/f'):
    return {'id': next(_ids), 'uid': uid, 'uidType': 'name', 'type': 'file_accessed',
            'time': f'{day}T10:00:00Z', 'params': {'path': path}}


def days(first, count):
    return [(date.fromisoformat(first) + timedelta(i)).isoformat() for i in range(count)]


def account(uid):
    return project_clue(native(uid, '2017-09-04')).account


@pytest.fixture
def rows():
    data = [native('alice', '2017-08-07')]
    data += [native('alice', d) for d in days('2017-09-04', 6)] + [native('bob', d) for d in days('2017-09-04', 5)]
    data += [native('carol', d) for d in days('2017-09-04', 4)]
    data += [native('dave', '2017-11-27'), native('alice', '2017-11-27'), native('bob', '2017-12-04'),
             native('alice', '2017-12-20')]
    return sorted(data, key=lambda r: (r['time'], r['id']))


def stream_of(data, calls):
    def stream(end):
        calls.append(end)
        return (r for r in data if r['time'][:10] <= end)
    return stream


def test_export_fixes_fit_only_cohort_and_emits_only_row_partitions(tmp_path, monkeypatch, rows):
    monkeypatch.setattr(export, 'ROOT', tmp_path)
    calls = []
    manifest = export.export(tmp_path / 'data/w33-export', stream_of(rows, calls), {'synthetic': True})
    assert calls == ['2017-11-26', '2018-01-14']  # pass 1 never sees validation or later
    cohort = json.loads((tmp_path / 'data/w33-export/cohort.json').read_bytes())
    assert manifest['cohort_file_sha256'] == hashlib.sha256((tmp_path / 'data/w33-export/cohort.json').read_bytes()).hexdigest()
    assert set(cohort['selected']) == {account('alice'), account('bob')}  # carol <5 fit days, dave not in fit
    assert (cohort['candidates'], cohort['eligible'], cohort['below_min_active_fit_days']) == (3, 2, 1)
    out = {part: [json.loads(line) for line in (tmp_path / f'data/w33-export/rows-{part}.jsonl').read_bytes().splitlines()]
           for part in export.ROW_PARTITIONS}
    assert {r['day'] for r in out['validation']} == {'2017-11-27'} and len(out['validation']) == 1
    assert out['validation'][0]['prior_usable_days'] == 7 and out['validation'][0]['status'] == 'eligible'
    assert all(r['partition'] == part for part, items in out.items() for r in items)
    assert not any(r['day'] < '2017-09-04' or r['day'] > '2017-12-17' for items in out.values() for r in items)
    assert manifest['coverage']['gap_history_only']['observed_days'] == 1
    assert manifest['coverage']['warmup']['observed_days'] == 1
    for part in export.ROW_PARTITIONS:
        data = (tmp_path / f'data/w33-export/rows-{part}.jsonl').read_bytes()
        assert manifest['partition_rows_sha256'][part] == hashlib.sha256(data).hexdigest()
    assert manifest['reserved_access'] is False and manifest['training_performed'] is False
    assert manifest['engineering_gates_pass'] is False and manifest['status'] == 'pretest_export_gate_no_go'
    with pytest.raises((ValueError, FileExistsError)):
        export.export(tmp_path / 'data/w33-export', stream_of(rows, []), {})


def test_gates_pass_status_when_minimums_met(tmp_path, monkeypatch, rows):
    monkeypatch.setattr(export, 'ROOT', tmp_path)
    monkeypatch.setattr(export, 'GATES', dict.fromkeys(export.GATES, 0))
    manifest = export.export(tmp_path / 'data/out', stream_of(rows, []), {})
    assert manifest['engineering_gates_pass'] and manifest['status'] == 'pretest_export_not_release'


def test_output_location_checked_before_any_stream(tmp_path, monkeypatch):
    monkeypatch.setattr(export, 'ROOT', tmp_path)
    (tmp_path / 'data/exists').mkdir(parents=True)
    never = lambda end: pytest.fail('Stream opened before output checks')
    for target in [tmp_path / 'public', tmp_path / 'data/exists']:
        with pytest.raises(ValueError):
            export.export(target, never, {})


def test_reserved_or_misordered_rows_fail_closed(tmp_path, monkeypatch, rows):
    monkeypatch.setattr(export, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='reserved'):  # a reserved row reaching extraction
        export.extract(rows + [native('alice', '2018-01-15')], [account('alice')])
    with pytest.raises(ValueError, match='after fitting'):  # a stream ignoring the cohort cut-off
        export.export(tmp_path / 'data/b', lambda end: iter(rows), {})
    assert not (tmp_path / 'data/b').exists()
    with pytest.raises(ValueError, match='reversal'):
        export.extract(list(reversed(rows)), [account('alice')])


def test_sources_changing_during_extraction_fail_closed(tmp_path, monkeypatch, rows):
    monkeypatch.setattr(export, 'ROOT', tmp_path)
    answers = iter([{'a': '1'}, {'a': '2'}])
    monkeypatch.setattr(reader, 'source_hashes', lambda names, root=None: next(answers))
    with pytest.raises(ValueError, match='changed'):
        export.export(tmp_path / 'data/c', stream_of(rows, []), {})
    assert not (tmp_path / 'data/c').exists()
