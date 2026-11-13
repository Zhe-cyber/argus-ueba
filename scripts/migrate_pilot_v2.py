"""Explicit pre-collection migration. Run only while both owned tasks are stopped.

No provider calls; preserves every action, receipt, run and polling timestamp.
The caller must separately verify/update the Windows task expiry before restart.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import local_pilot as pilot


def migrate_scope(db, account, stack):
    """Only the original verified commissioning probe may predate v2."""
    old = json.dumps([account, stack, pilot.LEGACY_PROFILE_SHA], separators=(',', ':'))
    new = json.dumps([account, stack, pilot.PROFILE_SHA], separators=(',', ':'))
    expected_id = hashlib.sha256(f'{pilot.LEGACY_PROFILE_SHA}|commissioning-v1|{account}|{stack}'.encode()).hexdigest()
    db.execute('BEGIN IMMEDIATE')
    try:
        rows = db.execute('SELECT action_id,day,status,plan,native_event_id FROM actions').fetchall()
        runs = db.execute('SELECT day,reserved_calls FROM runs').fetchall()
        if (len(rows) != 1 or rows[0][:3] != (expected_id, '2026-10-28', 'provider_verified')
                or not rows[0][4] or runs != [('2026-10-28', 5)]):
            raise ValueError('Migration requires exactly the original verified probe and five-call run; no ordinary history')
        row = json.loads(rows[0][3])
        if row.get('purpose') != 'commissioning_exclude_from_baseline' or row.get('ordinal') != 0:
            raise ValueError('Unexpected commissioning plan')
        db.execute('CREATE TABLE IF NOT EXISTS scope_migrations (old_contract TEXT PRIMARY KEY, new_contract TEXT NOT NULL, at_utc TEXT NOT NULL, reason TEXT NOT NULL)')
        current = db.execute('SELECT contract FROM scope WHERE id=1').fetchone()
        if current == (new,):
            if db.execute('SELECT new_contract FROM scope_migrations WHERE old_contract=?', (old,)).fetchone() != (new,):
                raise ValueError('Unrecorded scope change')
        elif current == (old,):
            db.execute('INSERT INTO scope_migrations VALUES(?,?,?,?)',
                       (old, new, datetime.now(timezone.utc).isoformat(),
                        'User approved daily machine-workload cadence before ordinary collection; final sign-off 15 November'))
            db.execute('UPDATE scope SET contract=? WHERE id=1', (new,))
        else:
            raise ValueError('Unexpected ledger scope')
        db.commit()
    except Exception:
        db.rollback()
        raise


def migrate(config_path):
    config_path = Path(config_path).resolve()
    cfg = json.loads(config_path.read_text())
    if (cfg.get('schema') != 'argus_local_pilot_v1' or Path(cfg['source_root']).resolve() != ROOT
            or cfg.get('end_local') != '2026-11-24' or cfg.get('actor_start') != '2026-10-29'):
        raise ValueError('Expected original source-pinned local pilot config')
    # This is a deliberate new source release, not an automatic pin refresh.
    if pilot.sha(ROOT / 'scripts/persona_profiles_v1.json') != pilot.LEGACY_PROFILE_SHA:
        raise ValueError('Frozen v1 changed')
    if pilot.sha(ROOT / 'scripts/persona_profiles_v2.json') != pilot.PROFILE_SHA:
        raise ValueError('Unexpected v2 profile')
    state = Path(cfg['state_dir'])
    if config_path != state.resolve() / 'config.json':
        raise ValueError('Unexpected config path')
    backup = state / 'cadence-v2-backups'
    backup.mkdir(exist_ok=True)
    saved = backup / 'config-v1.json'
    if saved.exists() and json.loads(saved.read_text()) != cfg:
        raise ValueError('Original backup differs; inspect manually')
    if not saved.exists():
        pilot.atomic_json(saved, cfg)
    ledger = Path(cfg['ledger_dir']) / 'ledger.db'
    with sqlite3.connect(ledger) as db:
        snapshot = backup / 'ledger-v1.db'
        if not snapshot.exists():
            with sqlite3.connect(snapshot) as destination:
                db.backup(destination)
        migrate_scope(db, cfg['account_id'], cfg['stack'])
    cfg.update(schema='argus_local_pilot_v2', actor_end='2026-11-13', end_local='2026-11-14',
               source_hashes=pilot.pinned_sources())
    pilot.validate(cfg)
    pilot.atomic_json(config_path, cfg)
    return {'migrated': True, 'original_probe_and_budgets_preserved': True,
            'actor_end': cfg['actor_end'], 'collection_end': cfg['end_local'], 'model_activated': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    print(json.dumps(migrate(parser.parse_args().config)))
