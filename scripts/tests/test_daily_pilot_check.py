from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from scripts import daily_pilot_check as daily

NOW = datetime(2026, 11, 1, 1, tzinfo=timezone.utc)


def inputs():
    study = {'days': [], 'status': 'history_pending', 'history_gates_pass': False, 'eligible_roles': 0}
    tick = {'at_utc': NOW.isoformat(), 'ok': True,
            'phases': {s: {'ok': True} for s in ('aws', 'actors', 'audit')}}
    polls = {s: {'last_attempt': NOW.isoformat(), 'last_outcome': {'ok': True}}
             for s in ('github', 'cloudflare')}
    return study, tick, polls


@pytest.mark.parametrize('offset,status', [(0, 'fresh'), (-15, 'fresh'), (-16, 'stale'), (1, 'future_timestamp')])
def test_tick_freshness(offset, status):
    assert daily.freshness((NOW + timedelta(minutes=offset)).isoformat(), NOW, 15)['status'] == status


@pytest.mark.parametrize('value', [None, '', '2026-11-01T00:00:00', 'invalid'])
def test_bad_freshness_is_unknown(value):
    assert daily.freshness(value, NOW, 15)['status'] == 'unknown_invalid_or_missing_time'


def test_future_and_partial_history_are_not_failures():
    study, tick, polls = inputs()
    study['days'] = [{'day': '2026-11-02', 'status': 'future'},
                     {'day': '2026-11-01', 'status': 'current_partial'}]
    result = daily.summarize(study, tick, polls, NOW)
    assert result['issues'] == []
    assert result['history_gates_pass'] is False
    assert result['scoring_decision'] == 'not_assessed'


def test_old_incomplete_day_remains_visible_and_yesterday_roles_reported():
    study, tick, polls = inputs()
    study['days'] = [{'day': '2026-10-30', 'status': 'incomplete', 'persona': 'persona-01'},
                     {'day': '2026-10-31', 'status': 'usable', 'persona': 'persona-02'}]
    result = daily.summarize(study, tick, polls, NOW)
    assert 'incomplete_closed_study_days' in result['issues']
    assert result['incomplete_closed_study_roles'][0]['day'] == '2026-10-30'
    assert len(result['yesterday_aws_study_roles']) == 1


def test_failed_poll_is_separate_from_activity():
    study, tick, polls = inputs()
    polls['github']['last_outcome']['ok'] = False
    tick['phases']['aws']['ok'] = False
    result = daily.summarize(study, tick, polls, NOW)
    assert 'github_poll_needs_review' in result['issues']
    assert 'aws_phase_failed_or_unknown' in result['issues']


def test_new_failure_marker_is_not_hidden_by_fresh_success():
    study, tick, polls = inputs()
    failed = {'at_utc': (NOW + timedelta(seconds=1)).isoformat()}
    assert 'collector_failure_newer_than_last_completed_tick' in daily.summarize(study, tick, polls, NOW, failed)['issues']
    old = {'at_utc': (NOW - timedelta(minutes=1)).isoformat()}
    assert daily.summarize(study, tick, polls, NOW, old)['issues'] == []


def test_journal_day_window_excludes_expected_overnight_gap(tmp_path):
    path = tmp_path / 'journal.jsonl'
    start = datetime(2026, 10, 31, 8, tzinfo=daily.MY)
    ticks = [{'at_utc': (start + timedelta(minutes=n)).isoformat(), 'ok': True} for n in range(0, 720, 5)]
    path.write_text('\n'.join(json.dumps(t) for t in ticks))
    result = daily.journal_summary(path, '2026-10-31')
    assert result['max_gap_minutes_including_active_window_boundaries'] == 5
    assert result['complete_coverage_asserted'] is False
    path.write_text(path.read_text() + '\nmalformed\n' + json.dumps({'at_utc': start.isoformat(), 'ok': False}))
    result = daily.journal_summary(path, '2026-10-31')
    assert result['malformed_lines'] == 1 and result['failed_tick_reports'] == 1


def test_missing_and_empty_journal_are_not_complete(tmp_path):
    path = tmp_path / 'none.jsonl'
    assert daily.journal_summary(path, '2026-10-31')['status'] == 'missing_telemetry'
    path.write_text('')
    assert daily.journal_summary(path, '2026-10-31')['max_gap_minutes_including_active_window_boundaries'] == 720


def test_journal_bound(tmp_path):
    path = tmp_path / 'journal.jsonl'
    path.write_bytes(b'x' * (10 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match='bound'):
        daily.journal_summary(path, '2026-10-31')


def test_observed_sources_scoped_readonly_and_zero_is_not_failure(tmp_path):
    database = tmp_path / 'events.db'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE events(source, source_account_id, resource, timestamp, "user")')
        db.executemany('INSERT INTO events VALUES (?,?,?,?,?)', [
            ('aws_cloudtrail', 'private-account', '', '2026-10-30T16:00:00Z', 'private-user'),
            ('aws_cloudtrail', 'other-account', '', '2026-10-30T16:00:00Z', 'other-user'),
            ('github_events', 'owner', 'private/repo', 'bad', 'private-login')])
    cfg = {'account_id': 'private-account', 'repo': 'private/repo', 'cloudflare': {'account': 'cf-id'}}
    before = database.read_bytes()
    result = daily.observed(database, cfg, '2026-10-31')
    assert database.read_bytes() == before
    assert result['aws_cloudtrail']['events_yesterday'] == 1
    assert result['cloudflare_access']['activity_status'] == 'no_observed_activity'
    assert result['github_events']['invalid_timestamps_in_source_snapshot'] == 1
    assert 'private' not in json.dumps(result)


def test_run_failure_preserves_good_report(tmp_path):
    config = tmp_path / 'config.json'
    output = tmp_path / 'reports'
    output.mkdir()
    latest = output / 'latest.json'
    latest.write_bytes(b'old-good-report')
    config.write_text(json.dumps({'schema': 'argus_daily_check_config_v1', 'source_hashes': {},
                                  'output_dir': str(output)}))
    with pytest.raises(ValueError, match='Daily check failed'):
        daily.run(config)
    assert latest.read_bytes() == b'old-good-report'
    assert json.loads((output / 'last_attempt.json').read_text())['ok'] is False


def test_report_run_and_expiry_without_provider_calls(tmp_path, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(daily, 'datetime', Clock)
    study, tick, polls = inputs()
    monkeypatch.setattr(daily.readiness, 'evaluate', lambda *args: study)
    monkeypatch.setattr(daily, 'observed', lambda *args: {'cloudflare_access': {'events_yesterday': 0}})
    (tmp_path / 'last_tick.json').write_text(json.dumps(tick))
    (tmp_path / 'poll_state.json').write_text(json.dumps(polls))
    pilot = tmp_path / 'pilot.json'
    pilot.write_text(json.dumps({'schema': 'argus_local_pilot_v2', 'source_root': str(daily.ROOT),
                                'actor_start': '2026-10-29', 'end_local': '2026-11-16',
                                'state_dir': str(tmp_path), 'ledger_dir': str(tmp_path),
                                'connected_dir': str(tmp_path), 'account_id': 'test', 'stack': 'test'}))
    config = tmp_path / 'check.json'
    config.write_text(json.dumps({'schema': 'argus_daily_check_config_v1', 'output_dir': str(tmp_path),
                                  'pilot_config': str(pilot), 'source_hashes': daily.hashes()}))
    result = daily.run(config)
    assert result['issues'] == ['yesterday_tick_telemetry_missing']
    assert json.loads((tmp_path / 'last_attempt.json').read_text())['ok'] is True
    report = json.loads((tmp_path / 'latest.json').read_text())
    assert report['observed_sources']['cloudflare_access']['events_yesterday'] == 0
    before = (tmp_path / 'latest.json').read_bytes()
    monkeypatch.setattr(daily, 'END', NOW)
    assert daily.run(config)['status'] == 'check_period_expired'
    assert (tmp_path / 'latest.json').read_bytes() == before
