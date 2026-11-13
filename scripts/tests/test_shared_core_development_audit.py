import hashlib
from scripts.audit_shared_core_development import audit


def row(day, path='/namespace/file', uid='test'):
    return {'time': day + 'T12:00:00Z', 'uidType': 'name', 'uid': uid,
            'params': {'path': path}}


def test_prior_active_days_not_events_or_calendar_days():
    user = hashlib.sha256(b'clue-7119953:test').hexdigest()
    rows = [row('2017-07-07')] * 20 + [row(d) for d in
            ['2017-07-09', '2017-07-11', '2017-07-13']]
    result = audit(rows, [user])
    assert result['coverage']['fit'] == {'observed_account_days': 1,
                                       'eligible_by_k': {'3': 1, '5': 0, '7': 0}}


def test_later_dates_and_unselected_accounts_do_not_change_audit():
    user = hashlib.sha256(b'clue-7119953:test').hexdigest()
    original = [row('2017-07-13')]
    assert audit(original, [user]) == audit(original + [row('2017-08-11'),
           row('2017-07-13', uid='other')], [user])


def test_namespace_counts_are_fitting_only_and_coarsen_paths():
    user = hashlib.sha256(b'clue-7119953:test').hexdigest()
    result = audit([row('2017-07-13', '/same/a'), row('2017-07-13', '/same/b'),
                    row('2017-07-27', '/different/c')], [user])
    namespace = result['fitting_namespace']
    assert namespace['distinct_paths'] == 2
    assert namespace['distinct_top_level_namespaces'] == 1
    assert namespace['counts']['fitting_events'] == 2
