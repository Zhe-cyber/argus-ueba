"""
test_api.py — pytest suite for the FastAPI UEBA endpoint layer.

Run:
    pytest backend/tests/ -v

Strategy
--------
We never touch disk.  A module-scoped fixture seeds the DataStore
singleton with deterministic NumPy / pandas data before the TestClient
starts, then patches store.load() to a no-op so the lifespan hook
can't overwrite our mock data.

Known-user IDs are derived from the seeded DataFrame at runtime —
no IDs are hardcoded in the tests.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Import app and store before seeding so module-level code runs first
from backend.main import app
from backend.loader import store

# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

N_USERS = 25  # enough to produce all three risk buckets reliably


def _seed_store() -> None:
    """
    Populate the DataStore singleton with fully deterministic mock data.

    Scores are evenly spaced [0.1, 1.0] so percentile thresholds are
    predictable:
        p90 threshold ≈ scores[-3]   → 2 High-risk users
        p70 threshold ≈ scores[-8]   → 5 Medium-risk users (roughly)
    """
    np.random.seed(0)
    users  = [f"USR{i:03d}" for i in range(N_USERS)]
    scores = np.linspace(0.1, 1.0, N_USERS)          # deterministic ascending

    store.scores_df = pd.DataFrame({
        "user":           users,
        "ae_score":       scores,
        "if_score":       np.linspace(0.05, 0.95, N_USERS),
        "rule_score":     np.linspace(0.08, 0.92, N_USERS),
        "wa_score":       np.linspace(0.06, 0.94, N_USERS),
        "ensemble_score": scores,
        # Last 3 users are confirmed insiders; 3 distinct insider scenarios
        "is_insider":     [1 if i >= N_USERS - 3 else 0 for i in range(N_USERS)],
        "scenario":       [i % 4 for i in range(N_USERS)],
    })
    store.shap_df = pd.DataFrame({
        "user": users,
        **{f"feat_{j}": np.random.uniform(-0.5, 0.5, N_USERS) for j in range(12)},
    })

    store._score_col      = "ae_score"
    store._user_col       = "user"
    store._shap_user_col  = "user"
    store._feature_cols   = [f"feat_{j}" for j in range(12)]

    s = store.scores_df["ae_score"]
    store._high_threshold   = float(s.quantile(0.90))
    store._medium_threshold = float(s.quantile(0.70))
    store.loaded = True


# Seed once at module import — the store is ready before any fixture runs
_seed_store()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """
    Module-scoped TestClient.

    store.load() is patched to a no-op so the FastAPI lifespan hook does not
    attempt disk I/O and does not overwrite the seeded mock data.
    """
    with patch.object(store, "load", side_effect=lambda: None):
        with TestClient(app) as c:
            yield c


@pytest.fixture(scope="module")
def known_user_id() -> str:
    """First user ID from the seeded scores DataFrame — guaranteed to exist."""
    return str(store.scores_df.iloc[0][store._user_col])


@pytest.fixture(scope="module")
def high_risk_user_id() -> str:
    """
    A user ID that is definitively High risk.

    The last row has ae_score == 1.0, always above the p90 threshold.
    """
    return str(store.scores_df.iloc[-1][store._user_col])


@pytest.fixture(scope="module")
def low_risk_user_id() -> str:
    """
    A user ID that is definitively Low risk.

    The first row has ae_score == 0.1, always below the p70 threshold.
    """
    return str(store.scores_df.iloc[0][store._user_col])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRoot:
    def test_root(self, client):
        """GET / returns 200 with version, mode, and users fields."""
        r = client.get("/")
        assert r.status_code == 200
        body = r.json()
        assert "version" in body,    "Missing 'version' field"
        assert "mode"    in body,    "Missing 'mode' field"
        assert "users"   in body,    "Missing 'users' field"
        assert body["version"] == "v4"
        assert body["users"]   == N_USERS
        assert body["mode"] in ("sqlite", "postgres")


class TestGetUsers:
    def test_get_users(self, client):
        """GET /users returns a paginated envelope; each item has ae_score."""
        r = client.get("/users")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["users"], list)
        assert len(body["users"]) > 0
        assert "ae_score" in body["users"][0], "ae_score missing from user summary"

    def test_get_users_pagination(self, client):
        """limit / offset correctly page the results."""
        r_full  = client.get("/users?limit=5&offset=0")
        r_page2 = client.get("/users?limit=5&offset=5")
        assert r_full.status_code  == 200
        assert r_page2.status_code == 200
        ids_p1 = [u["user"] for u in r_full.json()["users"]]
        ids_p2 = [u["user"] for u in r_page2.json()["users"]]
        # Pages must not overlap
        assert not set(ids_p1) & set(ids_p2), "Pages overlap — offset not working"

    def test_get_users_sorted_by_score(self, client):
        """Users must be returned highest ae_score first."""
        r = client.get("/users?limit=10")
        users = r.json()["users"]
        scores = [u["ae_score"] for u in users]
        assert scores == sorted(scores, reverse=True), "Results are not score-sorted"

    def test_get_users_filter_high(self, client):
        """GET /users?risk=High returns only High-risk users."""
        r = client.get("/users?risk=High")
        assert r.status_code == 200
        users = r.json()["users"]
        assert len(users) > 0, "Expected at least one High-risk user"
        assert all(u["risk_level"] == "High" for u in users), (
            "Non-High user in High-filtered results"
        )

    def test_get_users_filter_medium(self, client):
        """GET /users?risk=Medium returns only Medium-risk users."""
        r = client.get("/users?risk=Medium")
        assert r.status_code == 200
        users = r.json()["users"]
        assert len(users) > 0
        assert all(u["risk_level"] == "Medium" for u in users)

    def test_get_users_filter_low(self, client):
        """GET /users?risk=Low returns only Low-risk users."""
        r = client.get("/users?risk=Low")
        assert r.status_code == 200
        users = r.json()["users"]
        assert len(users) > 0
        assert all(u["risk_level"] == "Low" for u in users)

    def test_get_users_invalid_risk_returns_400(self, client):
        """GET /users?risk=CRITICAL returns 400."""
        r = client.get("/users?risk=CRITICAL")
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"

    def test_get_users_summary_schema(self, client, known_user_id):
        """Every user summary contains the full required schema."""
        r = client.get("/users?limit=5")
        for user in r.json()["users"]:
            assert "user"       in user
            assert "ae_score"   in user
            assert "risk_level" in user
            assert "is_insider" in user
            assert "scenario"   in user
            assert user["risk_level"] in ("High", "Medium", "Low")
            assert user["is_insider"] in (0, 1)
            assert user["scenario"]   in (0, 1, 2, 3)


class TestGetUserDetail:
    def test_get_user_detail(self, client, known_user_id):
        """GET /users/{id} returns 200 with all required score fields."""
        r = client.get(f"/users/{known_user_id}")
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        body = r.json()
        for field in (
            "user", "ae_score", "risk_level", "is_insider", "scenario",
            "if_score", "rule_score", "wa_score", "ensemble_score", "top_features",
        ):
            assert field in body, f"Missing field: {field!r}"

    def test_get_user_detail_correct_id(self, client, known_user_id):
        """The returned user.user field matches the requested ID."""
        r = client.get(f"/users/{known_user_id}")
        assert r.json()["user"] == known_user_id

    def test_get_user_detail_top_features_capped_at_5(self, client, known_user_id):
        """top_features must contain at most 5 entries."""
        r = client.get(f"/users/{known_user_id}")
        features = r.json()["top_features"]
        assert isinstance(features, list)
        assert len(features) <= 5, f"Expected ≤ 5 features, got {len(features)}"

    def test_get_user_detail_top_features_schema(self, client, known_user_id):
        """Each top_feature must have feature, shap_value, and direction fields."""
        r = client.get(f"/users/{known_user_id}")
        for feat in r.json()["top_features"]:
            assert "feature"    in feat
            assert "shap_value" in feat
            assert "direction"  in feat
            assert feat["direction"] in ("increases_risk", "decreases_risk")

    def test_get_user_not_found(self, client):
        """GET /users/NOBODY returns 404."""
        r = client.get("/users/NOBODY")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"
        assert "detail" in r.json()

    def test_get_user_high_risk_score_above_threshold(self, client, high_risk_user_id):
        """The High-risk fixture user's score must be at or above the p90 threshold."""
        r = client.get(f"/users/{high_risk_user_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["risk_level"] == "High"
        assert body["ae_score"] >= store._high_threshold


class TestGetUserShap:
    def test_get_user_shap(self, client, known_user_id):
        """GET /users/{id}/shap returns features list and reason string."""
        r = client.get(f"/users/{known_user_id}/shap")
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        body = r.json()
        assert "features" in body, "Missing 'features' field"
        assert "reason"   in body, "Missing 'reason' field"
        assert "user"     in body

    def test_get_user_shap_capped_at_10(self, client, known_user_id):
        """SHAP response must return at most 10 features."""
        r = client.get(f"/users/{known_user_id}/shap")
        features = r.json()["features"]
        assert len(features) <= 10, f"Expected ≤ 10 features, got {len(features)}"

    def test_get_user_shap_feature_schema(self, client, known_user_id):
        """Each feature must have feature, shap_value, and direction fields."""
        r = client.get(f"/users/{known_user_id}/shap")
        for feat in r.json()["features"]:
            assert "feature"    in feat
            assert "shap_value" in feat
            assert "direction"  in feat
            assert feat["direction"] in ("increases_risk", "decreases_risk"), (
                f"Bad direction: {feat['direction']!r}"
            )

    def test_get_user_shap_direction_matches_sign(self, client, known_user_id):
        """direction must be consistent with the sign of shap_value."""
        r = client.get(f"/users/{known_user_id}/shap")
        for feat in r.json()["features"]:
            if feat["shap_value"] > 0:
                assert feat["direction"] == "increases_risk"
            else:
                assert feat["direction"] == "decreases_risk"

    def test_get_user_shap_sorted_by_abs_value(self, client, known_user_id):
        """Features must be sorted by |shap_value| descending."""
        r = client.get(f"/users/{known_user_id}/shap")
        abs_vals = [abs(f["shap_value"]) for f in r.json()["features"]]
        assert abs_vals == sorted(abs_vals, reverse=True), (
            "SHAP features are not sorted by |shap_value| descending"
        )

    def test_get_user_shap_reason_is_string(self, client, known_user_id):
        """reason must be a non-empty string."""
        r = client.get(f"/users/{known_user_id}/shap")
        reason = r.json()["reason"]
        assert isinstance(reason, str)
        assert len(reason) > 0

    def test_get_user_shap_not_found(self, client):
        """GET /users/NOBODY/shap returns 404."""
        r = client.get("/users/NOBODY/shap")
        assert r.status_code == 404


class TestGetStats:
    def test_get_stats(self, client):
        """GET /stats returns 200 with all required fields."""
        r = client.get("/stats")
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        body = r.json()
        for field in ("total_users", "high_risk", "medium_risk", "low_risk", "insiders"):
            assert field in body, f"Missing field: {field!r}"

    def test_get_stats_counts_sum_to_total(self, client):
        """high_risk + medium_risk + low_risk must equal total_users."""
        body = client.get("/stats").json()
        assert (
            body["high_risk"] + body["medium_risk"] + body["low_risk"]
            == body["total_users"]
        ), (
            f"Risk counts {body['high_risk']}+{body['medium_risk']}+"
            f"{body['low_risk']} ≠ total {body['total_users']}"
        )

    def test_get_stats_total_matches_n_users(self, client):
        """total_users must equal the number of rows in the seeded DataFrame."""
        body = client.get("/stats").json()
        assert body["total_users"] == N_USERS

    def test_get_stats_insiders_non_negative(self, client):
        """insiders count must be ≥ 0 and ≤ total_users."""
        body = client.get("/stats").json()
        assert 0 <= body["insiders"] <= body["total_users"]


class TestIngest:
    # ── Sample raw events ──────────────────────────────────────────────────

    AWS_EVENT = {
        "source": "aws_cloudtrail",
        "event": {
            "eventTime":       "2024-03-15T10:23:45Z",
            "userIdentity":    {"userName": "alice", "type": "IAMUser"},
            "eventName":       "GetObject",
            "sourceIPAddress": "203.0.113.42",
            "requestParameters": {"bucketName": "prod-bucket"},
            "eventID":         "abc123",
            "awsRegion":       "us-east-1",
        },
    }

    AZURE_EVENT = {
        "source": "azure_ad",
        "event": {
            "createdDateTime":    "2024-03-15T09:11:22Z",
            "userPrincipalName":  "bob@contoso.com",
            "appDisplayName":     "Microsoft Teams",
            "resourceDisplayName": "Microsoft Teams",
            "ipAddress":          "198.51.100.17",
            "correlationId":      "corr-001",
            "id":                 "evt-uuid-001",
        },
    }

    def test_ingest_aws(self, client):
        """POST /ingest with AWS CloudTrail event returns a valid 8-field NormalizedEvent."""
        r = client.post("/ingest", json=self.AWS_EVENT)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        body = r.json()

        # All 8 unified schema fields must be present
        for field in ("timestamp", "user", "source", "action", "resource",
                      "ip_address", "metadata", "raw"):
            assert field in body, f"Missing field: {field!r}"

        # Values must round-trip correctly from the sample input
        assert body["user"]       == "alice"
        assert body["source"]     == "aws_cloudtrail"
        assert body["action"]     == "GetObject"
        assert body["timestamp"]  == "2024-03-15T10:23:45Z"
        assert body["ip_address"] == "203.0.113.42"
        assert body["resource"]   == "prod-bucket"
        assert isinstance(body["metadata"], dict)
        assert isinstance(body["raw"],      dict)

    def test_ingest_azure(self, client):
        """POST /ingest with Azure AD event returns a valid NormalizedEvent."""
        r = client.post("/ingest", json=self.AZURE_EVENT)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        body = r.json()

        for field in ("timestamp", "user", "source", "action", "resource",
                      "ip_address", "metadata", "raw"):
            assert field in body

        assert body["user"]       == "bob@contoso.com"
        assert body["source"]     == "azure_ad"
        assert body["action"]     == "Microsoft Teams"
        assert body["timestamp"]  == "2024-03-15T09:11:22Z"
        assert body["ip_address"] == "198.51.100.17"

    def test_ingest_cert_logon(self, client):
        """POST /ingest with CERT logon event returns source=cert_logon."""
        payload = {
            "source": "cert_logon",
            "event": {
                "id":       "LOG001",
                "date":     "2024-01-10 08:02:14",
                "user":     "carol",
                "pc":       "WS-CAROL-01",
                "activity": "Logon",
            },
        }
        r = client.post("/ingest", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["source"] == "cert_logon"
        assert body["user"]   == "carol"

    def test_ingest_bad_source(self, client):
        """
        POST /ingest with an unknown source must return an error.

        The IngestRequest Pydantic model validates the source field, so FastAPI
        returns 422 (Unprocessable Entity) before the route handler runs.
        This is the correct HTTP response for a schema-level validation failure
        and is stricter than a plain 400 Bad Request.
        """
        r = client.post("/ingest", json={"source": "unknown", "event": {}})
        # 422 = Pydantic rejects the request body (source not in allowed set)
        assert r.status_code == 422, (
            f"Expected 422 Unprocessable Entity for unknown source, got {r.status_code}"
        )
        detail = r.json()
        assert "detail" in detail   # FastAPI always wraps validation errors

    def test_ingest_missing_event_field(self, client):
        """POST /ingest with no 'event' key returns 422."""
        r = client.post("/ingest", json={"source": "aws_cloudtrail"})
        assert r.status_code == 422

    def test_ingest_raw_preserves_input(self, client):
        """The 'raw' field in the response must contain the original event dict."""
        r = client.post("/ingest", json=self.AWS_EVENT)
        raw = r.json()["raw"]
        assert raw["eventName"]  == "GetObject"
        assert raw["awsRegion"]  == "us-east-1"
