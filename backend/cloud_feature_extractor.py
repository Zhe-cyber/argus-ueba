"""
cloud_feature_extractor.py — Extract behavioral features from cloud log sources.

Works with the unified 8-field normalized schema produced by normalizer.py.
Designed for AWS CloudTrail, Azure AD, Cloudflare Access, and GitHub Events.

Unlike the CERT feature extractor (which counts USB/email/file events), this
module captures cloud-native behavioral signals: IAM/privilege activity, data
exfiltration patterns, service diversity, credential operations, and so on.

Feature vector (12 dimensions)
-------------------------------
1.  event_count          — total events in the time window
2.  unique_actions        — number of distinct actions performed
3.  unique_resources      — number of distinct resources accessed
4.  unique_ips            — number of distinct source IPs (0 for GitHub)
5.  after_hours_events    — events outside Mon–Fri 07:00–19:00 UTC
6.  sensitive_events      — events matching sensitive resource patterns
7.  error_events          — events with error/denied/fail in action or resource
8.  new_action_count      — actions never seen before in this user's history
9.  iam_sts_events        — IAM / STS / KMS / credential operations
10. data_exfil_events     — read/get/download/list on data stores (S3, blobs, files)
11. admin_events          — user/role/policy create/delete/attach operations
12. assume_role_events    — AssumeRole / GetSessionToken / impersonation events

These 12 features aggregate over a time window (e.g. one day) and are scaled
to [0, 1] by the cloud AE's scaler before model inference.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Feature names (order matters — must match training script)
# ---------------------------------------------------------------------------

CLOUD_FEATURES: list[str] = [
    "event_count",
    "unique_actions",
    "unique_resources",
    "unique_ips",
    "after_hours_events",
    "sensitive_events",
    "error_events",
    "new_action_count",
    "iam_sts_events",
    "data_exfil_events",
    "admin_events",
    "assume_role_events",
]

CLOUD_INPUT_DIM = len(CLOUD_FEATURES)   # 12

# ---------------------------------------------------------------------------
# Pattern libraries (case-insensitive)
# ---------------------------------------------------------------------------

_IAM_PATTERNS = re.compile(
    r"\b(iam|sts|kms|ssm|secretsmanager|credential|getpolicyversion|"
    r"listpolicies|listentitiesforpolicy|attachuserrole|detachrole|"
    r"createrole|deleterole|createuser|deleteuser|createaccesskey|"
    r"updateaccesskey|createloginprofile|listusers|listroles|"
    r"microsoft\.authorization|microsoft\.aad|passwordprofile|"
    r"passwordreset|addmember|removemember)\b",
    re.IGNORECASE,
)

_EXFIL_PATTERNS = re.compile(
    r"\b(getobject|listobjects|listbuckets|getbucketacl|downloadobject|"
    r"readfile|listfiles|listshares|downloadblob|getblob|listblobs|"
    r"describeinstances|getsecretvalue|getparameter|getparameters|"
    r"describedbinstances|listfunctions|getfunction|readcontents|"
    r"DownloadObject|ListObject|read|download|get|list)\b",
    re.IGNORECASE,
)

_ADMIN_PATTERNS = re.compile(
    r"\b(createuser|deleteuser|creategroup|deletegroup|createpolicy|"
    r"deletepolicy|attachpolicy|detachpolicy|putrolepolicy|"
    r"updateassumerolepolicy|createaccesskey|createloginprofile|"
    r"updateloginprofile|changepassword|enablemfadevice|deactivatemfadevice|"
    r"addusertopolicy|removeuserfromgroup|addmember|removemember|"
    r"activatedirectory|createapplication|deleteapplication|"
    r"runinstances|terminateinstances|startinstances|stopinstances|"
    r"createbucket|deletebucket|createfunction|deletefunction)\b",
    re.IGNORECASE,
)

_ASSUME_PATTERNS = re.compile(
    r"\b(assumerole|getsessiontoken|getfederationtoken|assumerolewithsaml|"
    r"assumerolewithwebidentity|imPersonation|addmember|oauth)\b",
    re.IGNORECASE,
)

_ERROR_PATTERNS = re.compile(
    r"\b(error|denied|fail|unauthoriz|forbidden|accessdeni|"
    r"not\s*found|invalid|except|throttl|limit)\b",
    re.IGNORECASE,
)

_SENSITIVE_PATTERNS = re.compile(
    r"\b(iam|secret|kms|admin|root|password|credential|token|key|"
    r"ssm|backup|prod|production|confidential|sensitive|pii|"
    r"financial|salary|internal|private|vpn|ssh)\b",
    re.IGNORECASE,
)

# Off-hours constants
_OH_START = 7   # 07:00 UTC inclusive
_OH_END   = 19  # 19:00 UTC exclusive


# ---------------------------------------------------------------------------
# Single-event feature extraction
# ---------------------------------------------------------------------------

def _is_off_hours(ts_raw: str) -> bool:
    """True if timestamp falls outside Mon–Fri 07:00–19:00 UTC."""
    if not ts_raw:
        return False
    try:
        clean = ts_raw.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean)
        except ValueError:
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(ts_raw, fmt)
                    break
                except ValueError:
                    continue
            else:
                return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        if dt.weekday() >= 5:
            return True
        return not (_OH_START <= dt.hour < _OH_END)
    except Exception:
        return False


def extract_single(event: dict[str, Any]) -> dict[str, int]:
    """
    Extract per-event feature increments from a single normalized event.

    Returns a dict with only the non-zero features so callers can cheaply
    aggregate with totals[feat] += v.
    """
    action   = str(event.get("action",     "")).strip()
    resource = str(event.get("resource",   "")).strip()
    ip       = str(event.get("ip_address", "")).strip()
    ts       = str(event.get("timestamp",  "")).strip()

    combined = f"{action} {resource}".lower()

    feats: dict[str, int] = {
        "event_count": 1,
    }

    if ip and ip not in ("", "127.0.0.1", "::1"):
        feats["unique_ips_token"] = hash(ip)   # tracked separately below

    if _is_off_hours(ts):
        feats["after_hours_events"] = 1
    if _SENSITIVE_PATTERNS.search(resource):
        feats["sensitive_events"] = 1
    if _ERROR_PATTERNS.search(action) or "(denied)" in action.lower():
        feats["error_events"] = 1
    if _IAM_PATTERNS.search(combined):
        feats["iam_sts_events"] = 1
    if _EXFIL_PATTERNS.search(combined):
        feats["data_exfil_events"] = 1
    if _ADMIN_PATTERNS.search(combined):
        feats["admin_events"] = 1
    if _ASSUME_PATTERNS.search(combined):
        feats["assume_role_events"] = 1

    return feats


# ---------------------------------------------------------------------------
# Window-level feature aggregation
# ---------------------------------------------------------------------------

def aggregate_window(events: list[dict[str, Any]], history: list[dict[str, Any]] | None = None) -> dict[str, float]:
    """
    Compute the 12-element feature vector for a list of events in one time window.

    Parameters
    ----------
    events  : events in the current window (e.g., one day)
    history : all prior events for this user (used for new_action_count).
              Pass None to skip the new_action_count feature.

    Returns
    -------
    dict mapping CLOUD_FEATURES names → float values
    """
    if not events:
        return {f: 0.0 for f in CLOUD_FEATURES}

    totals: dict[str, float] = {f: 0.0 for f in CLOUD_FEATURES}
    seen_actions:   set[str] = set()
    seen_resources: set[str] = set()
    seen_ips:       set[str] = set()

    prior_actions: set[str] = set()
    if history:
        prior_actions = {str(e.get("action", "")).lower().strip() for e in history}

    new_action_count = 0

    for ev in events:
        action   = str(ev.get("action",     "")).lower().strip()
        resource = str(ev.get("resource",   "")).strip()
        ip       = str(ev.get("ip_address", "")).strip()
        ts       = str(ev.get("timestamp",  "")).strip()
        combined = f"{action} {resource}".lower()

        seen_actions.add(action)
        if resource:
            seen_resources.add(resource)
        if ip and ip not in ("", "127.0.0.1", "::1"):
            seen_ips.add(ip)

        if history is not None and action and action not in prior_actions:
            new_action_count += 1
            prior_actions.add(action)   # don't double-count within window

        totals["event_count"] += 1

        if _is_off_hours(ts):
            totals["after_hours_events"] += 1
        if _SENSITIVE_PATTERNS.search(resource):
            totals["sensitive_events"] += 1
        if _ERROR_PATTERNS.search(action) or "(denied)" in action:
            totals["error_events"] += 1
        if _IAM_PATTERNS.search(combined):
            totals["iam_sts_events"] += 1
        if _EXFIL_PATTERNS.search(combined):
            totals["data_exfil_events"] += 1
        if _ADMIN_PATTERNS.search(combined):
            totals["admin_events"] += 1
        if _ASSUME_PATTERNS.search(combined):
            totals["assume_role_events"] += 1

    totals["unique_actions"]   = float(len(seen_actions))
    totals["unique_resources"] = float(len(seen_resources))
    totals["unique_ips"]       = float(len(seen_ips))
    totals["new_action_count"] = float(new_action_count)

    return totals
