"""
normalizer.py — Multi-cloud log normalization layer.

Takes raw events from different cloud/CERT sources and maps them to a
unified 8-field internal schema:

    {
        "timestamp":  str   # ISO 8601
        "user":       str   # user identifier
        "source":     str   # one of the SOURCE_* constants below
        "action":     str   # human-readable action description
        "resource":   str   # what was accessed / acted on
        "ip_address": str   # source IP or ""
        "metadata":   dict  # any additional fields worth keeping
        "raw":        dict  # original event, untouched
    }
"""

from __future__ import annotations

from typing import Callable

# ---------------------------------------------------------------------------
# Source identifiers
# ---------------------------------------------------------------------------

SOURCE_AWS        = "aws_cloudtrail"
SOURCE_AZURE      = "azure_ad"
SOURCE_CF         = "cloudflare_access"
SOURCE_CERT_LOGON  = "cert_logon"
SOURCE_CERT_FILE   = "cert_file"
SOURCE_CERT_DEVICE = "cert_device"
SOURCE_CERT_EMAIL  = "cert_email"
SOURCE_CERT_HTTP   = "cert_http"
SOURCE_GITHUB      = "github_events"

KNOWN_SOURCES = {
    SOURCE_AWS,
    SOURCE_AZURE,
    SOURCE_CF,
    SOURCE_CERT_LOGON,
    SOURCE_CERT_FILE,
    SOURCE_CERT_DEVICE,
    SOURCE_CERT_EMAIL,
    SOURCE_CERT_HTTP,
    SOURCE_GITHUB,
}

REQUIRED_FIELDS = ("timestamp", "user", "source", "action", "resource", "ip_address", "metadata", "raw")


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _build(
    *,
    source: str,
    timestamp: str,
    user: str,
    action: str,
    resource: str,
    ip_address: str,
    metadata: dict,
    raw: dict,
) -> dict:
    """Assemble and return a validated unified event dict."""
    return {
        "timestamp":  timestamp  or "",
        "user":       user       or "",
        "source":     source,
        "action":     action     or "",
        "resource":   resource   or "",
        "ip_address": ip_address or "",
        "metadata":   metadata   if isinstance(metadata, dict) else {},
        "raw":        raw,
    }


def _nested_get(d: dict, *keys: str, default: str = "") -> str:
    """Safely retrieve a value from a nested dict; return *default* if missing."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return str(cur) if cur is not None else default


# ---------------------------------------------------------------------------
# Parser: AWS CloudTrail
# ---------------------------------------------------------------------------

def parse_aws_cloudtrail(event: dict) -> dict:
    """
    Map an AWS CloudTrail record to the unified schema.

    Key fields:
        eventTime            → timestamp
        userIdentity.userName (or principalId / arn fallback) → user
        eventName            → action
        requestParameters    → resource  (JSON-serialised or key extracted)
        sourceIPAddress      → ip_address
    """
    identity = event.get("userIdentity", {}) or {}
    user = (
        identity.get("userName")
        or identity.get("principalId")
        or identity.get("arn")
        or ""
    )

    req_params = event.get("requestParameters") or {}
    # Try to pull the most meaningful single value from requestParameters;
    # fall back to a compact string representation.
    resource = (
        req_params.get("bucketName")
        or req_params.get("resourceArn")
        or req_params.get("instanceId")
        or req_params.get("roleName")
        or req_params.get("functionName")
        or (str(req_params) if req_params else "")
    )

    metadata: dict = {}
    for key in ("eventID", "eventSource", "awsRegion", "userAgent", "errorCode", "errorMessage"):
        val = event.get(key)
        if val is not None:
            metadata[key] = val
    if identity:
        metadata["userIdentity"] = identity

    return _build(
        source=SOURCE_AWS,
        timestamp=event.get("eventTime", ""),
        user=str(user),
        action=event.get("eventName", ""),
        resource=str(resource),
        ip_address=event.get("sourceIPAddress", ""),
        metadata=metadata,
        raw=event,
    )


# ---------------------------------------------------------------------------
# Parser: Azure AD Sign-In / Audit logs
# ---------------------------------------------------------------------------

def _aad_extract_user(event: dict) -> str:
    """
    Extract a user principal from any Azure AD log format.

    Handles:
      - Sign-in logs:  userPrincipalName (top-level)
      - Audit logs:    InitiatedBy (JSON string or dict) → user.userPrincipalName
      - Audit logs:    InitiatingUserOrApp (top-level string)
      - M365 Defender: AccountUpn, AccountName
    """
    import json as _json

    # 1. Plain sign-in / simple fields
    for field in ("userPrincipalName", "InitiatingUserOrApp", "InitiatingUser",
                  "AccountUpn", "AccountName"):
        val = event.get(field, "")
        if val:
            return str(val)

    # 2. InitiatedBy — may be a JSON string or already a dict
    initiated_by = event.get("InitiatedBy", "")
    if initiated_by:
        if isinstance(initiated_by, str):
            try:
                initiated_by = _json.loads(initiated_by)
            except Exception:
                pass
        if isinstance(initiated_by, dict):
            upn = (
                _nested_get(initiated_by, "user", "userPrincipalName")
                or _nested_get(initiated_by, "app", "displayName")
            )
            if upn:
                return str(upn)

    return ""


def _aad_extract_resource(event: dict) -> str:
    """
    Extract the primary affected resource from any Azure AD log format.

    Handles:
      - Sign-in logs:  resourceDisplayName
      - Audit logs:    TargetResources (JSON string or list) → first displayName
      - Audit logs:    targetDisplayName
      - M365 Defender: FileName, RemoteUrl
    """
    import json as _json

    # 1. Simple top-level fields
    for field in ("resourceDisplayName", "targetDisplayName", "FileName", "RemoteUrl"):
        val = event.get(field, "")
        if val:
            return str(val)

    # 2. TargetResources — JSON string or list
    tr = event.get("TargetResources", "")
    if tr:
        if isinstance(tr, str):
            try:
                tr = _json.loads(tr)
            except Exception:
                pass
        if isinstance(tr, list) and tr:
            return str(tr[0].get("displayName", "") or tr[0].get("id", ""))

    return ""


def parse_azure_ad(event: dict) -> dict:
    """
    Map an Azure AD log entry to the unified schema.

    Handles three formats automatically:
      1. Sign-in logs    — createdDateTime, userPrincipalName, appDisplayName
      2. Audit logs      — ActivityDateTime / TimeGenerated, InitiatedBy (JSON),
                           OperationName / ActivityDisplayName, TargetResources
      3. M365 Defender   — Timestamp, AccountUpn, ActionType, FileName / RemoteUrl
      4. Azure Monitor diagnostic logs (SignInLogs / AuditLogs via Log Analytics)
                         — top-level `time`/`callerIpAddress`/`location`, with the
                         real fields nested under `properties`.
    """
    # ── Azure Monitor schema: flatten `properties` so the lookups below work ──
    if isinstance(event.get("properties"), dict):
        event = {**event, **event["properties"]}

    # ── Timestamp ────────────────────────────────────────────────────────────
    timestamp = (
        event.get("createdDateTime")
        or event.get("ActivityDateTime")
        or event.get("TimeGenerated")
        or event.get("Timestamp")
        or event.get("time")
        or ""
    )

    # ── User ──────────────────────────────────────────────────────────────────
    user = _aad_extract_user(event)

    # ── Action ────────────────────────────────────────────────────────────────
    action = (
        event.get("appDisplayName")
        or event.get("ActivityDisplayName")
        or event.get("OperationName")
        or event.get("ActionType")
        or event.get("Category")
        or ""
    )

    # ── Resource ──────────────────────────────────────────────────────────────
    resource = _aad_extract_resource(event)

    # ── IP address ────────────────────────────────────────────────────────────
    ip_address = (
        event.get("ipAddress")
        or event.get("IPAddress")
        or event.get("RemoteIP")
        or event.get("callerIpAddress")
        or ""
    )

    # ── Country (Azure Monitor / sign-in location) ───────────────────────────
    loc = event.get("location")
    country = ""
    if isinstance(loc, dict):
        country = loc.get("countryOrRegion") or loc.get("country") or ""
    elif isinstance(loc, str):
        country = loc

    # ── Metadata ─────────────────────────────────────────────────────────────
    metadata: dict = {}
    for key in (
        "id", "Id", "CorrelationId", "correlationId",
        "conditionalAccessStatus", "riskDetail", "riskLevelAggregated",
        "status", "Result", "clientAppUsed", "deviceDetail", "location",
        "UserAgent", "Category", "LoggedByService", "AADOperationType",
        "Type", "SourceSystem",
    ):
        val = event.get(key)
        if val is not None:
            metadata[key] = val
    if country:
        metadata["country"] = country

    return _build(
        source=SOURCE_AZURE,
        timestamp=timestamp,
        user=user,
        action=action,
        resource=resource,
        ip_address=ip_address,
        metadata=metadata,
        raw=event,
    )


# ---------------------------------------------------------------------------
# Parser: Cloudflare Access (Zero Trust)
# ---------------------------------------------------------------------------

def parse_cloudflare_access(event: dict) -> dict:
    """
    Map a Cloudflare Access authentication log entry to the unified schema.

    Real API format (GET /accounts/{id}/access/logs/access_requests):
        action      → action type (e.g. "login", "logout", "allow")
        allowed     → bool — whether access was granted
        app_domain  → FQDN of the protected application
        app_uid     → Cloudflare application UUID
        created_at  → ISO 8601 timestamp
        user_email  → identity email
        user_id     → Cloudflare identity UUID
        ip_address  → source IP
        country     → 2-letter ISO country code (gold for geo_rarity flag)
        ray_id      → Cloudflare request ID

    Free tier: 50 users, 24 h retention, no Logpush streaming.
    No Cloudflare account required to use this parser — synthetic events
    matching this format are sufficient for the FYP demo.
    """
    action_type = str(event.get("action", "access")).lower().strip()
    allowed     = event.get("allowed", True)

    # Append "(denied)" suffix when access was blocked — important signal
    action = action_type if allowed else f"{action_type} (denied)"

    metadata: dict = {}
    for key in ("country", "app_uid", "ray_id", "user_id", "app_type"):
        val = event.get(key)
        if val is not None:
            metadata[key] = val

    return _build(
        source=SOURCE_CF,
        timestamp=event.get("created_at", ""),
        user=str(event.get("user_email", "")),
        action=action,
        resource=str(event.get("app_domain", "")),
        ip_address=str(event.get("ip_address", "")),
        metadata=metadata,
        raw=event,
    )


# ---------------------------------------------------------------------------
# Parsers: CERT insider-threat dataset
# ---------------------------------------------------------------------------
# The CMU CERT dataset uses a common base layout with source-specific fields.
# Common columns: id, date, user, pc, activity, [details vary by log type]

def parse_cert_logon(event: dict) -> dict:
    """
    CERT r6.2 logon.csv row.

    Columns: id, date, user, pc, activity (Logon/Logoff)
    """
    activity = event.get("activity", "")
    action = f"Logon:{activity}" if activity else "Logon"

    metadata: dict = {}
    for key in ("id", "pc"):
        val = event.get(key)
        if val is not None:
            metadata[key] = val

    return _build(
        source=SOURCE_CERT_LOGON,
        timestamp=event.get("date", ""),
        user=event.get("user", ""),
        action=action,
        resource=event.get("pc", ""),
        ip_address="",
        metadata=metadata,
        raw=event,
    )


def parse_cert_file(event: dict) -> dict:
    """
    CERT r6.2 file.csv row.

    Columns: id, date, user, pc, filename, activity (File Copy / Write / Open…)
    """
    metadata: dict = {}
    for key in ("id", "pc", "to_removable_media", "from_removable_media"):
        val = event.get(key)
        if val is not None:
            metadata[key] = val

    return _build(
        source=SOURCE_CERT_FILE,
        timestamp=event.get("date", ""),
        user=event.get("user", ""),
        action=event.get("activity", "File Activity"),
        resource=event.get("filename", ""),
        ip_address="",
        metadata=metadata,
        raw=event,
    )


def parse_cert_device(event: dict) -> dict:
    """
    CERT r6.2 device.csv row.

    Columns: id, date, user, pc, activity (Connect/Disconnect)
    """
    activity = event.get("activity", "")
    action = f"Device:{activity}" if activity else "Device Activity"

    metadata: dict = {}
    for key in ("id", "pc"):
        val = event.get(key)
        if val is not None:
            metadata[key] = val

    return _build(
        source=SOURCE_CERT_DEVICE,
        timestamp=event.get("date", ""),
        user=event.get("user", ""),
        action=action,
        resource=event.get("pc", ""),
        ip_address="",
        metadata=metadata,
        raw=event,
    )


def parse_cert_email(event: dict) -> dict:
    """
    CERT r6.2 email.csv row.

    Columns: id, date, user, pc, to, cc, bcc, from, activity, size,
             attachments, content
    """
    metadata: dict = {}
    for key in ("id", "pc", "to", "cc", "bcc", "from", "size",
                "attachments", "content"):
        val = event.get(key)
        if val is not None:
            metadata[key] = val

    recipient = event.get("to", "")
    resource = f"email→{recipient}" if recipient else "email"

    return _build(
        source=SOURCE_CERT_EMAIL,
        timestamp=event.get("date", ""),
        user=event.get("user", ""),
        action=event.get("activity", "Send Email"),
        resource=resource,
        ip_address="",
        metadata=metadata,
        raw=event,
    )


def parse_cert_http(event: dict) -> dict:
    """
    CERT r6.2 http.csv row.

    Columns: id, date, user, pc, url, activity, content
    """
    metadata: dict = {}
    for key in ("id", "pc", "content"):
        val = event.get(key)
        if val is not None:
            metadata[key] = val

    return _build(
        source=SOURCE_CERT_HTTP,
        timestamp=event.get("date", ""),
        user=event.get("user", ""),
        action=event.get("activity", "HTTP Request"),
        resource=event.get("url", ""),
        ip_address="",
        metadata=metadata,
        raw=event,
    )


# ---------------------------------------------------------------------------
# Parser: GitHub Events (free real-time source — no account required)
# ---------------------------------------------------------------------------

# Map GitHub event types to human-readable SOC actions
_GH_ACTION_MAP = {
    "PushEvent":             "Code push",
    "CreateEvent":           "Branch/tag created",
    "DeleteEvent":           "Branch/tag deleted",
    "PullRequestEvent":      "Pull request",
    "IssuesEvent":           "Issue activity",
    "IssueCommentEvent":     "Issue comment",
    "ForkEvent":             "Repository forked",
    "WatchEvent":            "Repository starred",
    "ReleaseEvent":          "Release published",
    "MemberEvent":           "Member change",
    "PublicEvent":           "Repository made public",
    "GollumEvent":           "Wiki updated",
    "CommitCommentEvent":    "Commit comment",
    "PullRequestReviewEvent":"PR review",
}


def parse_github_events(event: dict) -> dict:
    """
    Map a GitHub Events API record to the unified schema.

    Real API format (GET /events or GET /users/{username}/events):
        id          — event ID string
        type        — event type (PushEvent, CreateEvent, …)
        actor       — { login, display_login, id }
        repo        — { name, url }
        payload     — event-specific payload dict
        created_at  — ISO 8601 timestamp
        public      — bool (private events only visible with auth)

    Free tier: 60 unauthenticated req/hour · 5000 req/hour with token.
    Poll with:  GET https://api.github.com/events
                Authorization: token <GITHUB_TOKEN>   (optional, raises limit)
    """
    actor   = event.get("actor") or {}
    repo    = event.get("repo")  or {}
    payload = event.get("payload") or {}

    user    = str(actor.get("login") or actor.get("display_login") or "")
    ev_type = str(event.get("type", ""))
    action  = _GH_ACTION_MAP.get(ev_type, ev_type)

    # Enrich action with payload hints
    pr_action  = payload.get("action", "")
    if ev_type == "PullRequestEvent" and pr_action:
        action = f"PR {pr_action}"
    elif ev_type == "IssuesEvent" and pr_action:
        action = f"Issue {pr_action}"
    elif ev_type == "PushEvent":
        size = payload.get("size", 0)
        action = f"Code push ({size} commit{'s' if size != 1 else ''})"

    repo_name = str(repo.get("name", ""))

    metadata: dict = {}
    metadata["event_id"] = event.get("id", "")
    metadata["public"]   = event.get("public", True)
    if payload.get("ref"):
        metadata["ref"] = payload["ref"]
    if payload.get("size") is not None:
        metadata["commits"] = payload["size"]
    if actor.get("id"):
        metadata["actor_id"] = actor["id"]

    return _build(
        source=SOURCE_GITHUB,
        timestamp=event.get("created_at", ""),
        user=user,
        action=action,
        resource=repo_name,
        ip_address="",
        metadata=metadata,
        raw=event,
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_PARSERS: dict[str, Callable[[dict], dict]] = {
    SOURCE_AWS:         parse_aws_cloudtrail,
    SOURCE_AZURE:       parse_azure_ad,
    SOURCE_CF:          parse_cloudflare_access,
    SOURCE_CERT_LOGON:  parse_cert_logon,
    SOURCE_CERT_FILE:   parse_cert_file,
    SOURCE_CERT_DEVICE: parse_cert_device,
    SOURCE_CERT_EMAIL:  parse_cert_email,
    SOURCE_CERT_HTTP:   parse_cert_http,
    SOURCE_GITHUB:      parse_github_events,
}


def normalize(event: dict, source: str) -> dict:
    """
    Route *event* to the correct parser based on *source*.

    Parameters
    ----------
    event  : raw log event as a dict
    source : one of the SOURCE_* string constants

    Returns
    -------
    Unified 8-field event dict.

    Raises
    ------
    ValueError  if *source* is not recognised
    TypeError   if *event* is not a dict
    """
    if not isinstance(event, dict):
        raise TypeError(f"event must be a dict, got {type(event).__name__!r}")
    if source not in _PARSERS:
        raise ValueError(
            f"Unknown source {source!r}. "
            f"Valid sources: {sorted(_PARSERS)}"
        )
    return _PARSERS[source](event)
