"""Versioned live-only coverage policy for W33 v2 diagnostics on the controlled AWS personas.

Diagnostic history selection only. It does not change the frozen W33 feature/evaluation
contract, the W33 release, the AWS study gates or any model/threshold. Read-only on the
ledger and the event store. Inert on import.

A controlled persona day enters diagnostic history, and may be scored, only if it is closed,
had at least one planned action, had >=90% of its frozen-plan actions independently
native-verified and available by the cut-off, and has no unresolved or not-yet-ingested claim.

- "Native-verified" means: unique native ID; the unchanged readiness matcher accepts it (exact
  operation/resource/request/principal/assumed-role ARN, success, inside the planned day).
- "Available by the cut-off" means: an aware `ingested_at` <= the same UTC cut-off as the feature
  snapshot.
- Planned idle days never become manufactured zero-event history.
- Excluded case dates are partitioned *before* ordinary-plan validation: their rows are counted,
  never validated as ordinary actions, and the day gets neither history nor a score.
- Coverage is coverage of planned controlled actions only. It does not prove the account had no
  other activity, nor that every log was collected.
- Non-persona accounts are outside this policy and their completeness stays unknown.
"""
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from scripts import live_history_readiness as readiness
from scripts.persona_history_plan import make_plan, MALAYSIA
from scripts.shared_core_features import digest, instant
from scripts.simulation_lab import buckets, validate_scope

POLICY = {
    'name': 'clue_v2_live_persona_coverage', 'version': 2,
    'applies_to': 'controlled AWS persona roles identified by verified assumed-role ARN and a valid native '
                  'scoped account key (acct_ + 64 hex) only',
    'denominator': 'frozen plan actions (persona_profiles_v2, PROFILE_SHA) for the persona and local day',
    'verification': 'unchanged live_history_readiness.native_matches with a unique native event ID, plus '
                    'aware ingested_at <= the common UTC cut-off',
    'usable': 'closed day, planned >= 1, verified*10 >= planned*9, unresolved == 0, not_yet_ingested == 0',
    # 29 Oct mixes warm-up with commissioning operations marked exclude-from-baseline, so diagnostic history
    # starts on 30 Oct. Days before the start have no policy cell and are excluded.
    'history_start_local': '2026-10-30',
    'commissioning': 'ledger rows with purpose commissioning_exclude_from_baseline are outside the denominator; '
                     'any persona day containing one is excluded from history and scoring',
    'excluded_dates_local': ['2026-11-14', '2026-11-15'],  # AWS V3 reserved case days: partitioned first
    'idle_days': 'planned idle: no history entry, never a zero-event active day',
    'incomplete_days': 'excluded from history; the day itself is reported incomplete and not scored',
    'non_persona_accounts': 'outside this policy; completeness unknown; frozen W33 history rules unchanged',
}
PERSONAS = [f'persona-{i:02d}' for i in range(1, 7)]
COMMISSIONING = 'commissioning_exclude_from_baseline'
FIELDS = ('persona', 'ordinal', 'planned_utc', 'planned_local', 'operation', 'symbolic_bucket', 'bucket', 'key')
ACCOUNT_KEY = re.compile(r'acct_[0-9a-f]{64}')


def policy_sha256():
    return digest(POLICY)


def utc_cutoff(at):
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ValueError('Aware cut-off required; naive times are never interpreted in host-local time')
    return at.astimezone(timezone.utc)


def planned_actions(day, account, stack):
    """Frozen-plan actions for one local day, with readiness-identical action IDs."""
    validate_scope(account, stack)
    raw = (readiness.ROOT / 'scripts/persona_profiles_v2.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != readiness.PROFILE_SHA:
        raise ValueError('Frozen daily profile differs')
    targets = dict(zip([f'p{i:02d}' for i in range(1, 7)] + ['confidential'], buckets(account, stack)))
    result = {}
    for row in make_plan(json.loads(raw), date.fromisoformat(day))['actions']:
        identity = f"{readiness.PROFILE_SHA}|{day}|{row['persona']}|{row['ordinal']}"
        action_id = hashlib.sha256(identity.encode()).hexdigest()
        result[action_id] = {**row, 'action_id': action_id, 'bucket': targets[row['symbolic_bucket']], 'day': day}
    return result


def ledger_rows(ledger, account, stack, start, end):
    with closing(sqlite3.connect(Path(ledger).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        scope = db.execute('SELECT contract FROM scope WHERE id=1').fetchone()
        if scope is None or json.loads(scope[0]) != [account, stack, readiness.PROFILE_SHA]:
            raise ValueError('Wrong study scope/profile')
        rows = db.execute('''SELECT action_id,day,persona,plan,status,request_id,principal_id,native_event_id
            FROM actions WHERE day>=? AND day<=? ORDER BY day,action_id LIMIT 20001''', (start, end)).fetchall()
        db.rollback()
    if len(rows) > 20000:
        raise ValueError('Ledger bound exceeded')
    return [dict(row) for row in rows]


def _dates(start, end):
    current = date.fromisoformat(start)
    while current.isoformat() <= end:
        yield current.isoformat()
        current += timedelta(days=1)


def _ingested_by_cutoff(db, account, native_event_id, cutoff):
    """'available' | 'not_yet_ingested' | 'invalid_ingestion_time' | 'missing' for one native receipt."""
    found = db.execute("SELECT ingested_at FROM events WHERE source='aws_cloudtrail' AND source_account_id=? "
                       "AND event_id=?", (account, native_event_id)).fetchall()
    if len(found) != 1:
        return 'missing'
    try:
        ingested = instant(found[0][0])
    except (ValueError, TypeError):
        return 'invalid_ingestion_time'
    return 'available' if ingested <= cutoff else 'not_yet_ingested'


def persona_day_coverage(ledger, database, account, stack, end, cutoff):
    """Per (local day, persona) coverage from history start to `end` inclusive, at one UTC cut-off."""
    cutoff = utc_cutoff(cutoff)
    today = cutoff.astimezone(MALAYSIA).date().isoformat()
    start = POLICY['history_start_local']
    excluded = set(POLICY['excluded_dates_local'])
    commissioning, case_rows, rows = Counter(), Counter(), []
    for row in ledger_rows(ledger, account, stack, start, end):
        if row['day'] in excluded:  # partitioned before any ordinary-plan validation
            case_rows[row['day'], row['persona']] += 1
        elif json.loads(row['plan']).get('purpose') == COMMISSIONING:
            commissioning[row['day'], row['persona']] += 1
        else:
            rows.append(row)
    actual = {row['action_id']: row for row in rows}
    if len(actual) != len(rows):
        raise ValueError('Duplicate ledger action')
    native_counts = Counter(row['native_event_id'] for row in rows if row['native_event_id'])
    expected = {}
    for day in _dates(start, end):
        if day not in excluded:
            expected.update(planned_actions(day, account, stack))
    if set(actual) - set(expected):
        raise ValueError('Unexpected ledger action outside the frozen plan')
    days = {(d, p): {'day': d, 'persona': p, 'planned': 0, 'verified': 0, 'missing': 0, 'missed': 0,
                     'unresolved': 0, 'not_yet_ingested': 0, 'verified_native_event_ids': []}
            for d in _dates(start, end) for p in PERSONAS}
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        for action_id, planned in expected.items():
            cell = days[planned['day'], planned['persona']]
            cell['planned'] += 1
            row = actual.get(action_id)
            if row is None:
                cell['missing'] += 1
                continue
            plan = json.loads(row['plan'])
            if row['day'] != planned['day'] or row['persona'] != planned['persona'] or any(plan.get(f) != planned[f] for f in FIELDS):
                raise ValueError('Stored action differs from the frozen plan')
            if row['status'] == 'missed' and not row['request_id'] and not row['native_event_id']:
                cell['missed'] += 1
                continue
            availability = (_ingested_by_cutoff(db, account, row['native_event_id'], cutoff)
                            if row['status'] == 'provider_verified' and row['native_event_id'] else 'missing')
            if availability == 'not_yet_ingested':
                cell['not_yet_ingested'] += 1
            elif (availability == 'available' and native_counts[row['native_event_id']] == 1
                  and readiness.native_matches(db, row, planned, account, stack, cutoff)):
                cell['verified'] += 1
                cell['verified_native_event_ids'].append(row['native_event_id'])
            else:
                cell['unresolved'] += 1
        db.rollback()
    for cell in days.values():
        cell['verified_native_event_ids'].sort()
        cell['commissioning_actions'] = commissioning[cell['day'], cell['persona']]
        cell['case_actions'] = case_rows[cell['day'], cell['persona']]
        if cell['day'] in excluded:
            cell['status'] = 'excluded_case_date'
        elif cell['commissioning_actions']:
            cell['status'] = 'excluded_commissioning'
        elif cell['day'] >= today:
            cell['status'] = 'not_closed'
        elif cell['planned'] == 0:
            cell['status'] = 'planned_idle'
        elif (cell['verified'] * 10 >= cell['planned'] * 9 and cell['unresolved'] == 0
              and cell['not_yet_ingested'] == 0):
            cell['status'] = 'usable'
        else:
            cell['status'] = 'incomplete'
    return sorted(days.values(), key=lambda c: (c['day'], c['persona']))


def persona_account_keys(database, account, stack, cutoff):
    """({persona: valid account key}, diagnostics) from verified assumed-role ARNs ingested by the cut-off.

    Null, malformed or non-native keys never map; a persona with only such rows is reported unavailable.
    One persona on two valid keys is ambiguous and raises."""
    validate_scope(account, stack)
    cutoff = utc_cutoff(cutoff)
    patterns = {p: f'arn:aws:sts::{account}:assumed-role/{stack}-{p}/argus-{p}' for p in PERSONAS}
    found, invalid_keys, late = {p: set() for p in PERSONAS}, Counter(), Counter()
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        for key, metadata, ingested_at in db.execute(
                "SELECT account_key, metadata, ingested_at FROM events WHERE source='aws_cloudtrail' "
                "AND source_account_id=?", (account,)):
            try:
                identity = json.loads(metadata).get('userIdentity', {})
                arn = identity.get('arn')
            except (ValueError, TypeError, AttributeError):
                continue
            persona = next((p for p, value in patterns.items() if arn == value), None)
            if persona is None or identity.get('type') != 'AssumedRole':
                continue
            try:
                if instant(ingested_at) > cutoff:
                    late[persona] += 1
                    continue
            except (ValueError, TypeError):
                late[persona] += 1
                continue
            if not isinstance(key, str) or not ACCOUNT_KEY.fullmatch(key):
                invalid_keys[persona] += 1
                continue
            found[persona].add(key)
    if any(len(keys) > 1 for keys in found.values()):
        raise ValueError('A persona maps to more than one live account key')
    mapping = {persona: next(iter(keys)) for persona, keys in found.items() if keys}
    diagnostics = {'unavailable_personas': sorted(set(PERSONAS) - set(mapping)),
                   'invalid_key_rows': dict(invalid_keys), 'late_or_unparseable_rows': dict(late)}
    return mapping, diagnostics


def accepted(coverage, persona_keys):
    """{(account_key, day): cell} for mapped persona accounts; only 'usable' days may enter history or be scored."""
    return {(persona_keys[c['persona']], c['day']): c for c in coverage if c['persona'] in persona_keys}
