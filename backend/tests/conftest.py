"""
conftest.py — shared pytest fixtures for the backend/tests suite.

Isolates the event-store SQLite file so the suite is deterministic
regardless of what a developer's local data/events.db happens to contain
(seeded cloud users from manual /ingest or /admin/seed-live-scores testing).

Root cause (LESSONS.md rule 10): GET /stats and GET /users both merge
CERT-parquet users with cloud users pulled live from event_store.py's
live_scores table. That merge is correct product behaviour (the dashboard
is supposed to show CERT + cloud users together) — the bug was only in the
test suite, which hardcoded N_USERS=25 without accounting for whatever
cloud rows happened to already be on disk.

event_store.py reads its DB_PATH as a module-level global on every call to
_db() (no cached connection, no value captured in a closure at import
time), so redirecting backend.event_store.DB_PATH to a fresh temp file
before the app starts is sufficient to isolate it — no production code
changes needed.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolated_event_store(tmp_path_factory: pytest.TempPathFactory):
    """
    Redirect the event-store SQLite file to a fresh, empty temp path for the
    whole test session.

    Session-scoped + autouse so it is patched in before any module-scoped
    fixture (e.g. test_api.py's `client`) creates the TestClient and fires
    the FastAPI lifespan hook (which calls event_store.init_db() against
    whatever backend.event_store.DB_PATH currently points at).

    Without this, /stats and /users totals silently include cloud users
    accumulated in a developer's real data/events.db from prior manual
    testing or /ingest calls made by this very suite in an earlier run —
    the suite was mutating real, persistent, file-backed state.
    """
    from backend import event_store

    tmp_dir = tmp_path_factory.mktemp("event_store")
    fresh_db_path: Path = tmp_dir / "events.db"

    original_db_path = event_store.DB_PATH
    event_store.DB_PATH = fresh_db_path
    try:
        yield fresh_db_path
    finally:
        event_store.DB_PATH = original_db_path
