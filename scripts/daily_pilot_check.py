"""Read-only pilot coverage; no provider calls, actor actions, scores or activation."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
from pathlib import Path
import os
import sqlite3
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import live_history_readiness as readiness

MY = readiness.MALAYSIA
END = readiness.protocol.SERVICE_EXPIRES
DEPENDENCIES = ('scripts/aws_study_v3.py', 'scripts/daily_pilot_check.py', 'scripts/live_history_readiness.py',
                'scripts/persona_history_plan.py', 'scripts/simulation_lab.py', 'scripts/persona_profiles_v2.json')


def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in DEPENDENCIES}


def stamp(value):
    if not isinstance(value, str):
        raise ValueError('Timestamp required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Zoned timestamp required')
    return result


def freshness(value, now, minutes):
    try:
        age = (now - stamp(value)).total_seconds()
    except (ValueError, TypeError):
        return {'status': 'unknown_invalid_or_missing_time'}
    return {'status': 'future_timestamp' if age < 0 else 'fresh' if age <= minutes * 60 else 'stale',
            'age_minutes': round(age / 60, 2)}


def journal_summary(path, day):
    midnight = datetime.fromisoformat(day).replace(tzinfo=MY)
    start, end = midnight + timedelta(hours=8), midnight + timedelta(hours=20)
    if not path.exists():
        return {'status': 'missing_telemetry', 'complete_coverage_asserted': False}
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError('Journal bound exceeded')
    times, bad, failed = [], 0, 0
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines()):
        if number >= 10000:
            raise ValueError('Journal bound exceeded')
        try:
            item = json.loads(line)
            when = stamp(item['at_utc'])
            if not midnight <= when < midnight + timedelta(days=1) or type(item.get('ok')) is not bool:
                raise ValueError('Invalid journal tick')
            if start <= when < end:
                times.append(when)
                failed += not item['ok']
        except (ValueError, KeyError, TypeError):
            bad += 1
    boundaries = [start, *sorted(set(times)), end]
    gap = max((b - a).total_seconds() / 60 for a, b in zip(boundaries, boundaries[1:]))
    return {'status': 'observed_telemetry_only', 'ticks': len(times), 'failed_tick_reports': failed,
            'malformed_lines': bad, 'active_window': '08:00-20:00 MY',
            'max_gap_minutes_including_active_window_boundaries': round(gap, 2),
            'complete_coverage_asserted': False}


def observed(database, cfg, day):
    """One RO snapshot; no activity does not establish normality."""
    conditions = [('aws_cloudtrail', cfg['account_id'], None), ('github_events', None, cfg['repo'])]
    if cfg.get('cloudflare'):
        conditions.append(('cloudflare_access', cfg['cloudflare']['account'], None))
    result = {}
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        for source, namespace, resource in conditions:
            sql, args = 'SELECT timestamp,"user" FROM events WHERE source=?', [source]
            if namespace is not None:
                sql += ' AND source_account_id=?'
                args.append(namespace)
            if resource is not None:
                sql += ' AND resource=?'
                args.append(resource)
            rows = db.execute(sql + ' LIMIT 100001', args).fetchall()
            if len(rows) > 100000:
                raise ValueError('Native store bound exceeded')
            count, invalid, actors = 0, 0, set()
            for timestamp, actor in rows:
                try:
                    if stamp(timestamp).astimezone(MY).date().isoformat() == day:
                        count += 1
                        if isinstance(actor, str) and actor:
                            actors.add(actor)
                except (ValueError, TypeError):
                    invalid += 1
            result[source] = {'events_yesterday': count, 'observed_account_references': len(actors),
                              'invalid_timestamps_in_source_snapshot': invalid,
                              'activity_status': 'observed_activity' if count else 'no_observed_activity',
                              'source_completeness': 'unknown'}
    return result


def summarize(study, tick, polls, now, failure=None):
    yesterday = (now.astimezone(MY).date() - timedelta(days=1)).isoformat()
    closed = [r for r in study['days'] if r['day'] < now.astimezone(MY).date().isoformat()]
    incomplete = [r for r in closed if r['status'] == 'incomplete']
    roles = [r for r in closed if r['day'] == yesterday]
    issues = []
    current = freshness(tick.get('at_utc'), now, 15)
    if current['status'] != 'fresh':
        issues.append('collector_tick_' + current['status'])
    if tick.get('ok') is not True:
        issues.append('collector_last_tick_failed_or_unknown')
    if failure:
        try:
            if stamp(failure['at_utc']) > stamp(tick.get('at_utc')):
                issues.append('collector_failure_newer_than_last_completed_tick')
        except (ValueError, KeyError, TypeError):
            issues.append('collector_failure_marker_time_unknown')
    provider_status = {}
    for source in ('github', 'cloudflare'):
        poll = polls.get(source, {})
        status = freshness(poll.get('last_attempt'), now, 75)
        status['outcome'] = 'success' if poll.get('last_outcome', {}).get('ok') is True else 'failed_or_unknown'
        provider_status[source] = status
        if status['status'] != 'fresh' or status['outcome'] != 'success':
            issues.append(source + '_poll_needs_review')
    if incomplete:
        issues.append('incomplete_closed_study_days')
    phases = tick.get('phases', {})
    for source in ('aws', 'actors', 'audit'):
        if phases.get(source, {}).get('ok') is not True:
            issues.append(source + '_phase_failed_or_unknown')
    return {'schema': 'argus_daily_pilot_check_v1', 'study': readiness.protocol.binding(), 'study_sha256': readiness.protocol.binding_sha256(), 'computed_at_utc': now.isoformat(),
            'timezone': 'Asia/Kuala_Lumpur', 'yesterday': yesterday,
            'status': 'needs_attention' if issues else 'operational_checks_pass', 'issues': issues,
            'collector_tick': current, 'provider_polls': provider_status,
            'yesterday_aws_study_roles': roles,
            'yesterday_study_status': 'study_day' if roles else 'outside_normal_study_windows',
            'incomplete_closed_study_roles': incomplete,
            'history_status': study['status'], 'history_gates_pass': study['history_gates_pass'],
            'eligible_roles': study['eligible_roles'], 'current_phase_context': {
                'actor_action_states': phases.get('actors', {}).get('action_states', {}),
                'audit_pending_or_ambiguous': phases.get('audit', {}).get('pending_or_ambiguous')},
            'model_release_evaluated': False, 'scoring_decision': 'not_assessed',
            'limitations': ['Operational check only, not proof of source completeness or normal behavior.',
                            'Separate ledger/native/telemetry snapshots; late receipts may require recheck.',
                            'No observed SaaS activity is not necessarily a collector failure.',
                            'Future and current-partial study days are not incomplete closed days.']}


def atomic_json(path, value):
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temp, path)


def run(check_config):
    config = json.loads(Path(check_config).read_text(encoding='utf-8-sig'))
    output = Path(config['output_dir']).resolve()
    if not output.is_dir():
        raise ValueError('Existing private output directory required')
    now = datetime.now(timezone.utc)
    if now >= END:
        return {'status': 'check_period_expired'}
    try:
        if config.get('schema') != 'argus_daily_check_config_v1' or config.get('source_hashes') != hashes():
            raise ValueError('Checker source drift')
        cfg = json.loads(Path(config['pilot_config']).read_text(encoding='utf-8-sig'))
        if cfg.get('schema') != 'argus_local_pilot_v2' or Path(cfg['source_root']).resolve() != ROOT:
            raise ValueError('Unexpected pilot config')
        state = Path(cfg['state_dir'])
        load = lambda name: json.loads((state / name).read_text()) if (state / name).exists() else {}
        study = readiness.evaluate(Path(cfg['ledger_dir']) / 'ledger.db', Path(cfg['connected_dir']) / 'events.db',
                                   cfg['account_id'], cfg['stack'], now)
        report = summarize(study, load('last_tick.json'), load('poll_state.json'), now, load('tick_failure.json'))
        report['observed_sources'] = observed(Path(cfg['connected_dir']) / 'events.db', cfg, report['yesterday'])
        report['yesterday_tick_journal'] = journal_summary(state / (report['yesterday'] + '-ticks.jsonl'), report['yesterday'])
        journal = report['yesterday_tick_journal']
        expected = cfg['actor_start'] <= report['yesterday'] <= cfg['end_local']
        report['yesterday_collection_expected'] = expected
        if not expected:
            journal['assessment'] = 'outside_pilot_collection_period'
        elif journal['status'] == 'missing_telemetry':
            report['issues'].append('yesterday_tick_telemetry_missing')
        elif (journal['malformed_lines'] or journal['failed_tick_reports']
              or journal['max_gap_minutes_including_active_window_boundaries'] > 15):
            report['issues'].append('yesterday_tick_failures_or_gaps_review')
        report['status'] = 'needs_attention' if report['issues'] else 'operational_checks_pass'
        if config['source_hashes'] != hashes():
            raise ValueError('Checker source changed during run')
        report['checker_source_sha256'] = config['source_hashes']
        snapshot = output / (now.strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid4().hex + '.json')
        with snapshot.open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
        atomic_json(output / 'latest.json', report)
        atomic_json(output / 'last_attempt.json', {'computed_at_utc': now.isoformat(), 'ok': True, 'status': report['status']})
        return {'status': report['status'], 'issues': report['issues'], 'yesterday': report['yesterday']}
    except Exception:
        atomic_json(output / 'last_attempt.json', {'computed_at_utc': now.isoformat(), 'ok': False,
                                                 'status': 'check_failed_previous_report_may_be_stale'})
        raise ValueError('Daily check failed; inspect scope/files/source pins. Previous report may be stale.') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    try:
        result = run(args.config)
        if sys.stdout:
            print(json.dumps(result))
        return 0
    except Exception:
        if sys.stderr:
            print('Daily check failed; see private last_attempt.json. No raw errors displayed.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
