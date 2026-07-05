"""
rarity_scorer.py — Source-agnostic rarity flags for live cloud log scoring.

Computes 6 boolean anomaly signals per event using only the 8-field
normalised schema. No training data required — mirrors Microsoft Sentinel's
ActivityInsights architecture and Cloudflare's identity-perimeter model.

Flags
-----
1. first_time_action   True if this (user, action) pair has never been seen
                       in the event store before this event.
2. new_ip              True if this source IP has never appeared for this user.
3. off_hours           True if the event timestamp falls outside Mon–Fri 07:00–19:00
                       UTC (conservative window; catches true after-hours use).
4. high_volume         True if the user has produced more than VOLUME_THRESHOLD
                       events in the past VOLUME_WINDOW_HOURS hours.
5. sensitive_resource  True if the resource path / ARN / object name matches
                       any pattern in SENSITIVE_PATTERNS (case-insensitive).
6. geo_rarity          True if the event's country (from metadata) has never been
                       seen for this user. Only fires when source=cloudflare_access
                       or any source that populates metadata.country.

Usage
-----
    from backend.rarity_scorer import compute_rarity_flags

    flags = compute_rarity_flags(event, recent_events)
    # flags → {"first_time_action": bool, "new_ip": bool, ...}

    score = rarity_score(flags)
    # score → float 0.0–1.0  (fraction of flags that are True)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Number of events in the last N hours that triggers the high-volume flag
VOLUME_THRESHOLD: int = 50
VOLUME_WINDOW_HOURS: int = 1

# Off-hours definition (UTC): flag events outside Mon–Fri 07:00–19:00.
# NOTE: this window (07–19) is intentionally WIDER than the AE feature
# window in feature_extractor.py (_BIZ_START=7, _BIZ_END=18). The AE window
# must stay frozen to match the trained model's feature semantics; the
# rarity flag is a conservative analyst-facing signal and tolerates the
# extra hour. Both are replaced by learned per-user active-hours profiles
# in FYP2 (plan item #4).
OFF_HOURS_START: int = 7   # inclusive
OFF_HOURS_END: int = 19    # exclusive (so 19:00 is off-hours)

# Regex patterns for sensitive resources (case-insensitive match on the
# resource field of the normalised event).  Covers AWS, Azure, GCP, and
# generic on-prem patterns observed in CERT and Cloudflare threat reports.
SENSITIVE_PATTERNS: list[str] = [
    # AWS IAM / secrets
    r"iam",
    r"secretsmanager",
    r"kms",
    r"sts",
    r"ssm",
    # AWS data stores with PII/financial signals
    r"s3.*\b(backup|sensitive|pii|financial|prod|production|confidential)\b",
    r"rds",
    r"dynamodb",
    # Azure sensitive services
    r"keyvault",
    r"microsoft\.keyvault",
    r"microsoft\.authorization",
    r"microsoft\.aad",
    r"passwordprofile",
    r"credential",
    # Generic high-value keywords
    r"password",
    r"secret",
    r"token",
    r"private.?key",
    r"ssh",
    r"vpn",
    r"admin",
    r"root",
    r"sudo",
    r"shadow",
    r"passwd",
    # CERT insider-threat dataset patterns
    r"\.exe$",
    r"usb",
    r"removable",
    r"wikileaks",
    r"jobsite",
]

_COMPILED_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in SENSITIVE_PATTERNS
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_rarity_flags(
    event: dict[str, Any],
    recent_events: list[dict[str, Any]],
) -> dict[str, bool]:
    """
    Compute the 6 rarity flags for a single normalised event.

    Parameters
    ----------
    event : dict
        A normalised event with at least: user, timestamp, action,
        resource, ip_address.
    recent_events : list[dict]
        All stored events for this user (used for first_time_action,
        new_ip, and high_volume).  Cheapest to pass already-fetched
        rows from event_store.get_user_events_window().

    Returns
    -------
    dict[str, bool]
        {
            "first_time_action":  bool,
            "new_ip":             bool,
            "off_hours":          bool,
            "high_volume":        bool,
            "sensitive_resource": bool,
        }
    """
    action   = str(event.get("action",     "")).lower().strip()
    resource = str(event.get("resource",   "")).strip()
    ip       = str(event.get("ip_address", "")).strip()
    ts_raw   = str(event.get("timestamp",  "")).strip()

    metadata = event.get("metadata", {})
    if isinstance(metadata, str):
        import json as _json
        try:
            metadata = _json.loads(metadata)
        except Exception:
            metadata = {}
    country = str(metadata.get("country", "")).strip().upper()

    return {
        "first_time_action":  _flag_first_time_action(action, recent_events),
        "new_ip":             _flag_new_ip(ip, recent_events),
        "off_hours":          _flag_off_hours(ts_raw),
        "high_volume":        _flag_high_volume(recent_events),
        "sensitive_resource": _flag_sensitive_resource(resource),
        "geo_rarity":         _flag_geo_rarity(country, recent_events),
    }


def rarity_score(flags: dict[str, bool]) -> float:
    """
    Aggregate rarity flags into a single score in [0.0, 1.0].

    Each flag is weighted equally; the score is the fraction of flags
    that are True.  A score of 1.0 means all 5 flags fired.
    """
    if not flags:
        return 0.0
    return round(sum(flags.values()) / len(flags), 4)


def rarity_risk_label(score: float) -> str:
    """Map a rarity score to a risk label (mirrors the AE thresholds)."""
    if score >= 0.6:
        return "High"
    if score >= 0.4:
        return "Medium"
    return "Low"


# ---------------------------------------------------------------------------
# Individual flag implementations
# ---------------------------------------------------------------------------

def _flag_first_time_action(
    action: str,
    recent_events: list[dict[str, Any]],
) -> bool:
    """
    True if this action has NEVER appeared in the user's event history.

    Uses the full history (not just the time window) so even a single
    past occurrence suppresses the flag.
    """
    if not action:
        return False
    seen_actions = {
        str(e.get("action", "")).lower().strip()
        for e in recent_events
    }
    return action not in seen_actions


def _flag_new_ip(
    ip: str,
    recent_events: list[dict[str, Any]],
) -> bool:
    """
    True if this IP address has never appeared for this user.

    Skips blank / RFC-1918 loopback addresses (127.x, ::1) since those
    are always 'new' and carry no signal.
    """
    if not ip or ip in ("", "127.0.0.1", "::1", "localhost"):
        return False
    seen_ips = {
        str(e.get("ip_address", "")).strip()
        for e in recent_events
        if e.get("ip_address")
    }
    return ip not in seen_ips


def _flag_off_hours(ts_raw: str) -> bool:
    """
    True if the event falls outside Mon–Fri 07:00–19:00 UTC.

    Accepts ISO-8601 timestamps (with or without timezone).
    Returns False on parse failure so ingestion never crashes.
    """
    if not ts_raw:
        return False
    try:
        # Handle timezone-aware and naive timestamps
        ts_raw_clean = ts_raw.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(ts_raw_clean)
        except ValueError:
            # Try a few fallback formats
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(ts_raw, fmt)
                    break
                except ValueError:
                    continue
            else:
                return False

        # Normalise to UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        # Weekend (Mon=0 … Sun=6)
        if dt.weekday() >= 5:
            return True

        # Outside 07:00–19:00 UTC
        return not (OFF_HOURS_START <= dt.hour < OFF_HOURS_END)

    except Exception:
        return False


def _flag_high_volume(recent_events: list[dict[str, Any]]) -> bool:
    """
    True if the user generated > VOLUME_THRESHOLD events in the last
    VOLUME_WINDOW_HOURS hours (based on ingested_at timestamps).
    """
    return len(recent_events) > VOLUME_THRESHOLD


def _flag_sensitive_resource(resource: str) -> bool:
    """
    True if the resource matches any pattern in SENSITIVE_PATTERNS.
    """
    if not resource:
        return False
    return any(p.search(resource) for p in _COMPILED_PATTERNS)


def _flag_geo_rarity(
    country: str,
    recent_events: list[dict[str, Any]],
) -> bool:
    """
    True if this country code has never appeared in this user's event history.

    Only meaningful when metadata.country is populated (e.g. Cloudflare Access,
    Azure AD with location enrichment). Returns False when country is blank.
    """
    if not country:
        return False
    seen_countries = set()
    for e in recent_events:
        meta = e.get("metadata", {})
        if isinstance(meta, str):
            import json as _json
            try:
                meta = _json.loads(meta)
            except Exception:
                meta = {}
        c = str(meta.get("country", "")).strip().upper()
        if c:
            seen_countries.add(c)
    return country not in seen_countries
