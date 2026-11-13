"""Read a SQLite/legacy JSON snapshot; import and roll back on a NEW copy only.

Never switches writers or changes the source database. Output contains private
snapshots and must remain outside Git and public presentation artifacts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import event_store as store
from workspace_next import case_store as cases


def digest_tables(path, exclude_cases=False):
    result = {}
    with sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True) as con:
        names = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for name in names:
            if exclude_cases and (name.startswith('analyst_case') or name=='sqlite_sequence'):
                continue
            quoted='"'+name.replace('"','""')+'"'
            rows=sorted(json.dumps(row,sort_keys=True,default=lambda x:x.hex(),allow_nan=False)
                        for row in con.execute('SELECT * FROM '+quoted))
            result[name]={'rows':len(rows),'sha256':hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
    return result


def backup(source,destination):
    with sqlite3.connect(f'file:{source.as_posix()}?mode=ro',uri=True) as src,sqlite3.connect(destination) as dst:
        src.backup(dst)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def rehearse(source_db,legacy_json,output):
    if store._PG:
        raise ValueError('SQLite rehearsal requires DATABASE_URL=sqlite-local; no PostgreSQL rehearsal claimed')
    source_db=Path(source_db).resolve(strict=True)
    legacy_json=Path(legacy_json).resolve(strict=True)
    output=Path(output).resolve()
    # A fresh directory prevents accidental reuse of an operational database.
    output.mkdir(parents=True,exist_ok=False)
    before=output/'before.db'; working=output/'working.db'
    backup(source_db,before); backup(before,working)
    legacy_bytes=legacy_json.read_bytes()
    records=json.loads(legacy_bytes)
    (output/'legacy-before.json').write_bytes(legacy_bytes)
    baseline=digest_tables(before)
    original_path=store.DB_PATH
    try:
        store.DB_PATH=working
        cases.init_db()
        imported=cases.import_legacy(records,'account-investigations-json-v1')
        require({table: value for table,value in digest_tables(working).items() if table in baseline}==baseline,
                'Existing table content changed during import')
        require(cases.import_legacy(records,'account-investigations-json-v1')==imported,
                'Import retry changed its result')
        for row in imported:
            require(row['legacy']['record']==records[row['legacy']['account']],
                    'Legacy record was not preserved exactly')
        backup(before,working)
        require(digest_tables(working)==baseline,'Rollback differs from backup')
    finally:
        store.DB_PATH=original_path
    receipt={'status':'passed','source_opened_read_only':True,'live_cutover':False,
             'legacy_sha256':hashlib.sha256(legacy_bytes).hexdigest(),
             'legacy_records':len(records),'imported_cases':len(imported),
             'native_tables_unchanged':True,'retry_idempotent':True,
             'rollback_tables_match_backup':True,
             'backup_tables':baseline,
             'limitations':'SQLite copy rehearsal only; concurrent live writer cutover and PostgreSQL remain untested.'}
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db',required=True)
    parser.add_argument('--legacy-json',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=rehearse(args.source_db,args.legacy_json,args.output)
    print(json.dumps({key:result[key] for key in ['status','legacy_records','imported_cases','native_tables_unchanged','rollback_tables_match_backup']}))
