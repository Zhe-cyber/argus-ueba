from datetime import datetime, timezone

import pytest

from scripts import b1_acceptance_check as b1

NOW = datetime(2026, 11, 5, 4, 0, tzinfo=timezone.utc)
SRC = lambda s: {'source': s, 'latest_observed_in_scan': '2026-11-05T03:00:00Z', 'collector': {'status': 'recent'}}


def api(findings=(), accounts=(), mode='live', sources=b1.SOURCES):
    data = {'/workspace/status': {'mode': mode, 'live_cutover': mode == 'live'},
            '/workspace/overview': {'operations_captured_at': '2026-11-04T03:00:00+00:00'},
            '/workspace/connections': {'sources': [SRC(s) for s in sources]},
            '/findings?limit=100&status=All': {'findings': list(findings)},
            '/findings?limit=100&status=All&category=observation': {'findings': []},
            '/cases?limit=100': {'cases': []}, '/workspace/accounts': list(accounts), '/workspace/people': []}
    return data.__getitem__


def result(rows, test):
    return next(r for r in rows if r[0] == test)


def test_clean_live_workspace_passes():
    rows = b1.check(api(findings=[{'id': 1, 'origin': 'rule', 'display_title': 'First-seen action', 'title': 'raw 123456789012'}],
                        accounts=[{'account_label': 'AWS root', 'source_account_id': '123456789012'}]), NOW)
    assert [result(rows, t)[1] for t in ('B1.1', 'B1.9', 'B1.10')] == ['PASS'] * 3
    assert len(rows) == 12


LEAKY = [('fired for 123456789012', 'aws_account_id'), ('AROAS3OONXMPHPNFBNMJB:x', 'aws_unique_id'),
         ('a.b@example.com', 'email'), ('from 10.0.0.12', 'ipv4')]


@pytest.mark.parametrize('text,kind', LEAKY)
def test_unmasked_leak_is_located_but_value_never_printed(text, kind):
    rows = b1.check(api(findings=[{'id': 7, 'origin': 'rule', 'display_title': text}]), NOW, mask=lambda t: t)
    evidence = result(rows, 'B1.9')
    assert evidence[1] == 'FAIL' and f'[#7].display_title: {kind}' in evidence[2] and text not in evidence[2]


@pytest.mark.skipif(not __import__('shutil').which('node'), reason='node not installed')
def test_real_presentation_mask_hides_every_leak_kind():
    rows = b1.check(api(findings=[{'id': i, 'origin': 'rule', 'display_title': t} for i, (t, _) in enumerate(LEAKY)]), NOW)
    assert result(rows, 'B1.9')[1] == 'PASS' and 'masks all 4' in result(rows, 'B1.9')[2]


def test_missing_node_falls_back_to_manual():
    def broken(_): raise OSError('no node')
    rows = b1.check(api(findings=[{'id': 1, 'origin': 'rule', 'display_title': 'a@b.com'}]), NOW, mask=broken)
    assert result(rows, 'B1.9')[1] == 'MANUAL'


def test_model_origin_or_risk_tier_fails_activation():
    rows = b1.check(api(findings=[{'id': 2, 'origin': 'model', 'display_title': 'x', 'risk_tier': 'High'}]), NOW)
    assert result(rows, 'B1.10')[1] == 'FAIL'


def test_snapshot_and_missing_source():
    rows = b1.check(api(mode='isolated_copy', sources=b1.SOURCES[:2]), NOW)
    assert result(rows, 'B1.1')[1] == 'FAIL' and 'github_events: missing' in result(rows, 'B1.1')[2]
    assert result(rows, 'B1.11')[1] == 'WARN'


def test_refuses_non_local_api():
    with pytest.raises(ValueError):
        b1.http_get('https://example.com')


class FakeCases:
    """Minimal in-memory case API; `honour_versions=False` simulates a silent overwrite bug."""
    def __init__(self, honour_versions=True):
        self.cases, self.keys, self.honour = {}, {}, honour_versions

    def get(self, path):
        if path.startswith('/findings'):
            return {'findings': [{'id': 5, 'account_label': 'argus-ueba-actors-persona-01'}]}
        return self.cases[path.rsplit('/', 1)[1]]

    def send(self, method, path, body):
        if method == 'POST':
            if body['request_key'] in self.keys:
                return 201, self.cases[self.keys[body['request_key']]]
            cid = f'c{len(self.cases)}'
            links = [{'kind': 'finding', 'target': str(body['finding_id'])}] if 'finding_id' in body else []
            history = [{'action': 'created', 'version': 1}] + [{'action': 'linked', 'version': 2}] * bool(links)
            self.cases[cid] = {'id': cid, 'version': len(history), 'status': 'New', 'notes': '', 'links': links, 'history': history}
            self.keys[body['request_key']] = cid
            return 201, self.cases[cid]
        case = self.cases[path.rsplit('/', 1)[1]]
        if self.honour and body['expected_version'] != case['version']:
            return 409, None
        case.update(body['changes'])
        case['version'] += 1
        case['history'].append({'action': 'updated', 'version': case['version']})
        return 200, case


def test_write_checks_pass_on_versioned_api():
    api = FakeCases()
    assert [r for _, r, _ in b1.write_checks(api.get, api.send)] == ['PASS', 'PASS']


def test_silent_overwrite_fails_b1_7():
    api = FakeCases(honour_versions=False)
    result = dict((t, r) for t, r, _ in b1.write_checks(api.get, api.send))
    assert result['B1.7'] == 'FAIL'
