"""
models.py — Pydantic response schemas for the UEBA API.

These models serve two purposes:
  1. FastAPI uses them to validate outgoing responses and generate OpenAPI docs.
  2. They act as a contract between the backend and the frontend — any field
     rename here must be reflected in the React components.

Schema hierarchy
----------------
UserSummary          ← /users list endpoint
  └─ UserDetail      ← /users/{user_id} detail endpoint (adds score breakdown
                        and top 5 SHAP features)

ShapFeature          ← one feature row in a SHAP response
UserShap             ← /users/{user_id}/shap endpoint

Stats                ← /stats endpoint
NormalizedEvent      ← /ingest response (what we echo back after normalisation)
IngestRequest        ← /ingest request body
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# SHAP feature (shared across UserDetail and UserShap)
# ---------------------------------------------------------------------------

class ShapFeature(BaseModel):
    """One SHAP feature contribution for a user."""

    feature: str   = Field(..., description="Feature name, e.g. 'logon_count_night'")
    shap_value: float = Field(..., description="Raw SHAP value (signed)")
    direction: str = Field(
        ...,
        description="'increases_risk' when SHAP value > 0, 'decreases_risk' otherwise",
    )

    @field_validator("direction")
    @classmethod
    def direction_must_be_valid(cls, v: str) -> str:
        allowed = {"increases_risk", "decreases_risk"}
        if v not in allowed:
            raise ValueError(f"direction must be one of {allowed}, got {v!r}")
        return v


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------

class UserSummary(BaseModel):
    """
    Lightweight user row returned by GET /users.

    Fields
    ------
    user        : user identifier (e.g. 'ACM2278')
    ae_score    : autoencoder reconstruction-error anomaly score
    risk_level  : 'High' | 'Medium' | 'Low'  (percentile-derived at load time)
    is_insider  : ground-truth label — 1 if confirmed insider, 0 otherwise
                  (used for evaluation dashboards only, not for decisions)
    scenario    : CERT scenario number (0 = benign, 1–3 = insider variant)
    data_source : 'cert' for CERT dataset users, 'cloud' for live-ingested users
    """

    user: str
    ae_score: float
    risk_level: str = Field(..., description="'High', 'Medium', or 'Low'")
    is_insider: int = Field(..., ge=0, le=1, description="Ground-truth label: 0 or 1")
    scenario: int   = Field(..., ge=0, le=3, description="CERT scenario: 0–3")
    data_source: str = Field("cert", description="'cert' or 'cloud'")

    @field_validator("risk_level")
    @classmethod
    def risk_level_must_be_valid(cls, v: str) -> str:
        allowed = {"High", "Medium", "Low"}
        if v not in allowed:
            raise ValueError(f"risk_level must be one of {allowed}, got {v!r}")
        return v


class UserListResponse(BaseModel):
    """Paginated, risk-ranked user list returned by GET /users."""

    total:  int = Field(..., ge=0, description="Total matching users before paging")
    limit:  int = Field(..., ge=1, description="Page size applied")
    offset: int = Field(..., ge=0, description="Records skipped before this page")
    users:  List[UserSummary]


class PeerDeviation(BaseModel):
    """How much a user's behaviour deviates from their peer group mean."""
    feature:    str
    user_value: float = Field(..., description="User's aggregated value for this feature")
    peer_mean:  float = Field(..., description="Mean value across peer group members")
    ratio:      float = Field(..., description="user_value / peer_mean — >1 means elevated vs peers")


class UserDetail(UserSummary):
    """
    Full user profile returned by GET /users/{user_id}.

    Score fields
    ------------
    ae_score       : Autoencoder reconstruction error — the adopted final detector ★
    if_score       : Isolation Forest (unsupervised comparison baseline)
    rule_score     : rule-based heuristic (comparison baseline)
    wa_score       : weighted IF + AE average (comparison baseline; underperforms AE)
    lgbm_score     : deprecated — LightGBM Stage 2 was not adopted; equals ae_score
    ensemble_score : alias of ae_score, retained for API/back-compat (no score fusion is used)
    top_features   : top 5 reconstruction-error attribution features
    peer_group     : KMeans cluster index (0–7, fitted on normal users)
    peer_size      : number of users in this peer group
    peer_deviations: top behavioural deviations vs peer group mean
    """

    if_score:        float
    rule_score:      float
    wa_score:        float
    lgbm_score:      float = Field(0.0, description="Deprecated; equals ae_score (LightGBM Stage 2 not adopted)")
    ensemble_score:  float = Field(0.0, description="Alias of ae_score; retained for back-compat (no score fusion)")
    top_features:    List[ShapFeature] = Field(
        default_factory=list,
        description="Top 5 attribution features sorted by absolute value descending",
        max_length=5,
    )
    peer_group:      Optional[int]               = Field(None, description="Peer cluster index (0–7)")
    peer_size:       Optional[int]               = Field(None, description="Number of users in peer group")
    peer_deviations: Optional[List[PeerDeviation]] = Field(None, description="Top deviations from peer group mean")


# ---------------------------------------------------------------------------
# SHAP endpoint schema
# ---------------------------------------------------------------------------

class UserShap(BaseModel):
    """
    Full SHAP breakdown returned by GET /users/{user_id}/shap.

    All features are included (not just the top 5), along with a
    plain-English explanation generated from the top contributors.
    """

    user: str
    features: List[ShapFeature] = Field(
        ..., description="All SHAP features sorted by |value| descending"
    )
    reason: str = Field(
        ...,
        description=(
            "Auto-generated plain-English summary of the top risk drivers, "
            "e.g. 'High after-hours logon activity and large external email volume.'"
        ),
    )


# ---------------------------------------------------------------------------
# Stats schema
# ---------------------------------------------------------------------------

class Stats(BaseModel):
    """Dataset-level summary returned by GET /stats."""

    total_users:      int   = Field(..., ge=0)
    high_risk:        int   = Field(..., ge=0, description="Users at High risk level")
    medium_risk:      int   = Field(..., ge=0, description="Users at Medium risk level")
    low_risk:         int   = Field(..., ge=0, description="Users at Low risk level")
    insiders:         int   = Field(..., ge=0, description="Ground-truth insider count (is_insider == 1)")
    high_threshold:   float = Field(..., description="AE score cutoff for High risk (F1-optimal from PR curve)")
    medium_threshold: float = Field(..., description="AE score cutoff for Medium risk (99th pct of normal users)")


# ---------------------------------------------------------------------------
# Normalisation / ingest schemas
# ---------------------------------------------------------------------------

class NormalizedEvent(BaseModel):
    """
    Unified 8-field event returned by POST /ingest after normalisation.

    Mirrors the output schema from normalizer.py exactly so FastAPI can
    validate it automatically.
    """

    timestamp:  str          = Field(..., description="ISO 8601 event timestamp")
    user:       str          = Field(..., description="User identifier")
    source:     str          = Field(
        ...,
        description=(
            "Log source: 'aws_cloudtrail' | 'azure_ad' | 'cert_logon' | "
            "'cert_file' | 'cert_device' | 'cert_email' | 'cert_http'"
        ),
    )
    action:     str          = Field(..., description="Human-readable action description")
    resource:   str          = Field(..., description="Resource that was accessed")
    ip_address: str          = Field(..., description="Source IP address or empty string")
    metadata:   Dict[str, Any] = Field(default_factory=dict, description="Additional source-specific fields")
    raw:        Dict[str, Any] = Field(..., description="Original unmodified event")

    @field_validator("source")
    @classmethod
    def source_must_be_known(cls, v: str) -> str:
        allowed = {
            "aws_cloudtrail", "azure_ad", "cloudflare_access",
            "cert_logon", "cert_file", "cert_device",
            "cert_email", "cert_http", "github_events",
        }
        if v not in allowed:
            raise ValueError(f"source must be one of {allowed}, got {v!r}")
        return v


# ---------------------------------------------------------------------------
# Alert schemas
# ---------------------------------------------------------------------------

ALERT_SEVERITIES = ("Critical", "High", "Medium", "Low")
ALERT_STATUSES   = ("Open", "Acknowledged", "Resolved", "False Positive")


class Alert(BaseModel):
    """One security alert row from the alerts table."""

    id:          int
    user_id:     str
    alert_type:  str  = Field(..., description="rarity_spike | ae_critical | anomalous_behavior | new_user")
    severity:    str  = Field(..., description="Critical | High | Medium | Low")
    title:       str
    details:     Dict[str, Any] = Field(default_factory=dict)
    status:      str  = Field(..., description="Open | Acknowledged | Resolved | False Positive")
    created_at:  str
    resolved_at: Optional[str] = None


class AlertStats(BaseModel):
    """Counts of alerts per status — used by the nav badge and stats bar."""
    open:           int = 0
    acknowledged:   int = 0
    resolved:       int = 0
    false_positive: int = 0
    total:          int = 0


class AlertStatusUpdate(BaseModel):
    """Request body for PATCH /alerts/{id}."""
    status: str

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in ALERT_STATUSES:
            raise ValueError(f"status must be one of {ALERT_STATUSES}, got {v!r}")
        return v


# ---------------------------------------------------------------------------
# Investigation schemas
# ---------------------------------------------------------------------------

INVESTIGATION_STATUSES = ("Pending", "Under Investigation", "Cleared", "Confirmed Insider")


class InvestigationHistoryEntry(BaseModel):
    timestamp: str
    analyst:   str
    status:    str
    note:      str


class InvestigationRecord(BaseModel):
    """Full investigation record returned by GET /users/{id}/investigation."""

    user_id:       str
    status:        str = Field(..., description="Pending | Under Investigation | Cleared | Confirmed Insider")
    analyst:       str = Field(..., description="Display name of the analyst who last updated the record")
    notes:         str = Field("", description="Free-text analyst notes")
    created_at:    str
    updated_at:    str
    history:       List[InvestigationHistoryEntry] = Field(default_factory=list)
    ai_suggestion: Optional[str] = Field(None, description="Claude-generated investigation guide")


class InvestigationUpdate(BaseModel):
    """Request body for PUT /users/{id}/investigation."""

    status:  str = Field(..., description="New status")
    analyst: str = Field("SOC Analyst", description="Analyst display name")
    notes:   str = Field("", description="Investigation notes")

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in INVESTIGATION_STATUSES:
            raise ValueError(
                f"status must be one of {INVESTIGATION_STATUSES}, got {v!r}"
            )
        return v


class PipelineResult(NormalizedEvent):
    """
    Extended response for POST /ingest.

    Includes the standard 8-field normalized event PLUS the downstream
    pipeline output: extracted behavioral features, live 24-hour risk score,
    and a summary of the user's accumulated event history.
    """

    # Step 2 — feature extraction
    extracted_features: Dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Behavioral feature increments contributed by this single event. "
            "Keys match the training pipeline feature names."
        ),
    )

    # Step 3 — live scoring (rolling 24-hour window)
    live_score:      float = Field(
        0.0,
        description="Rule-based risk score (0–1) computed from this user's events in the last 24 h",
    )
    ae_live_score:   Optional[float] = Field(
        None,
        description=(
            "Live AE reconstruction-error score (0–1) from the trained autoencoder, "
            "computed over ALL stored events for this user. "
            "None when ml/models/autoencoder_v4.pt is not present."
        ),
    )
    event_count_24h: int   = Field(
        0,
        description="Number of events ingested for this user in the last 24 hours",
    )
    cumulative_features: Dict[str, int] = Field(
        default_factory=dict,
        description="Total feature counts from all events in the last 24-hour window",
    )
    total_events: int = Field(
        0,
        description="All-time total events stored for this user",
    )

    # Step 5 — rarity flags (source-agnostic anomaly signals)
    rarity_flags: Dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "Five source-agnostic boolean anomaly signals: "
            "first_time_action, new_ip, off_hours, high_volume, sensitive_resource."
        ),
    )
    rarity_score: float = Field(
        0.0,
        description="Fraction of rarity flags that are True (0.0–1.0)",
    )


class LiveScore(BaseModel):
    """
    Current live score for a user (GET /users/{id}/live-score).

    Always returns HTTP 200. Fields are None / 0.0 when the user
    has never had an event ingested (no row in live_scores table).
    """

    user_id:     str
    ae_live:     Optional[float] = Field(None,  description="Live AE score (0–1) or null if not yet scored")
    rule_live:   float           = Field(0.0,   description="Rule-based live score (0–1)")
    rarity:      float           = Field(0.0,   description="Rarity signal fraction (0–1)")
    event_count: int             = Field(0,     description="Total events ingested for this user")
    updated_at:  Optional[str]   = Field(None,  description="ISO timestamp of last update")


class LiveEvent(BaseModel):
    """One event entry from the live event store (GET /users/{id}/events)."""

    id:          int
    user:        str
    timestamp:   str
    source:      str
    action:      str
    resource:    str
    ip_address:  str
    ingested_at: str


class IngestRequest(BaseModel):
    """
    Request body for POST /ingest.

    The caller submits a raw event dict and declares which log source
    it came from; the normalizer routes it to the correct parser.
    """

    event:  Dict[str, Any] = Field(..., description="Raw log event as received from the source")
    source: str = Field(
        ...,
        description=(
            "Log source identifier: 'aws_cloudtrail' | 'azure_ad' | "
            "'cert_logon' | 'cert_file' | 'cert_device' | 'cert_email' | 'cert_http'"
        ),
    )

    @field_validator("source")
    @classmethod
    def source_must_be_known(cls, v: str) -> str:
        allowed = {
            "aws_cloudtrail", "azure_ad", "cloudflare_access",
            "cert_logon", "cert_file", "cert_device",
            "cert_email", "cert_http", "github_events",
        }
        if v not in allowed:
            raise ValueError(f"source must be one of {allowed}, got {v!r}")
        return v
