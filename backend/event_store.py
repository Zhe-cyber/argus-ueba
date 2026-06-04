"""
event_store.py — Persistent store for normalized events processed via /ingest.

Supports two backends selected automatically:
  • PostgreSQL  — when DATABASE_URL starts with "postgresql://" or "postgres://"
                  (Neon, Supabase, Railway, any standard Postgres)
  • SQLite      — fallback for local development (no env var needed)

Provides:
  - Persistent event log that survives backend restarts
  - Per-user recent-event queries (for the activity feed)
  - Time-windowed feature aggregation (for live scoring)
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator

from backend.config import BASE_DIR

# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

_DB_URL: str = os.getenv("DATABASE_URL", "")
_PG: bool    = _DB_URL.startswith(("postgresql://", "postgres://"))
_PH: str     = "%s" if _PG else "?"   # SQL placeholder character

# SQLite path (used only when _PG is False)
DB_PATH = BASE_DIR / "data" / "events.db"

# DDL differs only in the primary-key column type
_DDL_EVENTS = """
    CREATE TABLE IF NOT EXISTS events (
        id          {pk},
        "user"      TEXT    NOT NULL,
        timestamp   TEXT    NOT NULL,
        source      TEXT    NOT NULL,
        action      TEXT    NOT NULL,
        resource    TEXT    NOT NULL,
        ip_address  TEXT    DEFAULT '',
        metadata    TEXT    DEFAULT '{{}}',
        ingested_at TEXT    NOT NULL
    )
""".format(pk="BIGSERIAL PRIMARY KEY" if _PG else "INTEGER PRIMARY KEY AUTOINCREMENT")

_DDL_LIVE_SCORES = """
    CREATE TABLE IF NOT EXISTS live_scores (
        user_id     TEXT PRIMARY KEY,
        ae_live     REAL    DEFAULT 0.0,
        rule_live   REAL    DEFAULT 0.0,
        rarity      REAL    DEFAULT 0.0,
        event_count INTEGER DEFAULT 0,
        updated_at  TEXT    NOT NULL
    )
"""

# Per-feature attribution for cloud users (seeded offline from the cloud AE).
# Lets cloud-only users show a SHAP-style breakdown + AI suggestion context.
_DDL_CLOUD_SHAP = """
    CREATE TABLE IF NOT EXISTS cloud_shap (
        user_id       TEXT PRIMARY KEY,
        features_json TEXT NOT NULL,
        reason        TEXT DEFAULT '',
        updated_at    TEXT NOT NULL
    )
"""

# Aggregate function for comma-separated distinct values
_GROUP_CONCAT = "STRING_AGG(DISTINCT source, ',')" if _PG else "GROUP_CONCAT(DISTINCT source)"


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

@contextmanager
def _db() -> Generator:
    """
    Context manager that yields an open connection.
    Commits on clean exit, rolls back on exception, always closes.
    """
    if _PG:
        import psycopg2
        import psycopg2.extras
        con = psycopg2.connect(_DB_URL)
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


def _cursor(con):
    """Return a dict-friendly cursor for whichever backend is active."""
    if _PG:
        import psycopg2.extras
        return con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return con.cursor()


def _rows(cur) -> list[dict]:
    """Normalise fetchall() results to list[dict] for both backends."""
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Schema init (called once at startup)
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables and indices if they don't exist."""
    with _db() as con:
        cur = _cursor(con)
        cur.execute(_DDL_EVENTS)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ev_user ON events(\"user\")")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ev_ts   ON events(ingested_at)")
        cur.execute(_DDL_LIVE_SCORES)
        cur.execute(_DDL_CLOUD_SHAP)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def insert_event(event: dict[str, Any]) -> None:
    """Persist one normalized event."""
    with _db() as con:
        cur = _cursor(con)
        cur.execute(
            f"""
            INSERT INTO events
                ("user", timestamp, source, action, resource, ip_address, metadata, ingested_at)
            VALUES ({_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH})
            """,
            (
                str(event.get("user", "")),
                str(event.get("timestamp", "")),
                str(event.get("source", "")),
                str(event.get("action", "")),
                str(event.get("resource", "")),
                str(event.get("ip_address", "")),
                json.dumps(event.get("metadata", {})),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_user_events(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return the most recent *limit* events for *user_id*, newest first.

    Selects only the display columns (no metadata) — suitable for the
    activity-feed endpoint (LiveEvent model).
    """
    with _db() as con:
        cur = _cursor(con)
        cur.execute(
            f"""
            SELECT id, "user", timestamp, source, action, resource, ip_address, ingested_at
            FROM events
            WHERE "user" = {_PH}
            ORDER BY ingested_at DESC
            LIMIT {_PH}
            """,
            (str(user_id), limit),
        )
        return _rows(cur)


def get_user_events_full(user_id: str, limit: int = 500) -> list[dict[str, Any]]:
    """Return the most recent *limit* events including the metadata column.

    Used by the rarity scorer (geo_rarity needs metadata.country) and any
    other scoring path that needs the full event payload.
    """
    with _db() as con:
        cur = _cursor(con)
        cur.execute(
            f"""
            SELECT * FROM events
            WHERE "user" = {_PH}
            ORDER BY ingested_at DESC
            LIMIT {_PH}
            """,
            (str(user_id), limit),
        )
        rows = _rows(cur)
    # Parse metadata JSON string → dict so callers get a consistent type
    for row in rows:
        if isinstance(row.get("metadata"), str):
            try:
                row["metadata"] = json.loads(row["metadata"])
            except Exception:
                row["metadata"] = {}
    return rows


def get_user_events_window(user_id: str, hours: int = 24) -> list[dict[str, Any]]:
    """Return all events for *user_id* in the last *hours* hours (for live scoring)."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with _db() as con:
        cur = _cursor(con)
        cur.execute(
            f"""
            SELECT * FROM events
            WHERE "user" = {_PH} AND ingested_at >= {_PH}
            ORDER BY ingested_at DESC
            """,
            (str(user_id), since),
        )
        return _rows(cur)


def get_total_event_count(user_id: str) -> int:
    """Return the total number of stored events for *user_id*."""
    with _db() as con:
        cur = _cursor(con)
        cur.execute(
            f'SELECT COUNT(*) AS cnt FROM events WHERE "user" = {_PH}',
            (str(user_id),),
        )
        row = cur.fetchone()
    if row is None:
        return 0
    return int(dict(row).get("cnt", 0))


def delete_event_store_user(user_id: str) -> int:
    """Delete a single user's events and live score. Returns events removed."""
    with _db() as con:
        cur = _cursor(con)
        cur.execute(f'DELETE FROM events WHERE "user" = {_PH}', (str(user_id),))
        removed = cur.rowcount or 0
        cur.execute(f'DELETE FROM live_scores WHERE user_id = {_PH}', (str(user_id),))
        con.commit()
    return int(removed)


def purge_all_live() -> int:
    """Wipe ALL event-store rows and live scores (CERT parquet data untouched).

    Returns the number of event rows removed. Use to clear accumulated test /
    demo ingestions before a clean demo run.
    """
    with _db() as con:
        cur = _cursor(con)
        cur.execute("SELECT COUNT(*) AS cnt FROM events")
        before = int(dict(cur.fetchone()).get("cnt", 0))
        cur.execute("DELETE FROM events")
        cur.execute("DELETE FROM live_scores")
        con.commit()
    return before


def list_event_store_users() -> list[dict[str, Any]]:
    """
    Return one row per distinct user in the event store.

    Each row contains:
      - user        : user ID string
      - event_count : total stored events
      - sources     : comma-separated distinct sources (e.g. 'aws_cloudtrail,azure_ad')
      - last_seen   : ISO timestamp of the most recent ingestion
    """
    with _db() as con:
        cur = _cursor(con)
        cur.execute(
            f"""
            SELECT
                "user",
                COUNT(*)                       AS event_count,
                {_GROUP_CONCAT}                AS sources,
                MAX(ingested_at)               AS last_seen
            FROM events
            GROUP BY "user"
            ORDER BY event_count DESC
            """
        )
        return _rows(cur)


# ---------------------------------------------------------------------------
# Live score persistence
# ---------------------------------------------------------------------------

def upsert_live_score(
    user_id: str,
    ae_live: float,
    rule_live: float,
    rarity: float,
    event_count: int,
) -> None:
    """
    Insert or update the live score record for *user_id*.

    Uses INSERT … ON CONFLICT … DO UPDATE which works in both
    SQLite ≥3.24 (2018) and PostgreSQL.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _db() as con:
        cur = _cursor(con)
        cur.execute(
            f"""
            INSERT INTO live_scores (user_id, ae_live, rule_live, rarity, event_count, updated_at)
            VALUES ({_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH})
            ON CONFLICT (user_id) DO UPDATE SET
                ae_live     = EXCLUDED.ae_live,
                rule_live   = EXCLUDED.rule_live,
                rarity      = EXCLUDED.rarity,
                event_count = EXCLUDED.event_count,
                updated_at  = EXCLUDED.updated_at
            """,
            (str(user_id), float(ae_live), float(rule_live),
             float(rarity), int(event_count), now),
        )


def get_live_score(user_id: str) -> dict[str, Any] | None:
    """
    Return the live score record for *user_id*, or None if not found.

    Returns a dict with keys: user_id, ae_live, rule_live, rarity,
    event_count, updated_at.
    """
    with _db() as con:
        cur = _cursor(con)
        cur.execute(
            f"SELECT * FROM live_scores WHERE user_id = {_PH}",
            (str(user_id),),
        )
        rows = _rows(cur)
    return rows[0] if rows else None


def get_all_live_scores() -> list[dict[str, Any]]:
    """Return all rows from live_scores, ordered by rarity desc."""
    with _db() as con:
        cur = _cursor(con)
        cur.execute("SELECT * FROM live_scores ORDER BY rarity DESC")
        return _rows(cur)


def upsert_cloud_shap(user_id: str, features_json: str, reason: str = "") -> None:
    """Insert or update the cloud SHAP attribution for *user_id*."""
    now = datetime.now(timezone.utc).isoformat()
    with _db() as con:
        cur = _cursor(con)
        cur.execute(
            f"""
            INSERT INTO cloud_shap (user_id, features_json, reason, updated_at)
            VALUES ({_PH}, {_PH}, {_PH}, {_PH})
            ON CONFLICT (user_id) DO UPDATE SET
                features_json = EXCLUDED.features_json,
                reason        = EXCLUDED.reason,
                updated_at    = EXCLUDED.updated_at
            """,
            (str(user_id), features_json, reason, now),
        )


def get_cloud_shap(user_id: str) -> dict[str, Any] | None:
    """Return the cloud SHAP record for *user_id*, or None if not found."""
    with _db() as con:
        cur = _cursor(con)
        cur.execute(
            f"SELECT * FROM cloud_shap WHERE user_id = {_PH}",
            (str(user_id),),
        )
        rows = _rows(cur)
    return rows[0] if rows else None
