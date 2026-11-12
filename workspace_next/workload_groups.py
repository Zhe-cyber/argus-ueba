"""Cross-cloud workload groups: a DECLARED lab mapping (workload-groups.json), not identity proof.

identity_links.approve() deliberately refuses AWS principals and service tokens, so this module never
writes links; it only reads a declaration and combines the per-account baseline scores of its members.
Generate the file once with: python -m workspace_next.workload_groups --db <copy> --write <json>
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3

from workspace_next import baseline_score as bs, system_accounts

BASIS = 'declared lab mapping, not identity proof'
CROSS_SOURCE_BONUS, BONUS_FLOOR = 10, 30


def _persona_labels():
    """{'persona-02': 'Batch reporter'} from the read-only persona profile file; {} when unreadable."""
    try:
        path = Path(__file__).resolve().parent.parent / 'scripts' / 'persona_profiles_v2.json'
        return {p['id']: p['label'] for p in json.loads(path.read_text(encoding='utf-8'))['personas']}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def _read(groups_path):
    path = Path(groups_path)
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else []


def combine(member_scores):
    """member_scores: [(source, score|None)] -> group score or None. Step-15 rule, fixed."""
    scored = [(s, v) for s, v in member_scores if v is not None]
    if not scored:
        return None
    top = max(v for _, v in scored)
    if len({s for s, v in scored if v >= BONUS_FLOOR}) >= 2:
        top += CROSS_SOURCE_BONUS
    return min(100, top)


def groups(db, groups_path, day=None):
    accounts = bs.load(db)
    day = datetime.strptime(day, '%Y-%m-%d').date() if day else bs.latest_day(db)
    out, unknown, personas = [], [], _persona_labels()
    declared = system_accounts.declared(db)
    scores = dict(bs._scores(db, 'WHERE day=?', (day.isoformat(),))) if day else {}  # stored backend scores
    for g in _read(groups_path):
        members, facts = [], []
        for key in g['members']:
            a = accounts.get(key)
            if a is None:
                unknown.append({'group': g['group'], 'account_key': key})  # reported, never fatal
                continue
            r = scores.get(key) or {'score': None, 'tier': 'No activity', 'facts': []}
            members.append({'account_key': key, 'account_label': a['label'], 'source': a['source'],
                            'score': r['score'], 'tier': r['tier'], 'day': day.isoformat() if day else None,
                            'infrastructure': system_accounts.is_infrastructure(a['label'], a['kind'], a['source'], declared)})
            facts += [f"[{a['source']}] {f}" for f in r['facts']]
        score = combine([(m['source'], m['score']) for m in members])
        out.append({'group': g['group'],
                    'label': f"{personas[g['group']]} ({g['group']})" if g['group'] in personas else g['label'], 'members': members, 'group_score': score,
                    'tier': 'Learning' if score is None else bs.tier(score), 'facts': facts})
    out.sort(key=lambda r: (r['group_score'] is None, -(r['group_score'] or 0)))
    return {'basis': BASIS, 'day': day.isoformat() if day else None, 'groups': out, 'unknown_members': unknown}


def timeline(db, groups_path, group, day=None, limit=200):
    """Merged MYT timeline of one group's member events on one MYT day, newest first."""
    g = next((x for x in _read(groups_path) if x['group'] == group), None)
    if g is None:
        return None
    day = datetime.strptime(day, '%Y-%m-%d').date() if day else bs.latest_day(db)
    labels = {k: bs.load(db).get(k, {}).get('label') for k in g['members']}
    rows = []
    marks = ','.join('?' * len(g['members']))
    with sqlite3.connect(f'file:{Path(db).resolve().as_posix()}?mode=ro', uri=True) as con:
        for key, ts, source, action, resource in con.execute(
                f'SELECT account_key,timestamp,source,action,resource FROM events WHERE account_key IN ({marks})',
                g['members']):
            try:
                when = bs._stamp(ts)
            except (ValueError, TypeError):
                continue
            if when.date() == day:
                rows.append({'time_myt': when.isoformat(), 'account_label': labels[key], 'source': source,
                             'action': action, 'resource': (resource or '')[:160]})
    rows.sort(key=lambda r: r['time_myt'], reverse=True)
    return {'basis': BASIS, 'group': group, 'day': day.isoformat() if day else None, 'events': rows[:limit],
            'truncated': len(rows) > limit}


def generate(db):
    """Lab declaration: persona-0N AWS role + the Cloudflare service token whose requests hit
    /workloads/persona-0N/ (the path scripts/cloudflare_machine_pilot.py calls), plus the lab GitHub bot."""
    accounts = bs.load(db)
    by_label = {a['label']: k for k, a in accounts.items()}
    tokens = {}
    with sqlite3.connect(f'file:{Path(db).resolve().as_posix()}?mode=ro', uri=True) as con:
        for key, resource in con.execute("SELECT account_key,resource FROM events WHERE source='cloudflare_access' "
                                         "AND account_kind='service_token' AND resource LIKE '%/workloads/persona-0%'"):
            m = re.search(r'/workloads/(persona-0[1-6])/', resource or '')
            if m:
                tokens.setdefault(m.group(1), set()).add(key)
    result = []
    for n in range(1, 7):
        p = f'persona-0{n}'
        members = [k for k in (by_label.get(f'argus-ueba-actors-{p}'),) if k] + sorted(tokens.get(p, ()))
        if len(tokens.get(p, ())) != 1 or len(members) != 2:
            raise SystemExit(f'cannot derive a one-to-one mapping for {p}; stop and escalate')
        result.append({'group': p, 'label': f'Lab workload {p}', 'members': members})
    bots = [k for k, a in accounts.items() if a['source'] == 'github_events' and re.fullmatch(r'argus-workload-lab-.*\[bot\]', a['label'] or '')]
    if len(bots) == 1:
        result.append({'group': 'github-lab-bot', 'label': 'Lab GitHub bot (shared)', 'members': bots})
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--db', required=True)
    ap.add_argument('--write', required=True)
    args = ap.parse_args()
    data = generate(args.db)
    Path(args.write).write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(f'wrote {len(data)} groups')
