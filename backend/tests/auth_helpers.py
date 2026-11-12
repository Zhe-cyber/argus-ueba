"""Sign tests in through a fixture user kept in a temp users file (never a real account)."""
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from backend import auth

PASSWORD = 'fixture-password-only-for-tests'


def sign_in(client, users_file, name='fixture-analyst', role='analyst'):
    if name not in auth.read_users(users_file):
        auth.add_user(users_file, name, role, PASSWORD)
    client.headers['X-Argus-Request'] = '1'
    response = client.post('/auth/login', json={'username': name, 'password': PASSWORD})
    assert response.status_code == 200, response.text
    return client


@contextmanager
def signed_in_client(app, tmp_path, name='fixture-analyst', role='analyst'):
    """Install auth on a bare app (e.g. one that only mounts case_api.router) and sign in."""
    folder = Path(tmp_path) / 'auth'
    auth.install(app, auth.Auth(folder / 'users.json', folder / 'session.key'))
    with TestClient(app) as client:
        yield sign_in(client, folder / 'users.json', name, role)
