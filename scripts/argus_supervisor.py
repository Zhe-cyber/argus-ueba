"""Single scheduler for the operational deployment: starts and watches every Argus component.

Components (all from config/ops.json, no hard-coded paths): ingest API, collector loop, persona
loop, workspace mirror, workspace API, notifier, web UI. A child that exits is restarted with exponential
back-off (2, 4, 8 ... capped at 60 s); five exits within ten minutes mark it failed (left stopped,
shown in health.json and the Connections page). health.json is rewritten every 30 s.

  python scripts/argus_supervisor.py --config data/live/ops/ops.json
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import ops_collect  # noqa: E402
from scripts.local_pilot import atomic_json  # noqa: E402

FAIL_LIMIT, FAIL_WINDOW, BACKOFF_CAP, HEALTH_EVERY = 5, 600, 60, 30
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


class Child:
    def __init__(self, name, argv, cwd=ROOT, env=None):
        self.name, self.argv, self.cwd, self.env = name, argv, cwd, env
        self.proc, self.state, self.next_start = None, 'starting', 0.0
        self.exits, self.restarts, self.started_at, self.last_exit_code = deque(), 0, None, None


def step(children, now, spawn):
    """Start due children, notice exits, apply back-off and the failure limit."""
    for c in children:
        if c.state == 'failed':
            continue
        if c.proc is not None and c.proc.poll() is not None:
            c.last_exit_code = c.proc.returncode
            c.proc = None
            c.exits.append(now)
            while c.exits and now - c.exits[0] > FAIL_WINDOW:
                c.exits.popleft()
            if len(c.exits) >= FAIL_LIMIT:
                c.state = 'failed'
                continue
            c.state, c.next_start = 'backoff', now + min(BACKOFF_CAP, 2 ** len(c.exits))
        if c.proc is None and now >= c.next_start:
            if c.started_at is not None:
                c.restarts += 1
            c.proc, c.state, c.started_at = spawn(c), 'running', now


def health(children, now):
    return {'schema': 'argus_supervisor_health_v1', 'at_utc': datetime.fromtimestamp(now, timezone.utc).isoformat(),
            'components': [{'name': c.name, 'state': c.state, 'restarts': c.restarts,
                            'exits_last_10_min': len(c.exits), 'last_exit_code': c.last_exit_code,
                            'running_since_utc': datetime.fromtimestamp(c.started_at, timezone.utc).isoformat()
                            if c.state == 'running' and c.started_at is not None else None} for c in children]}


def spawn_process(child):
    out = open(Path(child.env['ARGUS_LOG_DIR']) / f'{child.name}.log', 'ab')
    try:
        return subprocess.Popen(child.argv, cwd=child.cwd, env=child.env, stdout=out, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    finally:
        out.close()  # the child keeps its own handle


def prepare_workspace(cfg):
    """Workspace copy (preview.db + marker) the mirror refreshes from the operational store."""
    folder = ops_collect.guard_path(cfg, ops_collect._path(cfg['supervisor']['workspace_dir']))
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / 'preview.db'
    if not copy.exists():
        source = cfg['live_state_dir'] / 'events.db'
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(copy) as out:
            src.backup(out)
    marker = folder / 'workspace-copy.json'
    if not marker.exists():
        marker.write_text(json.dumps({'copy_db': str(copy.resolve()), 'not_live': True}), encoding='utf-8')
    return folder


def components(cfg, config_path):
    s = cfg['supervisor']
    python = s.get('python') or sys.executable
    workspace = prepare_workspace(cfg)
    ui = f"http://127.0.0.1:{s['web_ui_port']}"
    logs = cfg['status_dir'] / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    base = {**os.environ, 'DATABASE_URL': 'sqlite-local', 'ARGUS_LOG_DIR': str(logs)}
    auth = cfg.get('auth', {})
    workspace_env = {**base, 'ARGUS_WORKSPACE_COPY_DB': str(workspace / 'preview.db'), 'ARGUS_WORKSPACE_UI_ORIGIN': ui,
                     'ARGUS_SUPERVISOR_HEALTH': str(cfg['status_dir'] / 'health.json')}
    for key, env in (('users_file', 'ARGUS_AUTH_USERS_FILE'), ('secret_file', 'ARGUS_AUTH_SECRET_FILE')):
        if auth.get(key):
            workspace_env[env] = str(ops_collect.guard_path(cfg, ops_collect._path(auth[key])))
    conf = str(config_path)
    result = [
        Child('ingest-api', [python, str(ROOT / 'scripts/ops_collect.py'), 'serve', '--config', conf], env=base),
        Child('collector', [python, str(ROOT / 'scripts/ops_collect.py'), 'loop', '--config', conf], env=base),
        Child('personas', [python, str(ROOT / 'scripts/ops_personas.py'), 'loop', '--config', conf], env=base),
        Child('mirror', [python, '-m', 'workspace_next.live_mirror', '--source', str(cfg['live_state_dir'] / 'events.db'),
                         '--dest', str(workspace / 'preview.db'), '--interval', str(s.get('mirror_interval_seconds', 60))], env=base),
        Child('workspace-api', [python, '-m', 'uvicorn', 'workspace_next.app:create_app', '--factory', '--host', '127.0.0.1',
                                '--port', str(s['workspace_api_port'])], env=workspace_env),
    ]
    result.append(Child('notifier', [python, '-m', 'backend.notify', 'loop', '--config', conf], env=base))
    if s.get('frontend_dir') and s.get('node'):
        result.append(Child('web-ui', [s['node'], 'node_modules/next/dist/bin/next', 'start', '-H', '127.0.0.1',
                                       '-p', str(s['web_ui_port'])], cwd=Path(s['frontend_dir']), env=base))
    return result


def run(children, health_path, spawn=spawn_process, clock=time.time, sleep=time.sleep, until=None):
    last = 0.0
    try:
        while until is None or not until():
            now = clock()
            step(children, now, spawn)
            if now - last >= HEALTH_EVERY:
                atomic_json(health_path, health(children, now))
                last = now
            sleep(1)
    finally:
        for c in children:  # ponytail: children of a killed supervisor are orphaned; a Job object would reap them
            if c.proc is not None and c.proc.poll() is None:
                c.proc.terminate()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--config', required=True, type=Path)
    args = parser.parse_args(argv)
    cfg = ops_collect.load_config(args.config)
    cfg['status_dir'].mkdir(parents=True, exist_ok=True)
    run(components(cfg, args.config.resolve()), cfg['status_dir'] / 'health.json')


if __name__ == '__main__':
    raise SystemExit(main())
