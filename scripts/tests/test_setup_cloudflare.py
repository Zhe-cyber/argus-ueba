"""Safety checks for cloud provisioning; no real credentials or network."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from setup_cloudflare import APP_NAME, NAME, SetupError, provision

EMAIL = "reviewer@example.com"


class FakeAPI:
    def __init__(self, *, collision=False, denied=False, wrong_policy=False):
        self.calls = []
        self.collision = collision
        self.denied = denied
        self.wrong_policy = wrong_policy

    def all(self, path):
        self.calls.append(("GET", path, None))
        return [{"id": NAME}] if self.collision and path == "workers/scripts" else []

    def call(self, method, path, body=None, content_type=None):
        self.calls.append((method, path, body))
        if path == "workers/subdomain":
            if self.denied:
                raise SetupError("HTTP 403")
            return {"subdomain": "test-account"}
        if path == "access/apps":
            assert body["name"] == APP_NAME
            assert body["policies"][0]["include"] == [{"email": {"email": EMAIL}}]
            return {"id": "test-app"}
        if path == "access/apps/test-app/policies":
            return [{"decision": "allow", "include": (
                [{"everyone": {}}] if self.wrong_policy else [{"email": {"email": EMAIL}}]
            )}]
        return {}


def test_default_is_read_only():
    api = FakeAPI()
    assert provision(api, EMAIL)["changes"] == 0
    assert all(method == "GET" for method, _, _ in api.calls)


def test_permission_failure_stops_before_mutations():
    api = FakeAPI(denied=True)
    with pytest.raises(SetupError, match="403"):
        provision(api, EMAIL, deploy=True)
    assert all(method == "GET" for method, _, _ in api.calls)


def test_refuses_existing_worker_and_subdomain_rename():
    for api, options in [(FakeAPI(collision=True), {}),
                         (FakeAPI(), {"new_subdomain": "different"})]:
        with pytest.raises(SetupError):
            provision(api, EMAIL, deploy=True, **options)
        assert all(method == "GET" for method, _, _ in api.calls)


def test_route_enabled_only_after_policy_readback():
    api = FakeAPI()
    result = provision(api, EMAIL, deploy=True)
    assert result["login_evidence"] == "pending user sign-in"
    assert api.calls[-2][:2] == ("GET", "access/apps/test-app/policies")
    assert api.calls[-1] == ("POST", f"workers/scripts/{NAME}/subdomain",
                             {"enabled": True, "previews_enabled": False})
    upload = next(body for method, path, body in api.calls if method == "PUT")
    assert b'"ALLOWED_EMAIL"' in upload and b"ctx.access.getIdentity" in upload


def test_wrong_policy_never_enables_route():
    api = FakeAPI(wrong_policy=True)
    with pytest.raises(SetupError, match="read-back"):
        provision(api, EMAIL, deploy=True)
    assert not any(isinstance(body, dict) and body.get("enabled")
                   for _, _, body in api.calls)
