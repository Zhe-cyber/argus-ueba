"""Append a consistent read-only live snapshot to a marked private workspace.

Never rewrites events, findings, identities, scores or analyst records. Conflicting
existing rows fail closed. SQLite backup precedes every destination transaction.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


def refresh(source, target):
    source, target = Path(source).resolve(strict=True), Path(target).resolve(strict=True)
    marker = json.loads((target.parent/'workspace-copy.json').read_text(encoding='utf-8'))
    if source == target or target.name != 'preview.db' or marker != {'not_live': True, 'copy_db': str(target)}:
        raise ValueError('Explicit isolated destination required')
    tables = {}
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True)) as src:
        src.execute('PRAGMA query_only=ON'); src.execute('BEGIN')
        for table in ('events', 'alerts'):
            columns = [r[1] for r in src.execute(f'PRAGMA table_info("{table}")')]
            if not columns or columns[0] != 'id':
                raise ValueError('Unsupported source schema')
            rows = src.execute(f'SELECT * FROM "{table}" ORDER BY id LIMIT 200001').fetchall()
            if len(rows) > 200000:
                raise ValueError('Snapshot row limit exceeded')
            tables[table] = columns, rows
        src.rollback()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = target.parent/f'preview-before-refresh-{stamp}.db'
    inserted = {}
    with closing(sqlite3.connect(target, timeout=10)) as dst:
        with closing(sqlite3.connect(backup)) as saved:
            dst.backup(saved)
        with dst:
            dst.execute('BEGIN IMMEDIATE')
            for table, (columns, rows) in tables.items():
                if columns != [r[1] for r in dst.execute(f'PRAGMA table_info("{table}")')]:
                    raise ValueError('Destination schema differs')
                existing = {r[0]: r for r in dst.execute(f'SELECT * FROM "{table}"')}
                incoming = {r[0]: r for r in rows}
                if any(incoming.get(key) != row for key, row in existing.items()):
                    raise ValueError(f'Existing {table} differ; no overwrite permitted')
                new = [row for row in rows if row[0] not in existing]
                dst.executemany(f'INSERT INTO "{table}" VALUES ({",".join("?" for _ in columns)})', new)
                inserted[table] = len(new)
    result = {'refreshed_at_utc': datetime.now(timezone.utc).isoformat(),
              'inserted': inserted, 'backup': str(backup), 'case_writer_switch': False,
              'identity_links_refreshed': False, 'model_activated': False}
    (target.parent/f'refresh-{stamp}.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True); parser.add_argument('--target', required=True)
    args = parser.parse_args()
    print(json.dumps(refresh(args.source, args.target)))
