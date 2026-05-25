"""
investigations.py — SOC analyst investigation records.

Backend is selected automatically:
  • PostgreSQL  — when DATABASE_URL is set (production / HuggingFace Spaces)
  • JSON file   — fallback for local development (data/investigations.json)

Each record is keyed by user_id and stores:
  status, analyst, notes, ai_suggestion, created_at, updated_at, history (list)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.config import BASE_DIR

# ---------------------------------------------------------------------------
# Backend detection (reuses the same env var as event_store)
# ---------------------------------------------------------------------------

_DB_URL: str = os.getenv("DATABASE_URL", "")
_PG: bool    = _DB_URL.startswith(("postgresql://", "postgres://"))
_PH: str     = "%s" if _PG else "?"

VALID_STATUSES = {"Pending", "Under Investigation", "Cleared", "Confirmed Insider"}

# JSON fallback path (local dev only)
INVESTIGATIONS_PATH = BASE_DIR / "data" / "investigations.json"

# ---------------------------------------------------------------------------
# PostgreSQL helpers
# ---------------------------------------------------------------------------

def _pg_conn():
    import psycopg2
    import psycopg2.extras
    return psycopg2.connect(_DB_URL)


def _pg_cursor(con):
    import psycopg2.extras
    return con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _pg_init() -> None:
    """Create the investigations table if it doesn't exist."""
    con = _pg_conn()
    try:
        with con:
            cur = _pg_cursor(con)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS investigations (
                    user_id       TEXT PRIMARY KEY,
                    status        TEXT NOT NULL,
                    analyst       TEXT NOT NULL DEFAULT '',
                    notes         TEXT NOT NULL DEFAULT '',
                    ai_suggestion TEXT,
                    created_at    TEXT NOT NULL,
                    updated_at    TEXT NOT NULL,
                    history       TEXT NOT NULL DEFAULT '[]'
                )
            """)
    finally:
        con.close()


# Call init on module load if using PostgreSQL
if _PG:
    try:
        _pg_init()
    except Exception:
        pass  # Server may not be reachable at import time; init_db() in lifespan handles it


# ---------------------------------------------------------------------------
# JSON file helpers (local dev fallback)
# ---------------------------------------------------------------------------

def _load() -> dict:
    if not INVESTIGATIONS_PATH.exists():
        return {}
    with open(INVESTIGATIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    INVESTIGATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INVESTIGATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Shared utility
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_from_row(row: dict) -> dict:
    """Deserialise history JSON string to list, return clean record dict."""
    r = dict(row)
    h = r.get("history", "[]")
    if isinstance(h, str):
        try:
            r["history"] = json.loads(h)
        except Exception:
            r["history"] = []
    return r


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_investigations_db() -> None:
    """Called from main.py lifespan to ensure the table exists."""
    if _PG:
        _pg_init()


def get(user_id: str) -> Optional[dict]:
    """Return the investigation record for *user_id*, or None if absent."""
    if _PG:
        con = _pg_conn()
        try:
            cur = _pg_cursor(con)
            cur.execute(
                f"SELECT * FROM investigations WHERE user_id = {_PH}",
                (user_id,),
            )
            row = cur.fetchone()
            return _record_from_row(dict(row)) if row else None
        finally:
            con.close()
    else:
        return _load().get(user_id)


def list_all(status: Optional[str] = None) -> list[dict]:
    """
    Return all investigation records, newest-updated first.
    Optionally filter by *status*.
    """
    if _PG:
        con = _pg_conn()
        try:
            cur = _pg_cursor(con)
            if status:
                cur.execute(
                    f"SELECT * FROM investigations WHERE status = {_PH} ORDER BY updated_at DESC",
                    (status,),
                )
            else:
                cur.execute("SELECT * FROM investigations ORDER BY updated_at DESC")
            return [_record_from_row(dict(r)) for r in cur.fetchall()]
        finally:
            con.close()
    else:
        data = _load()
        records = [{"user_id": k, **v} for k, v in data.items()]
        if status:
            records = [r for r in records if r.get("status") == status]
        records.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
        return records


def upsert(user_id: str, status: str, analyst: str, notes: str) -> dict:
    """
    Create or update the investigation record for *user_id*.

    Every change is appended to the record's history list so analysts
    can trace the full decision chain.

    Raises ValueError if *status* is not a recognised value.
    """
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status {status!r}. "
            f"Must be one of: {sorted(VALID_STATUSES)}"
        )

    now = _now()

    if _PG:
        con = _pg_conn()
        try:
            with con:
                cur = _pg_cursor(con)
                # Fetch existing record
                cur.execute(
                    f"SELECT * FROM investigations WHERE user_id = {_PH}",
                    (user_id,),
                )
                existing = cur.fetchone()
                existing = _record_from_row(dict(existing)) if existing else None

                if existing:
                    history = list(existing.get("history", []))
                    history.append({
                        "timestamp": now,
                        "analyst":   analyst,
                        "status":    status,
                        "note":      notes,
                    })
                    created_at = existing.get("created_at", now)
                else:
                    history    = []
                    created_at = now

                cur.execute(
                    f"""
                    INSERT INTO investigations
                        (user_id, status, analyst, notes, created_at, updated_at, history)
                    VALUES ({_PH},{_PH},{_PH},{_PH},{_PH},{_PH},{_PH})
                    ON CONFLICT (user_id) DO UPDATE SET
                        status     = EXCLUDED.status,
                        analyst    = EXCLUDED.analyst,
                        notes      = EXCLUDED.notes,
                        updated_at = EXCLUDED.updated_at,
                        history    = EXCLUDED.history
                    """,
                    (user_id, status, analyst, notes,
                     created_at, now, json.dumps(history)),
                )
            return {
                "user_id":    user_id,
                "status":     status,
                "analyst":    analyst,
                "notes":      notes,
                "created_at": created_at,
                "updated_at": now,
                "history":    history,
            }
        finally:
            con.close()
    else:
        data     = _load()
        existing = data.get(user_id, {})
        history  = list(existing.get("history", []))

        if existing:
            history.append({
                "timestamp": now,
                "analyst":   analyst,
                "status":    status,
                "note":      notes,
            })

        data[user_id] = {
            "status":     status,
            "analyst":    analyst,
            "notes":      notes,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
            "history":    history,
        }
        _save(data)
        return {"user_id": user_id, **data[user_id]}


def save_suggestion(user_id: str, suggestion: str) -> None:
    """
    Attach an AI-generated suggestion to an existing investigation record.
    Creates a minimal Pending record first if none exists.
    """
    now = _now()

    if _PG:
        con = _pg_conn()
        try:
            with con:
                cur = _pg_cursor(con)
                cur.execute(
                    f"""
                    INSERT INTO investigations
                        (user_id, status, analyst, notes, ai_suggestion, created_at, updated_at, history)
                    VALUES ({_PH},'Pending','System','',{_PH},{_PH},{_PH},'[]')
                    ON CONFLICT (user_id) DO UPDATE SET
                        ai_suggestion = EXCLUDED.ai_suggestion,
                        updated_at    = EXCLUDED.updated_at
                    """,
                    (user_id, suggestion, now, now),
                )
        finally:
            con.close()
    else:
        data = _load()
        if user_id not in data:
            data[user_id] = {
                "status":       "Pending",
                "analyst":      "System",
                "notes":        "",
                "created_at":   now,
                "updated_at":   now,
                "history":      [],
                "ai_suggestion": suggestion,
            }
        else:
            data[user_id]["ai_suggestion"] = suggestion
            data[user_id]["updated_at"]    = now
        _save(data)


def delete(user_id: str) -> bool:
    """
    Remove the investigation record for *user_id*.
    Returns True if a record existed and was deleted, False otherwise.
    """
    if _PG:
        con = _pg_conn()
        try:
            with con:
                cur = _pg_cursor(con)
                cur.execute(
                    f"DELETE FROM investigations WHERE user_id = {_PH} RETURNING user_id",
                    (user_id,),
                )
                return cur.fetchone() is not None
        finally:
            con.close()
    else:
        data = _load()
        if user_id not in data:
            return False
        del data[user_id]
        _save(data)
        return True
