"""R3 cloud deploy: Linux secret loading, portable lock, null AWS profile, cloud_migrate pack/verify, deploy/ files.
Temp folders and fixture values only. Windows-only and Linux-only branches skip on the other platform."""
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
from types import SimpleNamespace

import pytest

from scripts import cloud_migrate, collect_live, linux_compat, ops_collect, ops_personas
from scripts.tests.test_ops_collect import make_config

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / 'deploy'
posix_only = pytest.mark.skipif(os.name == 'nt', reason='Linux branch')


# ---- secrets ----------------------------------------------------------------------------------------------

def stat(mode, uid=1000):
    return SimpleNamespace(st_mode=mode, st_uid=uid)


def test_secret_file_rule_is_owner_and_mode_0600_only():
    linux_compat.check_secret_file(stat(0o100600), 1000)
    for bad in (stat(0o100644), stat(0o100640), stat(0o100700), stat(0o100400), stat(0o100600, uid=0), stat(0o040600)):
        with pytest.raises(PermissionError):
            linux_compat.check_secret_file(bad, 1000)


def test_secret_names_cannot_escape_the_folder(tmp_path):
    for name in ('', '../x', 'a/b', '.hidden', 'a\\b'):
        with pytest.raises(ValueError):
            linux_compat.read_secret(name, base=tmp_path)


@posix_only
def test_secret_file_with_mode_0644_is_refused_and_0600_is_read(tmp_path):
    secret = tmp_path / 'persona-01'
    secret.write_text('  fixture-value\n')
    secret.chmod(0o644)
    with pytest.raises(PermissionError):
        linux_compat.read_secret('persona-01', base=tmp_path)
    secret.chmod(0o600)
    assert linux_compat.read_secret('persona-01', base=tmp_path) == 'fixture-value'


def pilot_config(state):
    (state / 'pilot-config.json').write_text(json.dumps({
        'host': 'argus-machine-lab.test.workers.dev', 'tokens': {'persona-01': {'id': 'tid', 'client_id': 'cid.access'}}}))


@posix_only
def test_persona_loader_reads_the_secret_file_on_linux(tmp_path, monkeypatch):
    state = tmp_path / 'state'
    state.mkdir()
    pilot_config(state)
    secret = tmp_path / 'persona-01'
    secret.write_text(json.dumps({'id': 'tid', 'client_id': 'cid.access', 'client_secret': 'fixture'}))
    secret.chmod(0o600)
    monkeypatch.setattr(linux_compat, 'SECRET_DIR', tmp_path)
    assert ops_personas.cf_loader(state, 'persona-01') == ('argus-machine-lab.test.workers.dev', 'cid.access', 'fixture')
    secret.chmod(0o644)
    with pytest.raises(PermissionError):
        ops_personas.cf_loader(state, 'persona-01')


@pytest.mark.skipif(os.name != 'nt', reason='Windows branch')
def test_windows_persona_loader_still_uses_dpapi(tmp_path, monkeypatch):
    from scripts import github_lab_app
    pilot_config(tmp_path)
    seen = []
    monkeypatch.setattr(github_lab_app, 'load_secret',
                        lambda p: seen.append(Path(p).name) or {'id': 'tid', 'client_id': 'cid.access', 'client_secret': 'fixture'})
    assert ops_personas.cf_loader(tmp_path, 'persona-01')[2] == 'fixture' and seen == ['persona-01.dpapi']


@posix_only
def test_cloudflare_collector_reads_its_api_token_from_the_secret_file(tmp_path, monkeypatch):
    from scripts import setup_cloudflare
    secret = tmp_path / 'cloudflare-api-token'
    secret.write_text('fixture-token')
    secret.chmod(0o600)
    monkeypatch.setattr(linux_compat, 'SECRET_DIR', tmp_path)
    seen = {}

    class Api:
        def __init__(self, account, token):
            seen['token'] = token

        def call(self, *a, **k):
            return []

    monkeypatch.setattr(setup_cloudflare, 'Cloudflare', Api)
    monkeypatch.setattr(collect_live, 'forward', lambda *a, **k: {'malformed': 0, 'retained': 0})
    collect_live.collect_cloudflare(SimpleNamespace(account_id='a' * 32, app_id='x'), None)
    assert seen['token'] == 'fixture-token'


# ---- portable lock ----------------------------------------------------------------------------------------

def test_lock_fails_fast_while_held_and_releases(tmp_path):
    path = tmp_path / 'x.lock'
    with linux_compat.lock(path):
        with pytest.raises(OSError):
            with linux_compat.lock(path):
                pass
    with linux_compat.lock(path):  # free again
        pass


# ---- null AWS profile -------------------------------------------------------------------------------------

def test_null_aws_profile_means_the_default_credential_chain(tmp_path, monkeypatch):
    cfg = make_config(tmp_path)
    cfg['providers']['aws']['profile'] = None
    seen = []
    monkeypatch.setattr(collect_live, 'collect_aws', lambda args, backend: seen.append(args.profile) or {})
    ops_collect.run_aws(cfg, None)
    assert seen == [None]
    cfg['providers']['aws'].pop('profile')
    ops_collect.run_aws(cfg, None)
    assert seen[-1] == 'argus-collector'  # unchanged default when the key is absent


# ---- cloud_migrate ----------------------------------------------------------------------------------------

def build_store(tmp_path):
    """A small operational layout plus its config (WAL-mode databases, like the live store)."""
    live, status, work = tmp_path / 'connected', tmp_path / 'ops', tmp_path / 'workspace'
    ledger, auth, bundle = tmp_path / 'ledger', tmp_path / 'auth', tmp_path / 'bundle-v2'
    for d in (live, status / 'ticks', work, ledger, auth, bundle):
        d.mkdir(parents=True)
    for path, rows in ((live / 'events.db', 5), (work / 'preview.db', 3), (ledger / 'ledger.db', 2)):
        db = sqlite3.connect(path)
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE events(id INTEGER PRIMARY KEY, v TEXT)')
        db.execute('CREATE TABLE noid(k TEXT)')
        db.executemany('INSERT INTO events(v) VALUES(?)', [(f'r{i}',) for i in range(rows)])
        db.commit()
        db.close()
    (ledger / 'ops-ledger.json').write_text('{"schema":"x"}')
    (status / 'ticks' / '2026-11-17-ticks.jsonl').write_text('{"ok":true}\n')
    (auth / 'users.json').write_text('{}')
    (auth / 'session.key').write_text('fixture')
    (work / 'system-accounts.json').write_text('{"labels":[]}')
    (bundle / 'manifest.json').write_text('{"m":1}')
    (bundle / 'model.pt').write_bytes(b'\x00\x01\x02')
    cfg = make_config(tmp_path, live_state_dir=str(live), status_dir=str(status),
                      personas={'enabled': False, 'start_local': '2026-11-16', 'ledger_dir': str(ledger)},
                      supervisor={'workspace_dir': str(work)},
                      auth={'users_file': str(auth / 'users.json'), 'secret_file': str(auth / 'session.key')})
    return cfg, bundle


def install(out, cfg):
    """Stand-in for the owner's copy step: write the packed databases over the configured stores."""
    shutil.copyfile(out / 'events.db', cfg['live_state_dir'] / 'events.db')
    shutil.copyfile(out / 'preview.db', ops_collect._path(cfg['supervisor']['workspace_dir']) / 'preview.db')
    shutil.copyfile(out / 'ledger' / 'ledger.db', cfg['personas']['ledger_dir'] / 'ledger.db')


def test_pack_then_verify_round_trip_and_a_deleted_row_is_caught(tmp_path):
    cfg, bundle = build_store(tmp_path)
    out = tmp_path / 'pack'
    manifest = cloud_migrate.pack(cfg, bundle, out)
    assert manifest['dbs']['events.db']['events'] == {'rows': 5, 'max_id': 5}
    assert manifest['dbs']['events.db']['noid'] == {'rows': 0, 'max_id': None}
    assert 'bundle/model.pt' in manifest['files'] and 'ticks/2026-11-17-ticks.jsonl' in manifest['files']
    assert manifest['method_binding_sha256'] == cloud_migrate.method_sha()
    assert cloud_migrate.verify(out) == []
    assert cloud_migrate.main(['verify', '--pack', str(out)]) == 0
    install(out, cfg)
    assert cloud_migrate.verify(out, cfg, bundle) == []  # installed copies equal the pack
    db = sqlite3.connect(out / 'preview.db')  # one row lost in transfer
    db.execute('DELETE FROM events WHERE id=3')
    db.commit()
    db.close()
    assert any('preview.db' in d for d in cloud_migrate.verify(out))
    assert cloud_migrate.main(['verify', '--pack', str(out)]) == 1


def test_verify_catches_a_changed_file_and_a_missing_installed_store(tmp_path):
    cfg, bundle = build_store(tmp_path)
    out = tmp_path / 'pack'
    cloud_migrate.pack(cfg, bundle, out)
    (bundle / 'model.pt').write_bytes(b'tampered')
    assert any('bundle/model.pt' in d for d in cloud_migrate.verify(out, cfg, bundle))
    (bundle / 'model.pt').write_bytes(b'\x00\x01\x02')
    (tmp_path / 'ledger' / 'ledger.db').unlink()
    assert any('ledger' in d for d in cloud_migrate.verify(out, cfg, bundle))


def edit_cell_same_ids(path):
    db = sqlite3.connect(path)
    db.execute("UPDATE events SET v='tampered' WHERE id=2")
    db.commit()
    db.close()


def test_edited_cell_with_unchanged_ids_and_counts_is_caught_in_pack_and_after_install(tmp_path):
    cfg, bundle = build_store(tmp_path)
    out = tmp_path / 'pack'
    cloud_migrate.pack(cfg, bundle, out)
    install(out, cfg)
    edit_cell_same_ids(cfg['live_state_dir'] / 'events.db')  # installed copy altered
    assert any('events.db' in d for d in cloud_migrate.verify(out, cfg, bundle))
    edit_cell_same_ids(out / 'events.db')  # packed copy altered in transit
    assert cloud_migrate.main(['verify', '--pack', str(out)]) == 1


def test_deleting_a_store_and_its_manifest_entries_is_caught(tmp_path):
    cfg, bundle = build_store(tmp_path)
    out = tmp_path / 'pack'
    cloud_migrate.pack(cfg, bundle, out)
    (out / 'events.db').unlink()
    path = out / cloud_migrate.MANIFEST
    manifest = json.loads(path.read_text())
    for key in ('entries', 'dbs', 'files'):
        manifest[key].pop('events.db')
    path.write_text(json.dumps(manifest))
    assert any('events.db' in d for d in cloud_migrate.verify(out))
    assert cloud_migrate.main(['verify', '--pack', str(out)]) == 1


def test_an_extra_unlisted_file_in_the_pack_is_caught(tmp_path):
    cfg, bundle = build_store(tmp_path)
    out = tmp_path / 'pack'
    cloud_migrate.pack(cfg, bundle, out)
    (out / 'bundle' / 'extra.bin').write_bytes(b'x')
    assert any('extra.bin' in d for d in cloud_migrate.verify(out))
    assert cloud_migrate.main(['verify', '--pack', str(out)]) == 1


def test_symlink_in_a_bundled_directory_is_refused(tmp_path):
    cfg, bundle = build_store(tmp_path)
    outside = tmp_path / 'outside-secret.txt'
    outside.write_text('fixture')
    try:
        (bundle / 'link.txt').symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip('cannot create symlinks without privilege here')
    with pytest.raises(ValueError):
        cloud_migrate.pack(cfg, bundle, tmp_path / 'pack')


def test_pack_refuses_a_used_output_folder_and_leaves_the_source_unchanged(tmp_path):
    cfg, bundle = build_store(tmp_path)
    out = tmp_path / 'pack'
    out.mkdir()
    (out / 'x').write_text('1')
    with pytest.raises(ValueError):
        cloud_migrate.pack(cfg, bundle, out)
    before = cloud_migrate.table_stats(cfg['live_state_dir'] / 'events.db')
    cloud_migrate.pack(cfg, bundle, tmp_path / 'pack2')
    assert cloud_migrate.table_stats(cfg['live_state_dir'] / 'events.db') == before


# ---- deploy/ files ----------------------------------------------------------------------------------------

def test_iam_policy_has_no_wildcard_resource_and_no_iam_writes():
    policy = json.loads((DEPLOY / 'iam-instance-policy.json').read_text())
    for statement in policy['Statement']:
        resources = statement['Resource'] if isinstance(statement['Resource'], list) else [statement['Resource']]
        assert all(r != '*' and '*' not in r.replace('/migrate/<PACK_ID>/*', '') for r in resources), statement['Sid']
        actions = statement['Action'] if isinstance(statement['Action'], list) else [statement['Action']]
        assert not any(a == '*' or a.endswith(':*') or a.startswith('iam:') for a in actions)
    # option A: persona runner uses its own key file, so the instance role cannot assume anything
    assert not any('sts:' in str(s['Action']) for s in policy['Statement'])
    s3 = next(s for s in policy['Statement'] if s['Action'] == 's3:GetObject')
    assert s3['Resource'].endswith('/migrate/<PACK_ID>/*')


def test_tunnel_example_routes_only_the_ui_and_the_workspace_api():
    text = (DEPLOY / 'cloudflared-config.example.yml').read_text()
    services = re.findall(r'^\s*-?\s*service:\s*(\S+)', text, re.M)
    assert services == ['http://127.0.0.1:8017', 'http://127.0.0.1:3013', 'http_status:404']
    assert '8013' not in re.sub(r'^\s*#.*$', '', text, flags=re.M)
    # both routed hostnames fail closed without a valid Access token for this application (security review #6)
    body = re.sub(r'^\s*#.*$', '', text, flags=re.M)
    routes = [r for r in re.split(r'\n  - ', body) if 'hostname:' in r]
    assert len(routes) == 2
    for route in routes:
        assert re.search(r'access:\s*\n\s*required:\s*true\s*\n\s*teamName:\s*\S+\s*\n\s*audTag:\s*\[\S+\]', route), route


def test_linux_ops_example_uses_the_instance_role_and_the_right_ports():
    cfg = json.loads((DEPLOY / 'ops.linux.example.json').read_text())
    assert cfg['schema'] == 'argus_ops_v1' and cfg['providers']['aws']['profile'] is None
    assert cfg['providers']['cloudflare']['app_ids'] == ['<LAB_ACCESS_APP_ID>']  # the Access app's own id never listed
    assert cfg['supervisor']['workspace_api_port'] == 8017 and cfg['supervisor']['web_ui_port'] == 3013
    assert cfg['backend_url'].endswith(':8013')
    assert cfg['live_state_dir'].startswith('/') and cfg['status_dir'].startswith('/')


def test_instance_role_label_marks_it_as_infrastructure(tmp_path):
    from workspace_next import system_accounts as sa
    (tmp_path / sa.FILE).write_text((DEPLOY / 'system-accounts.example.json').read_text())
    labels = sa.declared(tmp_path / 'preview.db')
    assert sa.is_infrastructure('argus-ops-instance', 'role', 'aws_cloudtrail', labels)
    assert not sa.is_infrastructure('argus-ueba-actors-persona-01', 'role', 'aws_cloudtrail', labels)


def test_trust_statement_adds_one_principal_and_the_service_unit_is_gated():
    trust = json.loads((DEPLOY / 'persona-trust-statement.json').read_text())
    assert trust['Action'] == 'sts:AssumeRole' and trust['Principal']['AWS'].endswith(':role/<INSTANCE_ROLE_NAME>')
    unit = (DEPLOY / 'argus.service').read_text()
    assert 'ConditionPathExists=/var/lib/argus/CUTOVER_OK' in unit and 'Restart=always' in unit
    assert 'scripts/argus_supervisor.py' in unit
