"""B1 acceptance checks (specs/EVALUATION_PLAN.md, part B1). Read-only GETs against a local workspace API.

Automates B1.1, B1.9, B1.10 and B1.11. Lists the remaining B1 tests as manual steps with their pass conditions.
B1.9 is judged on screen text in Presentation mode: the API keeps native IDs by design, so the display fields are
passed through the frontend's own maskText (via node) and must come out clean.
Never prints a leaked value: it reports only where a leak was found.
With --copy-writes it also runs B1.6 (case lifecycle + audit) and B1.7 (stale edit rejected) by writing test cases,
only to a disposable isolated copy: it refuses port 8015 (the demo copy judges see) and any non-isolated API.
Usage: python scripts/b1_acceptance_check.py [--base http://127.0.0.1:8015] [--json out.json] [--copy-writes]
"""
import argparse
from datetime import datetime, timezone
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

SOURCES = ['aws_cloudtrail', 'cloudflare_access', 'github_events']
LEAKS = {'aws_account_id': re.compile(r'(?<!\d)\d{12}(?!\d)'),
         'aws_unique_id': re.compile(r'\b(?:AROA|AIDA|AKIA|ASIA|AGPA)[A-Z0-9]{12,}\b'),
         'email': re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+'),
         'ipv4': re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')}
# Fields the dashboard renders as text; raw keys such as source_account_id are API-only by design.
DISPLAY = {'title', 'display_title', 'account_label', 'display_name', 'owner', 'notes', 'closing_reason'}
MANUAL = {
    'B1.2': 'Normalise: the three sources show the same canonical fields in one view; unsupported events carry a reason.',
    'B1.3': 'Deduplicate: a re-delivered event is not stored twice (event_count unchanged after a replay).',
    'B1.4': 'Identity linking: approve a link; the person timeline shows events from 2+ providers, labelled ownership evidence.',
    'B1.5': 'Findings: a rule finding opens with its evidence; observations are shown separately from findings.',
    'B1.6': 'Case workflow: finding -> evidence -> case -> note -> decision -> closed, with a full audit trail.',
    'B1.7': 'Concurrency: two tabs edit one case; the stale save is rejected and reloaded, never overwritten.',
    'B1.8': 'Model explanation: an account-day shows a raw score with per-feature terms, or a precise "why unscored".',
    'B1.12': 'Research page: the benchmark replay opens read-only and separate from live data.',
}


def http_get(base):
    host = urlsplit(base).hostname
    if host not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('local API only')
    def get(path):
        with urlopen(base.rstrip('/') + path, timeout=20) as r:
            return json.load(r)
    return get


def http_send(base):
    get = http_get(base)
    def send(method, path, body):
        req = Request(base.rstrip('/') + path, json.dumps(body).encode(), {'Content-Type': 'application/json'}, method=method)
        try:
            with urlopen(req, timeout=20) as r:
                return r.status, json.load(r)
        except HTTPError as e:
            return e.code, None
    return get, send


def write_checks(get, send):
    """B1.6 and B1.7 on a disposable copy. Returns result rows; never raises on a failed expectation."""
    actor, tag = 'B1 acceptance test', uuid4().hex[:8]
    rows = get('/findings?limit=100&status=All')['findings']
    finding = next((f for f in rows if 'persona' in (f.get('account_label') or '')), rows[0] if rows else None)
    if finding is None:
        return [('B1.6', 'FAIL', 'no finding to open a case from'), ('B1.7', 'MANUAL', 'needs a case')]
    key = 'b1-6-' + tag
    body = {'actor': actor, 'request_key': key, 'title': f'B1.6 acceptance test {tag}', 'finding_id': finding['id'],
            'reason': 'Acceptance test: finding to case', 'include_account': True}
    code, case = send('POST', '/cases/from-finding', body)
    retry_code, retry = send('POST', '/cases/from-finding', body)  # same request key: must not create a second case
    steps = [f'from-finding {code}', f'retry same key {retry_code}' + (' same case' if retry and case and retry['id'] == case['id'] else ' DIFFERENT')]
    ok = code == 201 and retry and case and retry['id'] == case['id']
    if ok:
        v = case['version']
        c1, case = send('PATCH', f"/cases/{case['id']}", {'actor': actor, 'request_key': key + '-note', 'expected_version': v,
                                                         'changes': {'notes': 'Reviewed evidence; scripted persona activity.'}})
        c2, case = send('PATCH', f"/cases/{case['id']}", {'actor': actor, 'request_key': key + '-close', 'expected_version': v + 1,
                                                         'changes': {'status': 'Closed', 'resolution': 'Expected or authorized activity',
                                                                     'closing_reason': 'Controlled persona workload.'}}) if case else (None, None)
        steps += [f'note {c1}', f'close {c2}']
        final = get(f"/cases/{case['id']}") if case else {}
        actions = [h['action'] for h in final.get('history', [])]
        versions = [h['version'] for h in final.get('history', [])]
        linked = any(l['kind'] == 'finding' and l['target'] == str(finding['id']) for l in final.get('links', []))
        ok = (final.get('status') == 'Closed' and linked and versions == list(range(1, len(versions) + 1))
              and actions[0] == 'created' and len(actions) >= 4)
        steps.append(f"status {final.get('status')}, finding linked {linked}, audit {len(actions)} entries v1..v{versions[-1] if versions else 0}")
    out = [('B1.6', 'PASS' if ok else 'FAIL', f"finding #{finding['id']} -> case -> note -> closed: " + '; '.join(steps))]

    code, case = send('POST', '/cases', {'actor': actor, 'request_key': 'b1-7-' + tag, 'title': f'B1.7 acceptance test {tag}'})
    if code != 201:
        return out + [('B1.7', 'FAIL', f'create {code}')]
    cid, seen = case['id'], case['version']  # both tabs loaded this version
    edit = lambda k, notes: send('PATCH', f'/cases/{cid}', {'actor': actor, 'request_key': f'b1-7-{tag}-{k}',
                                                           'expected_version': seen, 'changes': {'notes': notes}})
    first, _ = edit('a', 'Edit from tab A')
    stale, _ = edit('b', 'Edit from tab B (stale)')
    kept = get(f'/cases/{cid}').get('notes')
    ok = first == 200 and stale == 409 and kept == 'Edit from tab A'
    return out + [('B1.7', 'PASS' if ok else 'FAIL', f'first edit {first}; stale edit {stale} (409 expected); stored notes kept from tab A: {kept == "Edit from tab A"}')]


def age_hours(stamp, now):
    return (now - datetime.fromisoformat(stamp.replace('Z', '+00:00'))).total_seconds() / 3600


MASK_JS = Path(__file__).resolve().parents[1] / 'workspace_next' / 'frontend' / 'lib' / 'presentationPrivacy.mjs'


def node_mask(texts):
    script = (f"import {{maskText}} from {json.dumps(MASK_JS.as_uri())};let s='';"
              "process.stdin.on('data',d=>s+=d).on('end',()=>process.stdout.write(JSON.stringify(JSON.parse(s).map(maskText))))")
    out = subprocess.run(['node', '--input-type=module', '-e', script], input=json.dumps(texts),
                         capture_output=True, text=True, encoding='utf-8', check=True)
    return json.loads(out.stdout)


def leaks_in(text):
    return [name for name, rx in LEAKS.items() if rx.search(text)]


def display_texts(doc, where):
    hits = []
    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == 'title' and 'display_title' in node:
                    continue  # the UI renders display_title instead
                if k in DISPLAY and isinstance(v, str):
                    hits.append((f'{where}{path}.{k}', v))
                else:
                    walk(v, f'{path}.{k}')
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f'{path}[#{v["id"]}]' if isinstance(v, dict) and 'id' in v else f'{path}[{i}]')
    walk(doc, '')
    return hits


def risk_activations(doc, where):
    hits = []
    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == 'risk_tier' and v is not None or k == 'live_activation' and v is True:
                    hits.append(f'{where}{path}.{k}')
                walk(v, f'{path}.{k}')
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f'{path}[{i}]')
    walk(doc, '')
    return hits


def check(get, now=None, mask=node_mask, send=None):
    now = now or datetime.now(timezone.utc)
    status, overview, conn = get('/workspace/status'), get('/workspace/overview'), get('/workspace/connections')
    findings = get('/findings?limit=100&status=All')
    observations = get('/findings?limit=100&status=All&category=observation')
    docs = {'overview': overview, 'findings': findings, 'observations': observations, 'cases': get('/cases?limit=100'),
            'accounts': get('/workspace/accounts'), 'people': get('/workspace/people'), 'connections': conn}
    results = []

    by_source = {s['source']: s for s in conn.get('sources', [])}
    bad = [f'{s}: missing' for s in SOURCES if s not in by_source]
    bad += [f"{s}: collector {by_source[s]['collector']['status']}" for s in SOURCES
            if s in by_source and by_source[s]['collector']['status'] != 'recent']
    newest = {s: f"{age_hours(by_source[s]['latest_observed_in_scan'], now):.1f} h" for s in SOURCES
              if by_source.get(s, {}).get('latest_observed_in_scan')}
    live = status.get('mode') == 'live' or bool(status.get('live_cutover'))
    results.append(('B1.1', 'FAIL' if bad else 'PASS' if live else 'WARN',
                    '; '.join(bad) or f'all 3 collectors recent at capture; newest event age now {newest}'
                    + ('' if live else '; snapshot data, rerun against the live API')))

    texts = [t for name, doc in docs.items() for t in display_texts(doc, name)]
    raw = sum(bool(leaks_in(v)) for _, v in texts)
    capped = [n for n in ('findings', 'observations') if docs[n].get('has_more')]
    note = f'; first 100 only for {capped}' if capped else ''
    try:
        masked = mask([v for _, v in texts])
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        results.append(('B1.9', 'MANUAL', f'masking check unavailable ({type(error).__name__}); {raw} raw display fields carry '
                                          'native IDs; verify on screen with Presentation mode on' + note))
    else:
        leaks = [f'{where}: {",".join(leaks_in(v))}' for (where, _), v in zip(texts, masked) if leaks_in(v)]
        results.append(('B1.9', 'FAIL' if leaks else 'PASS',
                        (f'{len(leaks)} leak(s) after Presentation-mode masking: ' + '; '.join(leaks[:15]) if leaks else
                         f'Presentation mode masks all {raw} display fields that carry native IDs (mode off shows them by design)') + note))

    act = [h for name, doc in docs.items() for h in risk_activations(doc, name)]
    model = [f"finding {f['id']}" for f in findings.get('findings', []) + observations.get('findings', [])
             if f.get('origin') == 'model']
    results.append(('B1.10', 'FAIL' if act or model else 'PASS',
                    '; '.join(act + [f'non-rule origin: {m}' for m in model]) or 'no risk tier, no live activation, rule findings only'))

    captured = overview.get('operations_captured_at')
    if live:
        results.append(('B1.11', 'MANUAL', 'live mode: confirm stale receipts show as stale in the UI'))
    elif not captured:
        results.append(('B1.11', 'FAIL', f"mode {status.get('mode')} but no capture time is exposed"))
    else:
        h = age_hours(captured, now)
        results.append(('B1.11', 'WARN' if h > 24 else 'PASS',
                        f"mode {status.get('mode')}, capture {h:.1f} h old; UI must label it as recorded, not current"))

    automated = {}
    if send:
        automated = {t: (t, r, e) for t, r, e in write_checks(get, send)}
    results += [automated.get(k, (k, 'MANUAL', v)) for k, v in MANUAL.items()]
    return sorted(results, key=lambda r: [int(x) for x in r[0][3:].split('.')])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', default='http://127.0.0.1:8015')
    ap.add_argument('--json')
    ap.add_argument('--copy-writes', action='store_true', help='also run B1.6/B1.7 by writing test cases to a disposable copy')
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    send = None
    if a.copy_writes:
        if urlsplit(a.base).port == 8015:
            sys.exit('Refusing --copy-writes on 8015: that copy is the demo data. Use a disposable copy (e.g. 8016).')
        if http_get(a.base)('/workspace/status').get('mode') != 'isolated_copy':
            sys.exit('Refusing --copy-writes: API is not an isolated copy.')
        send = http_send(a.base)[1]
    rows = check(http_get(a.base), now, send=send)
    print(f'B1 acceptance check, {a.base}, {now.isoformat(timespec="seconds")}\n')
    print('| Test | Result | Evidence |\n|---|---|---|')
    for t, r, e in rows:
        print(f'| {t} | {r} | {e} |')
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump({'base': a.base, 'at_utc': now.isoformat(), 'results': rows}, f, indent=1)
    sys.exit(1 if any(r == 'FAIL' for _, r, _ in rows) else 0)


if __name__ == '__main__':
    main()
