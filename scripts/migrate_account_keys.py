"""Explicit local additive account-key migration; never changes native event fields."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def native_digest(store):
    fields = 'id,"user",timestamp,source,action,resource,ip_address,metadata,ingested_at,event_id,source_account_id,payload_digest,pipeline_result'
    digest = hashlib.sha256()
    count = 0
    with store._db() as con:
        cur = store._cursor(con); cur.execute('SELECT ' + fields + ' FROM events ORDER BY id')
        for row in store._rows(cur):
            digest.update(json.dumps(row, sort_keys=True, separators=(',', ':')).encode())
            digest.update(b'\n'); count += 1
    return {'count': count, 'sha256': digest.hexdigest()}


def migrate(store, legacy_cases=()):
    before = native_digest(store)
    store.init_db()
    result = store.backfill_account_keys()
    migrated = ambiguous = case_held = 0
    with store._db() as con:
        cur = store._cursor(con); cur.execute('SELECT id,user_id,details FROM alerts')
        alerts = store._rows(cur)
        for alert in alerts:
            from backend.account_identity import is_key
            if is_key(alert['user_id']):
                continue
            keys = store.legacy_account_keys(alert['user_id'])
            if alert['user_id'] in legacy_cases:
                case_held += 1
                continue
            if len(keys) != 1 or None in keys:
                ambiguous += 1
                continue
            details = json.loads(alert['details'] or '{}')
            if not isinstance(details, dict):
                raise ValueError('Invalid alert details; migration stopped')
            details['identity_migration_v1'] = {'legacy_user_id': alert['user_id'],
                                               'basis': 'unique_native_principal'}
            cur.execute(f'UPDATE alerts SET user_id={store._PH},details={store._PH} WHERE id={store._PH}',
                        (next(iter(keys)), json.dumps(details), alert['id']))
            migrated += cur.rowcount
    after = native_digest(store)
    if before != after:
        raise RuntimeError('Original event evidence changed; stop release and restore backup')
    return {'events': result, 'alerts_mapped': migrated, 'alerts_ambiguous': ambiguous,
            'alerts_held_for_legacy_case': case_held, 'native_evidence_unchanged': before == after,
            'native_evidence': after}


def migrate_case_references(cases, store):
    """Rename only one-to-one case keys; preserve every record value verbatim."""
    from collections import Counter
    from backend.account_identity import is_key
    candidates = {}
    for label in cases:
        if is_key(label):
            continue
        keys = store.legacy_account_keys(label)
        if len(keys) == 1 and None not in keys:
            candidates[label] = next(iter(keys))
    counts = Counter(candidates.values())
    result, mappings = dict(cases), {}
    for old, new in candidates.items():
        if counts[new] != 1 or new in cases:
            continue
        result[new] = result.pop(old)
        mappings[old] = new
    return result, mappings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--migrate-unique-cases', action='store_true')
    args = parser.parse_args()
    state = Path(args.state_dir).resolve(); out = Path(args.out).resolve()
    if not (state / 'events.db').is_file() or out.exists() or not out.is_relative_to(ROOT / 'data'):
        parser.error('Require existing local state and a new private report below checkout data')
    out.parent.mkdir(parents=True, exist_ok=True)
    os.environ['DATABASE_URL'] = 'sqlite-local'
    from backend import event_store as store
    if store._PG:
        raise ValueError('Local SQLite only')
    store.DB_PATH = state / 'events.db'
    cases = json.loads((state / 'investigations.json').read_text()) if (state / 'investigations.json').is_file() else {}
    case_mappings = {}
    if args.migrate_unique_cases:
        store.init_db(); store.backfill_account_keys()
        revised, case_mappings = migrate_case_references(cases, store)
        if case_mappings:
            # The release requires a pre-migration backup; retain another exact case copy here.
            backup = out.with_suffix('.cases-before.json')
            with backup.open('x', encoding='utf-8') as handle:
                json.dump(cases, handle, indent=2)
            temp = state / 'investigations.account-key-migration.tmp'
            with temp.open('x', encoding='utf-8') as handle:
                json.dump(revised, handle, indent=2)
            os.replace(temp, state / 'investigations.json')
            cases = revised
    result = migrate(store, cases)
    result['cases_mapped'] = len(case_mappings)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
