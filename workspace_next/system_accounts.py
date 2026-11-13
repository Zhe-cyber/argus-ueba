"""Display context only: which accounts are monitoring infrastructure rather than workloads or users.

Never changes a score, tier or alert. Rules: provider service principals (account_kind 'service'),
AWS service-linked roles (label AWSServiceRole*), and labels declared in system-accounts.json
next to the copy DB ({"basis": ..., "labels": [...]}). A missing or unreadable file means only the first two rules apply.
"""
import json
from pathlib import Path

FILE = 'system-accounts.json'
_CACHE = {}


def declared(db):
    """Declared infrastructure labels for the copy DB's folder (cached per file version)."""
    path = Path(db).resolve().parent / FILE
    try:
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if key not in _CACHE:
            _CACHE.clear()
            _CACHE[key] = frozenset(x for x in json.loads(path.read_text(encoding='utf-8-sig'))['labels'] if isinstance(x, str))
        return _CACHE[key]
    except (OSError, ValueError, KeyError, TypeError):
        return frozenset()


def is_infrastructure(account_label, account_kind, source=None, labels=frozenset()):
    label = account_label or ''
    return account_kind == 'service' or label.startswith('AWSServiceRole') or label in labels
