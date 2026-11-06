"""Prepare a fresh private store/frontend copy; no live writer switch."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.rehearse_case_migration import backup


def prepare(source_db,output,legacy=None):
    source_db=Path(source_db).resolve(strict=True)
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    target=output/'preview.db'
    backup(source_db,target)
    (output/'workspace-copy.json').write_text(json.dumps({'not_live':True,'copy_db':str(target)},indent=2),encoding='utf-8')
    from backend import event_store, identity_links
    from workspace_next import case_store
    if event_store._PG:
        raise ValueError('Preview requires DATABASE_URL=sqlite-local')
    original=event_store.DB_PATH
    try:
        event_store.DB_PATH=target
        case_store.init_db(); identity_links.init_db()
        if legacy:
            records=json.loads(Path(legacy).read_text(encoding='utf-8'))
            case_store.import_legacy(records,'account-investigations-json-v1')
    finally:
        event_store.DB_PATH=original
    shutil.copytree(ROOT/'frontend',output/'frontend',ignore=shutil.ignore_patterns('node_modules','.next','.git','.env*'))
    staged=ROOT/'workspace_next'/'frontend'
    shutil.copytree(staged/'pages',output/'frontend'/'pages',dirs_exist_ok=True)
    shutil.copytree(staged/'components',output/'frontend'/'components',dirs_exist_ok=True)
    # The preview navigation must not send users to the old live dashboard routes.
    (output/'frontend'/'pages'/'_app.js').write_text("import '@/styles/globals.css'\nexport default function App({Component,pageProps}) { return <div className=\"min-h-screen bg-slate-100 text-slate-800\"><Component {...pageProps}/></div> }\n",encoding='utf-8')
    return {'prepared':True,'live_cutover':False,'copied_frontend':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--legacy-json')
    args=parser.parse_args()
    print(json.dumps(prepare(args.source_db,args.output,args.legacy_json)))
