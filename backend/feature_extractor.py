"""
feature_extractor.py — Extract behavioral feature increments from normalized events.

Maps each normalized event to a dict of integer increments that match
the feature names used in the training pipeline (daily_features_v4.parquet).

These increments can be accumulated over a time window to produce the
same behavioral aggregates that feed the AE and LightGBM models.

Feature → source mapping
-------------------------
login_count          cert_logon, aws_cloudtrail, azure_ad
after_hours_count    any source  (outside 07:00–18:00)
files_accessed       cert_file
n_archive_files      cert_file   (.zip .tar .gz .7z .rar …)
n_exe_files          cert_file   (.exe)
n_afterhours_file    cert_file   + after-hours
usb_events           cert_file (removable media), cert_device
has_usb              cert_file (removable media), cert_device  (binary)
n_afterhours_usb     usb events + after-hours
usb_and_file         cert_file with removable media
email_count          cert_email
external_emails      cert_email  (recipient domain ≠ sender domain)
n_bcc_email          cert_email  (BCC field non-empty)
total_attachments    cert_email
n_afterhours_email   cert_email  + after-hours
http_count           cert_http
n_job_site           cert_http   (LinkedIn, Indeed, Glassdoor …)
n_cloud_storage      cert_http   (Dropbox, Google Drive, OneDrive …)
suspicious_http      cert_http   (Pastebin, anonymous file-sharing …)
n_afterhours_http    cert_http   + after-hours
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

# Business hours window (matching training notebook constants)
_BIZ_START = 7
_BIZ_END   = 18

_ARCHIVE_EXTS: frozenset[str] = frozenset({
    ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".tgz", ".tar.gz",
})
_JOB_SITES: frozenset[str] = frozenset({
    "linkedin", "indeed", "glassdoor", "monster", "careerbuilder",
    "ziprecruiter", "seek", "reed", "totaljobs", "jobstreet",
})
_CLOUD_SITES: frozenset[str] = frozenset({
    "dropbox", "drive.google", "onedrive", "box.com",
    "mega.nz", "wetransfer", "sharepoint",
})
_SUSPICIOUS_SITES: frozenset[str] = frozenset({
    "pastebin", "pastecode", "ghostbin", "hastebin",
    "anonfiles", "filebin", "temp.sh",
})


def _is_after_hours(timestamp: str) -> bool:
    """Return True when the event falls outside business hours (07:00–18:00)."""
    try:
        h = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).hour
        return h < _BIZ_START or h >= _BIZ_END
    except Exception:
        return False


def extract(event: dict[str, Any]) -> dict[str, int]:
    """
    Map one normalized event → feature increments (non-zero values only).

    Parameters
    ----------
    event : dict
        A normalized event as returned by normalizer.py (or stored in event_store).
        May have 'metadata' as either a dict or a JSON string.

    Returns
    -------
    dict[str, int]
        Feature name → increment value (always ≥ 1).
        Only features that are non-zero for this event are included.
    """
    source   = str(event.get("source", ""))
    ts       = str(event.get("timestamp", ""))
    resource = str(event.get("resource", "")).lower()
    metadata = event.get("metadata", {})

    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}

    ah = _is_after_hours(ts)
    f: dict[str, int] = {}

    # ── Logon (including Cloudflare Access) ──────────────────────────────
    if source in ("cert_logon", "aws_cloudtrail", "azure_ad", "cloudflare_access"):
        f["login_count"] = 1
        if ah:
            f["after_hours_count"] = 1

    # ── File activity ─────────────────────────────────────────────────────
    if source == "cert_file":
        f["files_accessed"] = 1
        if ah:
            f["n_afterhours_file"] = 1

        # Extension-based sub-categories
        ext = ""
        if "." in resource:
            ext = "." + resource.rsplit(".", 1)[-1]
        if ext in _ARCHIVE_EXTS:
            f["n_archive_files"] = 1
        if ext == ".exe":
            f["n_exe_files"] = 1

        # USB / removable media transfer
        to_usb   = bool(metadata.get("to_removable_media"))
        from_usb = bool(metadata.get("from_removable_media"))
        if to_usb or from_usb:
            f["usb_events"]   = 1
            f["has_usb"]      = 1
            f["usb_and_file"] = 1
            if ah:
                f["n_afterhours_usb"] = 1

    # ── Device (USB connect / disconnect) ─────────────────────────────────
    if source == "cert_device":
        f["usb_events"] = 1
        f["has_usb"]    = 1
        if ah:
            f["n_afterhours_usb"] = 1

    # ── Email ─────────────────────────────────────────────────────────────
    if source == "cert_email":
        f["email_count"] = 1
        if ah:
            f["n_afterhours_email"] = 1

        # External-recipient detection: any To: address in a different domain
        to_list  = metadata.get("to",  [])
        bcc_list = metadata.get("bcc", [])
        if isinstance(to_list,  str): to_list  = [to_list]
        if isinstance(bcc_list, str): bcc_list = [bcc_list]

        sender     = str(metadata.get("from", "@"))
        own_domain = sender.split("@")[-1].lower() if "@" in sender else ""
        if any(
            "@" in addr and addr.split("@")[-1].lower() != own_domain
            for addr in to_list
        ):
            f["external_emails"] = 1

        if bcc_list:
            f["n_bcc_email"] = 1

        attachments = int(metadata.get("attachments", 0) or 0)
        if attachments:
            f["total_attachments"] = attachments

    # ── HTTP / web ─────────────────────────────────────────────────────────
    if source == "cert_http":
        f["http_count"] = 1
        if ah:
            f["n_afterhours_http"] = 1

        if any(s in resource for s in _JOB_SITES):
            f["n_job_site"] = 1
        if any(s in resource for s in _CLOUD_SITES):
            f["n_cloud_storage"] = 1
        if any(s in resource for s in _SUSPICIOUS_SITES):
            f["suspicious_http"] = 1

    return f


# ---------------------------------------------------------------------------
# Aggregate a list of events into cumulative feature totals
# ---------------------------------------------------------------------------

def aggregate(events: list[dict[str, Any]]) -> dict[str, int]:
    """
    Sum feature increments across all *events* in a time window.

    Returns a dict of total counts (same keys as extract()).
    """
    totals: dict[str, int] = {}
    for ev in events:
        for k, v in extract(ev).items():
            totals[k] = totals.get(k, 0) + v
    return totals


# ---------------------------------------------------------------------------
# Rule-based live score  (matches training Cell 11 rule_score weights)
# ---------------------------------------------------------------------------

_RULE_WEIGHTS: dict[str, float] = {
    "usb_events":      0.25,
    "files_accessed":  0.20,
    "has_usb":         0.15,
    "n_archive_files": 0.10,
    "external_emails": 0.10,
    "suspicious_http": 0.10,
    "n_job_site":      0.10,
}

_CAPS: dict[str, int] = {
    "usb_events":      20,
    "files_accessed":  200,
    "has_usb":         1,
    "n_archive_files": 10,
    "external_emails": 30,
    "suspicious_http": 5,
    "n_job_site":      5,
}


def live_score(totals: dict[str, int]) -> float:
    """
    Compute a 0–1 rule-based risk score from aggregated feature totals.

    Uses the same feature weights as the training pipeline's rule_score,
    applied to a rolling time window instead of the full historical aggregate.
    """
    score = 0.0
    for feat, weight in _RULE_WEIGHTS.items():
        cap   = _CAPS.get(feat, 1)
        score += weight * min(totals.get(feat, 0), cap) / cap
    return round(score, 4)
