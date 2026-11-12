"""Workload group score rule and declaration handling. Temp SQLite only."""
import json

from backend.tests.test_baseline_score import make_db, history, today, DAY
from workspace_next import workload_groups as wg


def test_combine_rule():
    assert wg.combine([('aws', 50)]) == 50                          # single source: max only
    assert wg.combine([('aws', 50), ('aws', 40)]) == 50             # same source twice: no bonus
    assert wg.combine([('aws', 50), ('cf', 30)]) == 60              # two sources >= 30: +10
    assert wg.combine([('aws', 50), ('cf', 29)]) == 50              # second below 30: no bonus
    assert wg.combine([('aws', 95), ('cf', 40)]) == 100             # capped
    assert wg.combine([('aws', None)]) is None


def test_groups_merge_and_unknown_key(tmp_path):
    rows = history() + today(action='Write') + [
        ('b', f'2026-10-{DAY.day - i:02d}T02:00:00Z', 'cloudflare_access', 'Read', 'toy') for i in range(1, 7) for _ in range(4)
    ] + [('b', f'2026-10-{DAY.day:02d}T02:00:00Z', 'cloudflare_access', 'Write', 'toy')] * 4
    db = make_db(tmp_path / 'e.db', rows)
    declaration = tmp_path / 'workload-groups.json'
    declaration.write_text(json.dumps([{'group': 'g1', 'label': 'G1', 'members': ['a', 'b', 'missing']}]))
    out = wg.groups(db, declaration)
    assert out['basis'] == 'declared lab mapping, not identity proof'
    assert out['unknown_members'] == [{'group': 'g1', 'account_key': 'missing'}]  # reported, not a crash
    g = out['groups'][0]
    assert len(g['members']) == 2
    scores = [m['score'] for m in g['members']]
    assert g['group_score'] == min(100, max(scores) + (10 if all(s >= 30 for s in scores) else 0))
    assert any(f.startswith('[cloudflare_access]') for f in g['facts'])
    assert wg.timeline(db, declaration, 'g1')['events'] and wg.timeline(db, declaration, 'nope') is None


def test_new_day_without_member_activity_keeps_latest_scored_day(tmp_path):
    """A later day where only an unrelated account is active must not blank the group to Learning."""
    rows = history() + today() + [('other', f'2026-10-{DAY.day + 1:02d}T02:00:00Z', 'aws_cloudtrail', 'Read', 'toy')]
    db = make_db(tmp_path / 'e.db', rows)
    declaration = tmp_path / 'workload-groups.json'
    declaration.write_text(json.dumps([{'group': 'g1', 'label': 'G1', 'members': ['a']}]))
    g = wg.groups(db, declaration)['groups'][0]
    assert g['day'] == DAY.isoformat()                 # its own latest scored day, not the global latest day
    assert g['group_score'] is not None and g['tier'] != 'Learning'
    assert wg.timeline(db, declaration, 'g1')['day'] == DAY.isoformat()
    pinned = wg.groups(db, declaration, (DAY.replace(day=DAY.day + 1)).isoformat())['groups'][0]
    assert pinned['group_score'] is None and pinned['tier'] == 'No activity'   # explicit day still honoured
