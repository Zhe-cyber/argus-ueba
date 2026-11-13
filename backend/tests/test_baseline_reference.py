"""Algorithm identity for baseline score v1.1 (L7 section 1): replay the stored reference vectors exactly.

Since v1.2 this file asserts the v1.1 VARIANT of the scorer (the sensitive first-access floor disabled), kept as
history; test_baseline_reference_v1_2.py asserts the running method against baseline_reference_v1_2.json.

The vectors were generated from the pre-move scorer (backend/tests/data/generate_baseline_reference.py). A change
in any output is a method change and needs a new version of the evaluation rules, not an edit to this file.
Each case uses the built-in sensitive patterns plus the case's own extra regexes, set explicitly, so the
deployment sensitive-resource file never leaks into a case.
"""
from contextlib import contextmanager
from datetime import date
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile

import pytest

from backend.rarity_scorer import SENSITIVE_PATTERNS
from workspace_next import baseline_score as bs

OUT = Path(__file__).resolve().parent / 'data' / 'baseline_reference_v1_1.json'


@contextmanager
def _patterns(extra, floor=None):
    module = sys.modules[bs.score_day.__module__]  # wherever the scorer lives
    saved = module._SENSITIVE, getattr(module, 'SENSITIVE_FLOOR_SCORE', None)
    module._SENSITIVE = [re.compile(p, re.IGNORECASE) for p in [*SENSITIVE_PATTERNS, *extra]]
    module.SENSITIVE_FLOOR_SCORE = floor  # None = v1.1 variant
    try:
        yield
    finally:
        module._SENSITIVE, module.SENSITIVE_FLOOR_SCORE = saved


def compute(case, floor=None):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / 'ref.db'
        with sqlite3.connect(db) as con:
            con.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, account_key TEXT, account_label TEXT, '
                        'account_kind TEXT, timestamp TEXT, source TEXT, action TEXT, resource TEXT)')
            con.executemany("INSERT INTO events (account_key,account_label,account_kind,timestamp,source,action,resource) "
                            "VALUES ('a','a','role',?,?,?,?)", case['rows'])
        con.close()
        with _patterns(case['extra_sensitive_regex'], floor):
            return bs.score_day(bs.load(db)['a']['days'], date.fromisoformat(case['day']))


CASES = json.loads(OUT.read_text(encoding='utf-8'))['cases'] if OUT.exists() else []


def test_reference_file_is_complete():
    assert len(CASES) >= 40
    tiers = {c['expected']['tier'] for c in CASES}
    assert tiers == {'Learning', 'Low', 'Medium', 'High'}
    signals = {k for c in CASES for k, v in c['expected'].get('signals', {}).items() if v}
    assert signals == {'new_action', 'new_resource', 'unusual_hours', 'volume', 'sensitive_new'}
    assert any(c['expected'].get('signals', {}).get('new_resource', 0) is None for c in CASES)


@pytest.mark.parametrize('case', CASES, ids=[c['name'] for c in CASES])
def test_reference_vector(case):
    assert compute(case) == case['expected']
