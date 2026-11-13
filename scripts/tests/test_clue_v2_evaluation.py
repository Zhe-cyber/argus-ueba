"""W33 evaluator tests on synthetic rows, archives and scorers; never the real archive or test window."""
from datetime import date, datetime, timedelta, timezone
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from scripts import evaluate_clue_v2 as ev, shared_core_scenarios as scenarios
from scripts.shared_core_features import project_clue

_ids = iter(range(1, 10**9))
UIDS = ['u0', 'u1', 'u2', 'u3', 'u4']


def native(uid, day, hour=10, action='file_accessed', path='/ns/f'):
    return {'id': next(_ids), 'uid': uid, 'uidType': 'name', 'type': action, 'time': f'{day}T{hour:02d}:00:00Z',
            'params': {} if path is None else {'path': path}}


def account(uid):
    return project_clue(native(uid, '2017-08-07')).account


def history_days(first='2017-08-07', count=6):
    return [(date.fromisoformat(first) + timedelta(i)).isoformat() for i in range(count)]


def fake_scorers(seen=None):
    def score_v2(snapshot, acct):
        if seen is not None:
            seen.append((acct, snapshot['prior_usable_days']))
        if not snapshot['five_feature_eligible']:
            return dict.fromkeys(['B', 'C', 'C_norm', 'BL'])
        f = snapshot['features']
        nine = snapshot['nine_feature_eligible']
        return {'B': float(f['event_count']), 'C': float(f['unique_actions']) if nine else None,
                'C_norm': float(f['new_action_count']) if nine else None, 'BL': float(f['off_hours_fraction']) if nine else None}
    return score_v2, (lambda snap: float(snap['features']['event_count']) if snap['eligible'] else None)


def scenario_rows(invalid_uid=None, silent_uid=None):
    rows = [native(uid, d) for d in history_days() for uid in UIDS]
    for day in ('2018-01-15', '2018-01-16'):
        for uid in UIDS:
            if uid == silent_uid:
                continue
            rows += [native(uid, day, hour=9), native(uid, day, hour=14)]
            if uid == invalid_uid and day == '2018-01-15':
                rows.append(native(uid, day, path=None))  # path-required event without a path
    return sorted(rows, key=lambda r: (r['time'], r['id']))


def test_analyse_scores_once_and_variants_never_enter_history():
    seen = []
    score_v2, score_a = fake_scorers(seen)
    cohort = [account(u) for u in UIDS]
    result = ev.analyse(iter(scenario_rows()), cohort, ('2018-01-15', '2018-01-16'), score_v2, score_a)
    assert len(result['normal']) == 10 and all(r['scores']['A'] == 2.0 for r in result['normal'])
    # 6 history days. Day 1 originals and all its variants see 6 priors; day 2 sees exactly 7
    # (day 1's original only), however many variants day 1 produced.
    assert {prior for _, prior in seen} == {6, 7}
    assert sum(prior == 7 for _, prior in seen) >= 5
    families = {row['family'] for row in result['cases']}
    assert families == set(ev.FAMILIES)
    mass = [row for row in result['cases'] if row['family'] == 'mass_access']
    assert all(row['scores']['B'] == 10.0 for row in mass)  # 2 reads -> 10 events
    pairs = dict(scenarios.pairs(sorted(cohort)))
    switched = {row['account'] for row in result['cases'] if row['family'] == 'account_switch'}
    assert switched == set(pairs) and len(pairs) == 2 and result['switch_design'] == {'pairs': 2, 'unpaired_accounts': 1}


def test_invalid_original_and_inactive_donor_are_excluded_not_negative():
    cohort = [account(u) for u in UIDS]
    pairs = dict(scenarios.pairs(sorted(cohort)))
    target, donor = next(iter(pairs.items()))
    uid_of = {account(u): u for u in UIDS}
    score_v2, score_a = fake_scorers()
    result = ev.analyse(iter(scenario_rows(invalid_uid=uid_of[target], silent_uid=uid_of[pairs[next(t for t in pairs if t != target)]])),
                        cohort, ('2018-01-15', '2018-01-16'), score_v2, score_a)
    for family in ev.FAMILIES:
        assert result['exclusions'][family].get('invalid_original') == 1
    assert result['exclusions']['account_switch'].get('donor_inactive_or_unscorable', 0) >= 2
    invalid_normal = [r for r in result['normal'] if r['account'] == target and r['day'] == '2018-01-15']
    assert invalid_normal[0]['v2_status'] == 'invalid_input' and all(v is None for v in invalid_normal[0]['scores'].values())
    assert result['unscored_normal'] == {'invalid_input': 1}


def test_pretest_replay_collects_only_row_partitions():
    rows = [native(u, d) for d in history_days('2017-11-20', 10) for u in UIDS[:2]]
    score_v2, score_a = fake_scorers()
    result = ev.analyse(iter(rows), [account(u) for u in UIDS[:2]], None, score_v2, score_a, collect_rows=True)
    assert {r['partition'] for r in result['past_rows']} == {'fit', 'validation'}
    assert result['normal'] == [] and result['cases'] == []


def row(scores, family=None, original=None):
    item = {'scores': dict(zip(ev.DETECTORS, scores))}
    if family:
        item.update(family=family, original_scores=dict(zip(ev.DETECTORS, original or [0] * 5)))
    return item


def test_metrics_strict_thresholds_common_subset_and_unavailable_detector():
    normal = [row([0.1, 0.1, 0.1, None, 0.1]), row([0.2, 0.2, 0.2, 0.2, 0.2]), row([0.9, 0.9, 0.9, 0.9, 0.9])]
    cases = [row([0.5, 0.5, 0.5, 0.5, 0.5], f, [0.1] * 5) for f in ev.FAMILIES]
    thresholds = {d: {'0.01': 0.5, '0.05': 0.3} for d in ev.DETECTORS}
    thresholds['C_norm'] = None
    table = ev.metrics(normal, cases, thresholds)
    a = table['mass_access']['A']
    assert a['auroc'] == pytest.approx(2 / 3) and a['budgets']['0.01']['case_recall'] == 0.0  # strict >
    assert a['budgets']['0.05']['case_recall'] == 1.0 and a['budgets']['0.05']['normal_alert_fraction'] == pytest.approx(1 / 3)
    assert table['mass_access']['C_norm']['budgets']['0.01'] is None
    assert table['mass_access']['C_norm']['normal_days'] == 2
    assert a['paired_change'] == {'cases': 1, 'median': 0.4, 'positive_fraction': 1.0}
    common = ev.metrics(normal, cases, thresholds, common=True)
    assert common['mass_access']['A']['normal_days'] == 2  # the row lacking C_norm leaves the common subset


def test_dominance_requires_every_condition():
    cell = lambda recall, alert: {'case_recall': recall, 'normal_alert_fraction': alert}
    def table(left, right):
        return {f: {d: {'budgets': {b: (left if d == 'B' else right) for b in ev.BUDGETS}} for d in ev.DETECTORS}
                for f in ev.FAMILIES}
    coverage = dict.fromkeys(ev.DETECTORS, 10)
    assert ev.dominance(table(cell(0.6, 0.01), cell(0.5, 0.01)), coverage)['B_vs_A']['0.01'] == 'descriptively_dominant'
    assert ev.dominance(table(cell(0.6, 0.02), cell(0.5, 0.01)), coverage)['B_vs_A']['0.01'] == 'trade_off_or_no_gain'
    assert ev.dominance(table(cell(0.5, 0.01), cell(0.5, 0.01)), coverage)['B_vs_A']['0.01'] == 'trade_off_or_no_gain'
    assert ev.dominance(table(cell(0.6, 0.01), cell(0.5, 0.01)), {**coverage, 'B': 9})['B_vs_A']['0.01'] == 'trade_off_or_no_gain'
    assert ev.dominance(table(None, cell(0.5, 0.01)), coverage)['B_vs_A']['0.01'] == 'not_comparable'


def archive(tmp_path, items):
    path = tmp_path / 'archive.zip'
    with ZipFile(path, 'w', ZIP_DEFLATED) as zipped:
        zipped.writestr('clue.json', b''.join(i if isinstance(i, bytes) else json.dumps(i).encode() + b'\n' for i in items))
    return path


def test_stream_window_closes_at_boundary_without_reading_further(tmp_path):
    path = archive(tmp_path, [native('u0', '2017-08-06'), native('u0', '2017-08-07'), native('u0', '2018-01-28'),
                              native('u0', '2018-01-29'), b'{"truncated'])
    assert [r['time'][:10] for r in ev.stream_window(path, '2018-01-28')] == ['2017-08-07', '2018-01-28']
    with pytest.raises(ValueError, match='boundary'):
        list(ev.stream_window(archive(tmp_path, [native('u0', '2017-08-07')]), '2018-01-28'))


def test_release_refused_after_freeze_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, 'load_scorers', lambda *a: pytest.fail('Scorers loaded after the gate'))
    late = datetime(2026, 11, 15, 16, 0, tzinfo=timezone.utc)  # 16 Nov 00:00 MYT
    with pytest.raises(ValueError, match='freeze gate'):
        ev.release('r', 'p', 't', 'v', 'val', 'reh', tmp_path / 'data/release.json', clock=lambda: late)


@pytest.fixture
def released(tmp_path, monkeypatch):
    monkeypatch.setattr(ev, 'ROOT', tmp_path)
    monkeypatch.setattr(ev.trainer, 'ROOT', tmp_path)
    cohort = [account(u) for u in UIDS]
    score_v2, score_a = fake_scorers()
    thresholds = {d: {'0.01': 5.0, '0.05': 3.0} for d in ev.DETECTORS}
    record = {'artifacts': {'archive': {'path': 'archive.zip'}, 'preregistration': {'path': 'p'},
                            'training_manifest': {'path': str(tmp_path / 'training/manifest.json')},
                            'v1_release': {'path': 'v1'}},
              'thresholds': thresholds, 'cohort_sha256': ev.v2.digest(sorted(cohort))}
    monkeypatch.setattr(ev, 'verify_release', lambda path, expected: record)
    monkeypatch.setattr(ev, 'load_scorers', lambda *a: {'cohort': cohort, 'score_v2': score_v2, 'score_a': score_a,
                                                         'thresholds': thresholds})
    monkeypatch.setattr(ev, 'stream_window', lambda archive_path, end: iter(scenario_rows()))
    return tmp_path


MYT_16 = datetime(2026, 11, 16, 2, 0, tzinfo=timezone.utc)


def test_evaluate_only_inside_execution_window(released):
    for moment in [datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc), datetime(2026, 11, 17, 16, 30, tzinfo=timezone.utc)]:
        with pytest.raises(ValueError, match='execution window'):
            ev.evaluate('release.json', 'sha', released / 'data/eval', now=moment)
    assert not (released / ev.ACCESS_CLAIM).exists()


def test_single_reserved_access_per_experiment(released):
    document = ev.evaluate('release.json', 'sha', released / 'data/eval', now=MYT_16)
    assert document['status'] == 'reserved_evaluation_completed' and document['activated'] is False
    assert set(document['summary']['metrics_common']) == set(ev.FAMILIES)
    assert (released / ev.ACCESS_CLAIM).exists()
    with pytest.raises(FileExistsError):
        ev.evaluate('release.json', 'sha', released / 'data/eval-2', now=MYT_16)


def test_failed_access_stays_claimed_and_disclosed(released, monkeypatch):
    monkeypatch.setattr(ev, 'analyse', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('failure after access')))
    with pytest.raises(RuntimeError):
        ev.evaluate('release.json', 'sha', released / 'data/eval', now=MYT_16)
    assert (released / (ev.ACCESS_CLAIM + '.failed.json')).exists()
    with pytest.raises(FileExistsError):
        ev.evaluate('release.json', 'sha', released / 'data/eval-2', now=MYT_16)


def test_scorer_mismatch_with_release_stops_before_access(released, monkeypatch):
    original = ev.load_scorers
    monkeypatch.setattr(ev, 'load_scorers', lambda *a: {**original(), 'thresholds': {}})
    with pytest.raises(ValueError, match='changed'):
        ev.evaluate('release.json', 'sha', released / 'data/eval', now=MYT_16)
    assert not (released / ev.ACCESS_CLAIM).exists()


# --- Corrections after Codex review: generation accounting, unavailable vectors, release binding ---

def test_generated_then_unscorable_variants_are_counted_not_dropped():
    def score_v2(snapshot, acct):  # the 10-event mass-access variant is unscorable by every W33 detector
        if not snapshot['five_feature_eligible'] or snapshot['features']['event_count'] > 5:
            return dict.fromkeys(['B', 'C', 'C_norm', 'BL'])
        return dict.fromkeys(['B', 'C', 'C_norm', 'BL'], 1.0)
    score_a = lambda snap: (1.0 if snap['eligible'] and snap['features']['event_count'] <= 5 else None)
    result = ev.analyse(iter(scenario_rows()), [account(u) for u in UIDS], ('2018-01-15', '2018-01-16'), score_v2, score_a)
    mass = result['generation']['mass_access']
    assert mass['generated'] == 10 and mass['unscorable_by_all'] == 10 and mass['retained_scored_by_any'] == 0
    assert mass['unscored_by_detector'] == dict.fromkeys(ev.DETECTORS, 10)
    assert 'unscorable_variant' not in result['exclusions']['mass_access']
    summary = ev.summarise(result, {d: {'0.01': 5.0, '0.05': 3.0} for d in ev.DETECTORS})
    assert summary['generation']['mass_access']['generated'] == 10


def test_missing_v2_vector_is_unavailable_not_unchanged():
    rows = scenario_rows()
    for day in history_days()[:2]:  # two invalid W33 history days: A still has 6 priors, W33 only 4
        rows.append(native('u0', day, path=None))
    rows.sort(key=lambda r: (r['time'], r['id']))
    score_v2 = lambda snap, acct: dict.fromkeys(['B', 'C', 'C_norm', 'BL'], None if not snap['five_feature_eligible'] else 1.0)
    score_a = lambda snap: 1.0 if snap['eligible'] else None
    result = ev.analyse(iter(rows), [account(u) for u in UIDS], ('2018-01-15', '2018-01-16'), score_v2, score_a)
    u0 = [row for row in result['cases'] if row['account'] == account('u0') and row['day'] == '2018-01-15']
    assert u0 and all(row['scores']['A'] == 1.0 and row['scores']['B'] is None for row in u0)
    assert all(row['feature_unchanged']['v2'] is None for row in u0)
    summary = ev.summarise(result, {d: {'0.01': 5.0, '0.05': 3.0} for d in ev.DETECTORS})
    assert summary['feature_unchanged']['off_hours']['v2'].get('unavailable', 0) >= 1


def synthetic_validation_export(directory):
    import hashlib
    from scripts import clue_v2_features as features, clue_v2_access as access
    values = dict.fromkeys(features.FEATURES, 1)
    values.update(volume_log_ratio=0.0, new_resource_share=0.5, action_mix_js_distance=0.2, hour_profile_js_distance=0.3)
    rows = [{'partition': 'validation', 'account': f'user-{i}', 'day': '2017-11-27', 'status': 'eligible',
             'features': values, 'unavailable': {}} for i in range(3)]
    body = b''.join(access.canonical(r) + b'\n' for r in rows)
    directory.mkdir(parents=True)
    (directory / 'rows-validation.jsonl').write_bytes(body)
    (directory / 'manifest.json').write_bytes(access.canonical({
        'schema': 'w33_pretest_export_v1', 'reserved_access': False,
        'partition_rows_sha256': {'validation': hashlib.sha256(body).hexdigest()},
        'feature_contract_sha256': features.contract_sha256()}) + b'\n')
    return directory


def test_validation_report_must_be_the_one_generated_from_the_bound_export(tmp_path, monkeypatch):
    from scripts import report_clue_v2_validation as report
    monkeypatch.setattr(report, 'ROOT', tmp_path)
    export_dir = synthetic_validation_export(tmp_path / 'data/export')
    genuine = tmp_path / 'results/report.md'
    report.report(export_dir, genuine)
    assert len(ev.verify_validation_report(genuine, export_dir)) == 64
    unrelated = tmp_path / 'unrelated.md'
    unrelated.write_text('unrelated report, no W33 bindings\n')
    stale = tmp_path / 'stale.md'
    stale.write_bytes(genuine.read_bytes().replace(b'account-days: 3', b'account-days: 4'))
    assert stale.read_bytes() != genuine.read_bytes()
    for candidate in (unrelated, stale):
        with pytest.raises(ValueError, match='not the one produced'):
            ev.verify_validation_report(candidate, export_dir)


@pytest.fixture
def release_inputs(tmp_path, monkeypatch):
    """Real release construction with fixture artifacts; scorers and receipts are stubbed only."""
    import hashlib
    monkeypatch.setattr(ev.trainer, 'ROOT', tmp_path)
    files = {}
    for name in ['archive.zip', 'reader.json', 'prereg.json', 'training/manifest.json', 'training/B/model.pt',
                 'training/B/scaler.json', 'training/C/model.pt', 'training/C/scaler.json',
                 'training/c_norm_references.json', 'training/thresholds.json', 'v1.json', 'report.md']:
        path = tmp_path / 'inputs' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('fixture ' + name + '\n').encode())
        files[name] = path
    monkeypatch.setattr(ev.access, 'ARCHIVE_SHA', hashlib.sha256(files['archive.zip'].read_bytes()).hexdigest())
    loaded = {'cohort': ['a', 'b'], 'thresholds': {d: {'0.01': 1.0, '0.05': 0.5} for d in ev.DETECTORS},
              'training_manifest_sha256': 'm' * 64, 'preregistration_sha256': 'p' * 64,
              'v1_release_sha256': 'v' * 64, 'export_path': str(tmp_path / 'export')}
    monkeypatch.setattr(ev, 'load_scorers', lambda *a: loaded)
    monkeypatch.setattr(ev.reader, 'verify_reader', lambda path: ({}, str(files['archive.zip'])))
    validated = []
    monkeypatch.setattr(ev, 'verify_validation_report', lambda path, export: validated.append((path, export)) or 'x')
    rehearsal = {'status': ev.REHEARSAL_STATUS, 'test_rows_accessed': False, 'thresholds_reproduced': True,
                 'rows_compared': 4917, 'evaluator_source_sha256': ev.reader.source_hashes(ev.EVALUATOR_SOURCES),
                 'training_manifest_sha256': 'm' * 64, 'preregistration_sha256': 'p' * 64,
                 'v1_release_sha256': 'v' * 64, 'detector_a_thresholds': loaded['thresholds']['A']}
    counter = iter(range(1000))

    def run(rehearsal_changes=None, clock=lambda: datetime(2026, 11, 10, tzinfo=timezone.utc)):
        path = tmp_path / ('rehearsal-' + str(next(counter)) + '.json')
        path.write_text(json.dumps({**rehearsal, **(rehearsal_changes or {})}))
        return ev.release(files['reader.json'], files['prereg.json'], files['training/manifest.json'].parent,
                          files['v1.json'], files['report.md'], path, tmp_path / 'data/release.json', clock=clock)
    return tmp_path, run, validated


def test_release_positive_path_round_trips_through_real_verification(release_inputs):
    root, run, validated = release_inputs
    record = run()
    assert validated and record['created_at_utc'] == '2026-11-10T00:00:00+00:00'
    assert ev.verify_release(root / 'data/release.json', ev.sha(root / 'data/release.json')) == record


@pytest.mark.parametrize('changes', [{'v1_release_sha256': 'w' * 64}, {'detector_a_thresholds': {'0.01': 9.0, '0.05': 9.0}},
                                     {'thresholds_reproduced': False}, {'rows_compared': 0}])
def test_release_rejects_mismatched_rehearsal_evidence_before_writing(release_inputs, changes):
    root, run, _ = release_inputs
    with pytest.raises(ValueError, match='rehearsal'):
        run(rehearsal_changes=changes)
    assert not (root / 'data/release.json').exists()


def test_release_rechecks_freeze_after_artifact_work(release_inputs):
    root, run, _ = release_inputs
    moments = iter([datetime(2026, 11, 15, 15, 58, tzinfo=timezone.utc), datetime(2026, 11, 15, 16, 1, tzinfo=timezone.utc)])
    with pytest.raises(ValueError, match='freeze gate'):  # began 23:58 MYT, would finish 00:01 MYT
        run(clock=lambda: next(moments))
    assert not (root / 'data/release.json').exists()


@pytest.mark.parametrize('created', ['2026-11-15T16:00:01+00:00', '2026-11-10T00:00:00', 'not-a-time', None,
                                     '2026-11-10T08:00:00+08:00'])
def test_verify_release_rejects_late_naive_or_noncanonical_creation_time(release_inputs, created):
    import hashlib
    root, run, _ = release_inputs
    record = run()
    if created is None:
        record.pop('created_at_utc')
    else:
        record['created_at_utc'] = created
    body = {k: v for k, v in record.items() if k != 'release_sha256_body'}
    record['release_sha256_body'] = hashlib.sha256(ev.access.canonical(body)).hexdigest()
    forged = root / 'data/forged.json'
    forged.write_bytes(ev.access.canonical(record) + b'\n')
    with pytest.raises(ValueError):
        ev.verify_release(forged, ev.sha(forged))
