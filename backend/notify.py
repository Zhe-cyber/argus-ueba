"""Analyst notifications: one message per baseline finding (account-day) that reaches High.

Runs as its own loop (a supervisor component), reading findings read-only, so a slow or failing
sender can never block ingest. Sent/pending state lives in its own SQLite table, so a restart never
resends. Findings already High when the notifier first starts are recorded as skipped, not sent.
Messages mask account numbers, emails and IP addresses. Sender from config: outbox (default, a
local JSONL file), telegram (HTTPS bot API) or email (smtplib, STARTTLS). The credential is read
from a file the owner creates (path in config) and is never logged; failures record the error kind
only and are retried with back-off.

  python -m backend.notify loop --config data/live/ops/ops.json
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
import time

SOURCES = (  # (table, account column, day expression); tolerates a missing table
    # L8: the backend scorer writes every baseline finding here (details.day = MYT day); the pre-L8 copy-only
    # workspace_baseline_alerts table is retired (live_mirror.prepare_copy adopts and renames it), so it is not read.
    ('alerts', 'user_id', "coalesce(json_extract(details,'$.day'), substr(created_at,1,10))", "alert_type='baseline_risk' AND severity='High'"),
)
MAX_BACKOFF = 3600


def mask(text):
    text = re.sub(r'\b[^\s@]+@([^\s@]+\.[^\s@]+)\b', lambda m: '***@' + m.group(1), text)
    text = re.sub(r'\b\d{8}(\d{4})\b', r'********\1', text)
    return re.sub(r'\b\d{1,3}(\.\d{1,3}){3}\b', '<ip>', text)


def high_findings(db_paths):
    found = {}
    for path in db_paths:
        path = Path(path)
        if not path.is_file():
            continue
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
            for table, account, day, where in SOURCES:
                try:
                    rows = db.execute(f"SELECT {account}, {day}, title, details FROM {table} WHERE {where}").fetchall()
                except sqlite3.OperationalError:  # table not present in this store
                    continue
                for user, when, title, details in rows:
                    try:
                        score = json.loads(details or '{}').get('score')
                    except ValueError:
                        score = None
                    found.setdefault(f'{user}|{when}', {'account': user, 'day': when, 'title': title, 'score': score})
    return found


def message(finding):
    score = f" (score {finding['score']})" if finding.get('score') is not None else ''
    return mask(f"Argus: baseline risk High{score} for account {finding['account']} on {finding['day']} (MYT). "
                "Review it in the workspace work queue.")


class Notifier:
    def __init__(self, state_db, sender, clock=lambda: datetime.now(timezone.utc)):
        self.path, self.sender, self.clock = Path(state_db), sender, clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('''CREATE TABLE IF NOT EXISTS notifications(finding_key TEXT PRIMARY KEY, message TEXT NOT NULL,
                          status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_attempt_utc TEXT,
                          last_error TEXT, first_seen_utc TEXT NOT NULL, sent_utc TEXT)''')
            db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)')

    def scan(self, db_paths):
        now = self.clock().isoformat()
        findings = high_findings(db_paths)
        with closing(sqlite3.connect(self.path)) as db, db:
            first = db.execute("SELECT value FROM meta WHERE key='started'").fetchone() is None
            for key, finding in findings.items():
                db.execute('INSERT OR IGNORE INTO notifications(finding_key,message,status,next_attempt_utc,first_seen_utc) VALUES(?,?,?,?,?)',
                           (key, message(finding), 'skipped_before_start' if first else 'pending', now, now))
            db.execute("INSERT OR IGNORE INTO meta VALUES('started', ?)", (now,))

    def deliver(self):
        now = self.clock()
        sent = failed = 0
        with closing(sqlite3.connect(self.path)) as db:
            due = db.execute("SELECT finding_key, message, attempts FROM notifications WHERE status='pending' AND next_attempt_utc<=?",
                             (now.isoformat(),)).fetchall()
            for key, text, attempts in due:
                try:
                    self.sender(text)
                except Exception as error:  # kind only: messages could carry credentials or addresses
                    with db:
                        db.execute('UPDATE notifications SET attempts=?, next_attempt_utc=?, last_error=? WHERE finding_key=?',
                                   (attempts + 1, (now + timedelta(seconds=min(MAX_BACKOFF, 60 * 2 ** attempts))).isoformat(),
                                    type(error).__name__, key))
                    failed += 1
                    continue
                with db:
                    db.execute("UPDATE notifications SET status='sent', attempts=?, sent_utc=?, last_error=NULL WHERE finding_key=?",
                               (attempts + 1, now.isoformat(), key))
                sent += 1
        return {'sent': sent, 'failed': failed}


# ---- senders -----------------------------------------------------------------------------------

def outbox_sender(path):
    path = Path(path)

    def send(text):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as out:
            out.write(json.dumps({'at_utc': datetime.now(timezone.utc).isoformat(), 'text': text}) + '\n')
    return send


def _credential(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def telegram_sender(credential_file, chat_id, post=None):
    def send(text):
        import requests
        token = _credential(credential_file)['bot_token']
        response = (post or requests.post)(f'https://api.telegram.org/bot{token}/sendMessage',
                                           json={'chat_id': chat_id, 'text': text}, timeout=20)
        if response.status_code != 200:
            raise RuntimeError('telegram_http_' + str(response.status_code))
    return send


def email_sender(credential_file, host, port, sender, recipient, smtp=None):
    def send(text):
        import smtplib
        from email.message import EmailMessage
        cred = _credential(credential_file)
        msg = EmailMessage()
        msg['Subject'], msg['From'], msg['To'] = 'Argus: High baseline risk', sender, recipient
        msg.set_content(text)
        with (smtp or smtplib.SMTP)(host, port, timeout=20) as server:
            server.starttls()
            server.login(cred['username'], cred['password'])
            server.send_message(msg)
    return send


def sender_from_config(cfg, root):
    n = cfg.get('notify', {})
    path = lambda value: Path(value) if Path(value).is_absolute() else Path(root) / value  # noqa: E731
    kind = n.get('sender', 'outbox')
    if kind == 'telegram':
        return telegram_sender(path(n['credential_file']), n['telegram_chat_id'])
    if kind == 'email':
        e = n['email']
        return email_sender(path(n['credential_file']), e['host'], int(e.get('port', 587)), e['from'], e['to'])
    if kind != 'outbox':
        raise ValueError('notify.sender must be outbox, telegram or email')
    return outbox_sender(path(n.get('outbox_file', 'data/live/ops/notify-outbox.jsonl')))


def main(argv=None):
    from scripts import ops_collect
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=['once', 'loop'])
    parser.add_argument('--config', required=True, type=Path)
    args = parser.parse_args(argv)
    cfg = ops_collect.load_config(args.config)
    workspace = cfg.get('supervisor', {}).get('workspace_dir')
    sources = [cfg['live_state_dir'] / 'events.db'] + ([ops_collect._path(workspace) / 'preview.db'] if workspace else [])
    notifier = Notifier(cfg['status_dir'] / 'notify.db', sender_from_config(cfg, ops_collect.ROOT))

    def once():
        notifier.scan(sources)
        return notifier.deliver()
    if args.mode == 'once':
        print(json.dumps(once()))
        return 0
    ops_collect.loop(once, cfg.get('notify', {}).get('interval_seconds', 60))


if __name__ == '__main__':
    raise SystemExit(main())
