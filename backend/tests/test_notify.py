"""Notifications: temp stores, outbox and fake senders only. No network, no real credentials."""
from datetime import datetime, timedelta, timezone
import json
import re
import sqlite3
from types import SimpleNamespace

from backend import notify

ACCOUNT = '123456789012'


def store(path, rows):
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, user_id TEXT, alert_type TEXT, severity TEXT, title TEXT, details TEXT, created_at TEXT)')
        for user, severity, day in rows:
            db.execute("INSERT INTO alerts(user_id,alert_type,severity,title,details,created_at) VALUES(?,?,?,?,?,?)",
                       (user, 'baseline_risk', severity, 'Baseline risk', json.dumps({'day': day, 'score': 72}), day + 'T10:00:00+00:00'))


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 20, 2, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def started(tmp_path, sender, clock=None):
    """A notifier that has completed its first (backlog-skipping) scan on an empty store."""
    n = notify.Notifier(tmp_path / 'notify.db', sender, clock or Clock())
    n.scan([tmp_path / 'events.db'])
    return n


def test_one_message_per_high_finding_and_none_for_medium(tmp_path):
    out = tmp_path / 'outbox.jsonl'
    n = started(tmp_path, notify.outbox_sender(out))
    store(tmp_path / 'events.db', [(f'arn:aws:iam::{ACCOUNT}:role/p02', 'High', '2026-11-20'),
                                   ('alice@example.com', 'Medium', '2026-11-20')])
    n.scan([tmp_path / 'events.db']); assert n.deliver() == {'sent': 1, 'failed': 0}
    store(tmp_path / 'events.db', [(f'arn:aws:iam::{ACCOUNT}:role/p02', 'High', '2026-11-20')])  # same account-day again
    n.scan([tmp_path / 'events.db']); assert n.deliver() == {'sent': 0, 'failed': 0}
    lines = out.read_text(encoding='utf-8').splitlines()
    assert len(lines) == 1 and 'High' in lines[0] and '2026-11-20' in lines[0]


def test_no_resend_after_restart(tmp_path):
    out = tmp_path / 'outbox.jsonl'
    n = started(tmp_path, notify.outbox_sender(out))
    store(tmp_path / 'events.db', [('acct-a', 'High', '2026-11-20')])
    n.scan([tmp_path / 'events.db']); n.deliver()
    restarted = notify.Notifier(tmp_path / 'notify.db', notify.outbox_sender(out), Clock())
    restarted.scan([tmp_path / 'events.db'])
    assert restarted.deliver() == {'sent': 0, 'failed': 0}
    assert len(out.read_text(encoding='utf-8').splitlines()) == 1


def test_backlog_at_first_start_is_not_sent(tmp_path):
    store(tmp_path / 'events.db', [('old', 'High', '2026-11-10')])
    sent = []
    n = notify.Notifier(tmp_path / 'notify.db', sent.append, Clock())
    n.scan([tmp_path / 'events.db'])
    assert n.deliver() == {'sent': 0, 'failed': 0} and sent == []


def test_masking_of_accounts_emails_and_ips():
    text = notify.message({'account': f'arn:aws:iam::{ACCOUNT}:role/x alice@example.com 203.0.113.9', 'day': '2026-11-20', 'score': 70})
    assert ACCOUNT not in text and 'alice@' not in text and '203.0.113.9' not in text
    assert '********9012' in text and '***@example.com' in text and '<ip>' in text
    assert not re.search(r'\d{12}', text)


def test_send_failure_is_retried_later_and_isolated(tmp_path):
    clock, attempts = Clock(), []

    def flaky(text):
        attempts.append(text)
        if len(attempts) == 1:
            raise ConnectionError('secret-token-in-message')

    n = started(tmp_path, flaky, clock)
    store(tmp_path / 'events.db', [('a', 'High', '2026-11-20'), ('b', 'High', '2026-11-20')])
    n.scan([tmp_path / 'events.db'])
    assert n.deliver() == {'sent': 1, 'failed': 1}  # one failure does not stop the other message
    assert n.deliver() == {'sent': 0, 'failed': 0}  # back-off: not retried immediately
    clock.now += timedelta(minutes=2)
    assert n.deliver() == {'sent': 1, 'failed': 0}
    with sqlite3.connect(tmp_path / 'notify.db') as db:
        assert 'secret-token' not in str(db.execute('SELECT * FROM notifications').fetchall())


def test_workspace_copy_findings_are_read_too(tmp_path):
    sent = []
    n = started(tmp_path, sent.append)
    store(tmp_path / 'preview.db', [('acct', 'High', '2026-11-21'), ('acct2', 'Medium', '2026-11-21')])
    n.scan([tmp_path / 'events.db', tmp_path / 'preview.db'])
    assert n.deliver()['sent'] == 1 and len(sent) == 1


def test_reads_findings_written_by_the_backend_baseline_scorer(tmp_path, monkeypatch):
    """L8 coupling: a High account-day scored by backend.baseline_scorer (alerts row with a day column) is notified."""
    from backend import alert_store, event_store as events
    from backend.tests.test_baseline_alerts import put, history_rows, sync
    assert not events._PG, 'Run with DATABASE_URL=sqlite-local'
    monkeypatch.setattr(events, 'DB_PATH', tmp_path / 'events.db')
    events.init_db(); alert_store.init_alerts_db()
    sent = []
    n = started(tmp_path, sent.append)
    put(history_rows() + [('a', '2026-10-10T02:00:00Z', 'Delete', 'secretsmanager/prod-key')] * 40)  # High, as test_baseline_alerts
    sync()
    with sqlite3.connect(tmp_path / 'events.db') as db:
        highs = db.execute("SELECT user_id, day FROM alerts WHERE alert_type='baseline_risk' AND severity='High'").fetchall()
    assert highs
    n.scan([tmp_path / 'events.db'])
    assert n.deliver()['sent'] == len(highs) and all(day in text for (_, day), text in zip(sorted(highs), sorted(sent)))


def test_telegram_and_email_senders_use_the_credential_file_without_exposing_it(tmp_path):
    cred = tmp_path / 'cred.json'
    cred.write_text(json.dumps({'bot_token': 'FAKE-TOKEN', 'username': 'u', 'password': 'FAKE-PASSWORD'}))
    calls = []
    post = lambda url, json, timeout: calls.append((url, json)) or SimpleNamespace(status_code=200)  # noqa: E731
    notify.telegram_sender(cred, '42', post)('hello')
    assert calls[0][0].startswith('https://api.telegram.org/bot') and calls[0][1] == {'chat_id': '42', 'text': 'hello'}
    failing = lambda url, json, timeout: SimpleNamespace(status_code=401)  # noqa: E731
    try:
        notify.telegram_sender(cred, '42', failing)('hello')
    except RuntimeError as error:
        assert 'FAKE-TOKEN' not in str(error)

    class SMTP:
        def __init__(self, host, port, timeout):
            self.log = calls

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            calls.append('tls')

        def login(self, user, password):
            calls.append(('login', user))

        def send_message(self, msg):
            calls.append(('sent', msg['To']))

    notify.email_sender(cred, 'smtp.test', 587, 'argus@test', 'owner@test', SMTP)('hello')
    assert 'tls' in calls and ('login', 'u') in calls and ('sent', 'owner@test') in calls


def test_default_sender_is_the_outbox(tmp_path):
    send = notify.sender_from_config({'notify': {'outbox_file': str(tmp_path / 'o.jsonl')}}, tmp_path)
    send('x')
    assert (tmp_path / 'o.jsonl').is_file()
