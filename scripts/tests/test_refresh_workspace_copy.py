import json
import sqlite3
from pathlib import Path
import pytest
from scripts.refresh_workspace_copy import refresh


def stores(tmp_path):
    source, target = tmp_path/'source.db', tmp_path/'preview.db'
    for path in (source, target):
        with sqlite3.connect(path) as db:
            for table in ('events', 'alerts'):
                db.execute(f'CREATE TABLE {table}(id INTEGER PRIMARY KEY, value TEXT)')
                db.execute(f"INSERT INTO {table} VALUES(1,'original')")
            db.execute('CREATE TABLE analyst_cases(id TEXT, notes TEXT, version INTEGER)')
            db.execute("INSERT INTO analyst_cases VALUES('case','keep this',4)")
    (tmp_path/'workspace-copy.json').write_text(json.dumps({'not_live':True,'copy_db':str(target)}))
    return source,target


def test_append_idempotent_preserves_cases_and_backup_restores(tmp_path):
    source,target=stores(tmp_path)
    with sqlite3.connect(source) as db:
        db.execute("INSERT INTO events VALUES(2,'new event')")
        db.execute("INSERT INTO alerts VALUES(2,'new finding')")
    result=refresh(source,target)
    assert result['inserted']=={'events':1,'alerts':1}
    with sqlite3.connect(target) as db:
        assert db.execute('SELECT * FROM analyst_cases').fetchall()==[('case','keep this',4)]
    assert refresh(source,target)['inserted']=={'events':0,'alerts':0}
    restored=tmp_path/'restored.db'
    with sqlite3.connect(result['backup']) as saved,sqlite3.connect(restored) as dst:
        saved.backup(dst)
        assert dst.execute('SELECT count(*) FROM events').fetchone()[0]==1
        assert dst.execute('SELECT * FROM analyst_cases').fetchall()==[('case','keep this',4)]


def test_conflict_rolls_back_all_tables(tmp_path):
    source,target=stores(tmp_path)
    with sqlite3.connect(source) as db:
        db.execute("INSERT INTO events VALUES(2,'new')")
        db.execute("UPDATE alerts SET value='changed' WHERE id=1")
    with pytest.raises(ValueError,match='Existing alerts differ'):
        refresh(source,target)
    with sqlite3.connect(target) as db:
        assert db.execute('SELECT count(*) FROM events').fetchone()[0]==1


def test_unmarked_or_live_target_refused(tmp_path):
    source,target=stores(tmp_path)
    with pytest.raises(ValueError): refresh(source,source)
    (tmp_path/'workspace-copy.json').write_text('{}')
    with pytest.raises(ValueError): refresh(source,target)
