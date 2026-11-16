"""Move the operational stores between hosts (laptop <-> cloud server) without a raw file copy.

  python scripts/cloud_migrate.py pack   --config ops.json --bundle <pinned AE v2 bundle dir> --out <new folder>
  python scripts/cloud_migrate.py verify --pack <folder>                                   (transfer intact?)
  python scripts/cloud_migrate.py verify --pack <folder> --config ops.json --bundle <dir>  (installed copies equal?)

pack copies every SQLite file with the backup API (consistent even while the source is in WAL mode), plain files
byte for byte, and writes migrate-manifest.json: per table row count and max(id), sha256 of every other file, and
the sha256 of the baseline method-binding file in this checkout. verify recomputes the same and exits 1 on any
difference. Prints counts and names only, never file contents. Run pack only after the collector has drained.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import ops_collect  # noqa: E402

MANIFEST = 'migrate-manifest.json'
SCHEMA = 'argus_cloud_migrate_v1'
METHOD_FILE = 'config/baseline_method_v1_2.json'
SIDE_FILES = ('system-accounts.json', 'workload-groups.json')  # small workspace settings next to preview.db
SKIP_SUFFIXES = ('-wal', '-shm', '.lock', '.tmp')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def table_stats(path):
    """{table: {'rows', 'max_id'}} for every user table (max_id None when the table has no id column)."""
    uri = Path(path).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as db:
        stats = {}
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            quoted = '"' + name.replace('"', '""') + '"'
            has_id = any(col[1] == 'id' for col in db.execute(f'PRAGMA table_info({quoted})'))
            rows, top = db.execute(f'SELECT count(*), {"max(id)" if has_id else "NULL"} FROM {quoted}').fetchone()
            stats[name] = {'rows': rows, 'max_id': top}
        return stats


def entries(cfg, bundle):
    """(name inside the pack, path on a host, kind) for every store; names are the same on both hosts."""
    s = cfg['supervisor']
    workspace = ops_collect._path(s['workspace_dir'])
    out = [('events.db', cfg['live_state_dir'] / 'events.db', 'db'), ('preview.db', workspace / 'preview.db', 'db'),
           ('ticks', cfg['status_dir'] / ops_collect.TICKS_DIR, 'dir'), ('bundle', Path(bundle), 'dir')]
    auth = cfg.get('auth', {})
    for key, name in (('users_file', 'auth/users.json'), ('secret_file', 'auth/session.key')):
        if auth.get(key):
            out.append((name, ops_collect._path(auth[key]), 'file'))
    if cfg.get('personas', {}).get('ledger_dir'):
        out.append(('ledger', cfg['personas']['ledger_dir'], 'dir'))
    out += [(f'side/{n}', workspace / n, 'file') for n in SIDE_FILES if (workspace / n).is_file()]
    return out


def pack_entries(root):
    """Same entries read back from a pack folder."""
    root = Path(root)
    names = json.loads((root / MANIFEST).read_text(encoding='utf-8'))['entries']
    return [(n, root / n, k) for n, k in names.items()]


def describe(items):
    """{'dbs': {name: table stats}, 'files': {name: sha256}} for the entries; a missing source is an error."""
    dbs, files = {}, {}
    for name, path, kind in items:
        path = Path(path)
        if kind == 'dir':
            if not path.is_dir():
                raise ValueError(f'missing folder: {name}')
            found = [(f'{name}/{p.relative_to(path).as_posix()}', p) for p in sorted(path.rglob('*'))
                     if p.is_file() and not p.name.endswith(SKIP_SUFFIXES)]
        elif path.is_file():
            found = [(name, path)]
        else:
            raise ValueError(f'missing file: {name}')
        for rel, p in found:
            if p.suffix == '.db':
                dbs[rel] = table_stats(p)
            else:
                files[rel] = sha256(p)
    return {'dbs': dbs, 'files': files}


def method_sha():
    return sha256(ROOT / METHOD_FILE)


def differences(expected, actual):
    """Human-readable list of what differs between two describe() results (empty = identical)."""
    bad = []
    for kind in ('dbs', 'files'):
        for name in sorted(set(expected[kind]) | set(actual[kind])):
            if expected[kind].get(name) != actual[kind].get(name):
                bad.append(f'{kind[:-1]} differs or is missing: {name}')
    return bad


def copy_db(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(dest)) as out:
        src.backup(out)


def copy_file(source, dest):
    if Path(source).suffix == '.db':
        copy_db(source, dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)


def pack(cfg, bundle, out):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output folder must be new or empty')
    kinds = {}
    for name, source, kind in entries(cfg, bundle):
        source = Path(source)
        if kind == 'dir':
            if not source.is_dir():
                raise ValueError(f'missing folder: {name}')
            for p in sorted(source.rglob('*')):
                if p.is_file() and not p.name.endswith(SKIP_SUFFIXES):
                    copy_file(p, out / name / p.relative_to(source))
            (out / name).mkdir(parents=True, exist_ok=True)
        elif not source.is_file():
            raise ValueError(f'missing file: {name}')
        else:
            copy_file(source, out / name)
        kinds[name] = kind
    manifest = {'schema': SCHEMA, 'created_utc': datetime.now(timezone.utc).isoformat(), 'entries': kinds,
                'method_binding_sha256': method_sha(), **describe(pack_entries_from(out, kinds))}
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')
    return manifest


def pack_entries_from(root, kinds):
    return [(n, Path(root) / n, k) for n, k in kinds.items()]


def verify(pack_dir, cfg=None, bundle=None):
    """List of differences; [] means the pack (or, with cfg, the installed copies) match the manifest."""
    manifest = json.loads((Path(pack_dir) / MANIFEST).read_text(encoding='utf-8'))
    if manifest.get('schema') != SCHEMA:
        raise ValueError('Unknown manifest schema')
    if cfg is None:
        items, bad = pack_entries(pack_dir), []
    else:
        have = {n: (n, p, k) for n, p, k in entries(cfg, bundle)}
        items = [have[n] for n in manifest['entries'] if n in have]
        bad = [f'not configured or missing on this host: {n}' for n in manifest['entries'] if n not in have]
    try:
        actual = describe(items)
    except ValueError as error:
        return [str(error)]
    bad += differences(manifest, actual)
    if manifest['method_binding_sha256'] != method_sha():
        bad.append('baseline method-binding file differs from this checkout')
    return bad


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=['pack', 'verify'])
    parser.add_argument('--config', type=Path)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--pack', type=Path)
    args = parser.parse_args(argv)
    try:
        cfg = ops_collect.load_config(args.config) if args.config else None
        if args.mode == 'pack':
            if not (cfg and args.bundle and args.out):
                raise ValueError('pack needs --config, --bundle and --out')
            manifest = pack(cfg, args.bundle, args.out)
            print(json.dumps({'status': 'packed', 'databases': {n: {t: v['rows'] for t, v in s.items()} for n, s in manifest['dbs'].items()},
                              'files': len(manifest['files'])}))
            return 0
        if not args.pack or bool(cfg) != bool(args.bundle):
            raise ValueError('verify needs --pack, and --config together with --bundle for the installed copies')
        bad = verify(args.pack, cfg, args.bundle)
        print(json.dumps({'status': 'verified' if not bad else 'differences', 'differences': bad}))
        return 1 if bad else 0
    except Exception as error:  # kind only: messages could carry paths
        print(json.dumps({'status': 'stopped', 'error_kind': type(error).__name__,
                          'detail': str(error) if isinstance(error, ValueError) else ''}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
