"""R3: Secure session cookie behind the tunnel, and the /api prefix strip. Fixture user, temp files only."""
import pytest

from backend.tests.auth_helpers import PASSWORD, sign_in
from backend.tests.test_auth import workspace  # noqa: F401  shared fixture (temp copy DB, temp users file)


@pytest.fixture
def cloud_env(monkeypatch):
    monkeypatch.setenv('ARGUS_COOKIE_SECURE', '1')
    monkeypatch.setenv('ARGUS_API_PREFIX', '/api')


def login_header(client, users):
    sign_in(client, users)
    return client.post('/auth/login', json={'username': 'fixture-analyst', 'password': PASSWORD}).headers['set-cookie'].lower()


def test_session_cookie_is_secure_httponly_samesite_strict_when_enabled(cloud_env, workspace):
    _, client, users, *_ = workspace
    header = login_header(client, users)
    assert 'secure' in header.replace('samesite', '') and 'httponly' in header and 'samesite=strict' in header


def test_cookie_is_not_secure_by_default(workspace):
    _, client, users, *_ = workspace
    header = login_header(client, users)
    assert 'httponly' in header and 'secure' not in header.replace('samesite', '')


def test_api_prefix_is_stripped_and_auth_still_applies(cloud_env, workspace):
    _, client, users, *_ = workspace
    client.base_url = 'https://testserver'  # a Secure cookie is only sent over https, as behind the tunnel
    assert client.get('/api/health').json() == {'status': 'ok'}
    assert client.get('/health').json() == {'status': 'ok'}
    assert client.get('/api/workspace/status').status_code == 401  # still behind sign-in
    sign_in(client, users)
    assert client.get('/api/workspace/status').json()['mode'] == 'isolated_copy'


def test_no_prefix_configured_means_api_paths_do_not_exist(workspace):
    _, client, users, *_ = workspace
    assert client.get('/api/health').status_code in (401, 404)
