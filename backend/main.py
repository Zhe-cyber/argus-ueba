"""
main.py — FastAPI application for Argus (Multi-Cloud UEBA Platform).

Start with:
    uvicorn backend.main:app --reload --port 8000

Endpoints
---------
GET  /                    → version + mode + user count
GET  /users               → paginated user list  (query: risk, limit, offset)
GET  /users/{id}          → full user detail + top-5 SHAP features
GET  /users/{id}/shap     → full SHAP breakdown + plain-English reason
GET  /stats               → dataset-level summary statistics
POST /ingest              → normalise a raw log event and echo it back
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import os
from backend.config import DEMO_MODE
from backend.loader import store
from backend import investigations as inv_store
from backend import ai_suggest
from backend import event_store as evstore
from backend import alert_store as astore
from backend import feature_extractor as fex
from backend.ae_scorer import ae_scorer, cloud_ae_scorer, CLOUD_SOURCES
from backend.models import (
    Alert,
    AlertStats,
    AlertStatusUpdate,
    IngestRequest,
    InvestigationRecord,
    InvestigationUpdate,
    LiveEvent,
    LiveScore,
    NormalizedEvent,
    PeerDeviation,
    PipelineResult,
    ShapFeature,
    Stats,
    UserDetail,
    UserShap,
    UserSummary,
)
from backend.normalizer import normalize
from backend.rarity_scorer import compute_rarity_flags, rarity_score as calc_rarity_score

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_VERSION    = "v4"
SHAP_TOP_N     = 10   # features returned by /users/{id}/shap
REASON_TOP_N   = 3    # positive features used in the plain-English reason


# ---------------------------------------------------------------------------
# Lifespan: load data once at startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load scores, SHAP data, and initialise all database tables at startup."""
    store.load()
    evstore.init_db()
    inv_store.init_investigations_db()
    astore.init_alerts_db()
    yield


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    lifespan=lifespan,
    title="Argus API",
    description=(
        "Argus — Multi-Cloud User and Entity Behaviour Analytics. "
        "Anomaly scoring, SHAP explainability, and multi-source log normalisation "
        "across AWS CloudTrail, Azure AD, and CERT endpoint data."
    ),
    version=API_VERSION,
)

# ---------------------------------------------------------------------------
# CORS — controlled via ALLOWED_ORIGINS env var.
# Local dev:  not set → allow everything.
# Production: set to comma-separated URLs, e.g.
#             "https://my-app.vercel.app,https://ueba-security.com"
# ---------------------------------------------------------------------------

_raw_origins = os.getenv("ALLOWED_ORIGINS", "")
_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Internal mapping helpers
# ---------------------------------------------------------------------------

def _guard_loaded() -> None:
    """Raise 503 if the data store hasn't been initialised yet."""
    if not store.loaded:
        raise HTTPException(
            status_code=503,
            detail="Data not loaded. The service is still starting up — retry in a moment.",
        )


def _row_to_summary(row: dict[str, Any]) -> UserSummary:
    """
    Map a loader row dict to a UserSummary Pydantic model.

    loader.py uses 'user_id' and 'risk'; the models use 'user' and 'risk_level'.
    All other fields (is_insider, scenario) are read from the scores CSV via
    the catch-all columns that _row_to_dict() copies in.
    """
    return UserSummary(
        user=str(row.get("user_id", row.get("user", ""))),
        ae_score=float(row.get("ae_score", 0.0)),
        risk_level=str(row.get("risk", "Low")),
        is_insider=int(row.get("is_insider", 0)),
        scenario=int(row.get("scenario", 0)),
    )


def _derive_lgbm_score(row: dict[str, Any]) -> float:
    """
    Deprecated. The LightGBM Stage 2 model was never adopted and no score fusion
    is used; the final detector is the Autoencoder alone. This field is retained
    only for API/back-compat and mirrors ae_score (returns the CSV value if one
    happens to be present, otherwise ae_score).
    """
    raw = float(row.get("lgbm_score", 0.0))
    if raw > 0.0:
        return raw
    return round(float(row.get("ae_score", 0.0)), 6)


def _row_to_detail(
    row:          dict[str, Any],
    top_features: list[ShapFeature],
    peer_context: dict[str, Any] | None = None,
) -> UserDetail:
    """Map a loader row dict to a UserDetail model, injecting SHAP top-5 and peer context."""
    peer_devs = None
    if peer_context:
        peer_devs = [PeerDeviation(**d) for d in peer_context["deviations"]]

    return UserDetail(
        user=str(row.get("user_id", row.get("user", ""))),
        ae_score=float(row.get("ae_score", 0.0)),
        risk_level=str(row.get("risk", "Low")),
        is_insider=int(row.get("is_insider", 0)),
        scenario=int(row.get("scenario", 0)),
        if_score=float(row.get("if_score", 0.0)),
        rule_score=float(row.get("rule_score", 0.0)),
        wa_score=float(row.get("wa_score", 0.0)),
        lgbm_score=_derive_lgbm_score(row),
        ensemble_score=float(row.get("ensemble_score", row.get("ae_score", 0.0))),
        top_features=top_features[:5],
        peer_group=peer_context["peer_group"] if peer_context else None,
        peer_size=peer_context["peer_size"]  if peer_context else None,
        peer_deviations=peer_devs,
    )


def _build_shap_features(raw_features: list[dict[str, Any]], top_n: int) -> list[ShapFeature]:
    """
    Convert raw SHAP dicts from loader into ShapFeature models.

    raw_features is already sorted by |shap_value| descending by loader.py.
    """
    result: list[ShapFeature] = []
    for feat in raw_features[:top_n]:
        sv = float(feat.get("shap_value", feat.get("value", 0.0)))
        result.append(
            ShapFeature(
                feature=str(feat["feature"]),
                shap_value=sv,
                direction="increases_risk" if sv > 0 else "decreases_risk",
            )
        )
    return result


def _build_reason(features: list[ShapFeature], risk_level: str = "Low") -> str:
    """
    Generate a plain-English reason string.

    Low-risk users get a neutral message — reconstruction attribution always
    produces some positive values (centred on the normal baseline), so
    printing "Flagged:" for everyone is misleading.
    """
    if risk_level == "Low":
        return "No significant anomaly detected. Behaviour is within normal peer-group ranges."

    total_abs = sum(abs(f.shap_value) for f in features) or 1.0
    positives = [f for f in features if f.shap_value > 0][:REASON_TOP_N]

    if not positives:
        return "No significant risk-increasing features identified."

    parts = [
        f"{f.feature} ({abs(f.shap_value) / total_abs * 100:.1f}%)"
        for f in positives
    ]
    prefix = "Flagged:" if risk_level == "High" else "Elevated activity:"
    return f"{prefix} " + "; ".join(parts)


# ---------------------------------------------------------------------------
# Alert helpers
# ---------------------------------------------------------------------------

def _maybe_alert(
    user_id:    str,
    alert_type: str,
    severity:   str,
    title:      str,
    details:    dict | None = None,
    *,
    dedup_minutes: int = 60,
) -> None:
    """
    Create an alert only if no active alert of the same type exists for this
    user within the last *dedup_minutes* minutes.  Swallows all exceptions so
    a storage failure never crashes the ingest pipeline.
    """
    try:
        if not astore.recent_alert_exists(user_id, alert_type, dedup_minutes):
            astore.create_alert(user_id, alert_type, severity, title, details)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", summary="Health check / version info")
async def root() -> dict[str, Any]:
    """
    Returns the API version, operating mode, and total user count.
    Useful as a quick health / readiness check.
    """
    _guard_loaded()
    from backend.event_store import _PG
    db_mode = "postgres" if _PG else "sqlite"
    return {
        "version": API_VERSION,
        "mode":    db_mode,
        "users":   len(store.scores_df),
    }


@app.get(
    "/users",
    response_model=List[UserSummary],
    summary="List users with risk badges",
)
async def list_users(
    risk:   Optional[str] = Query(None,  description="Filter by risk level: High | Medium | Low"),
    limit:  int           = Query(100,   ge=1, le=1000, description="Page size"),
    offset: int           = Query(0,     ge=0,          description="Records to skip"),
) -> list[UserSummary]:
    """
    Return a paginated list of users sorted by anomaly score (highest first).

    Includes both CERT dataset users (from parquet) and cloud-sourced users
    that exist only in the live event store (e.g. AWS CloudTrail, Azure AD).
    """
    _guard_loaded()

    if risk is not None and risk not in {"High", "Medium", "Low"}:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid risk level {risk!r}. Must be 'High', 'Medium', or 'Low'.",
        )

    try:
        result = store.get_users(risk=risk, limit=limit, offset=offset)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    parquet_users = [_row_to_summary(row) for row in result["users"]]
    parquet_ids   = {u.user for u in parquet_users}

    # Augment with event-store-only users (cloud sources not in CERT parquet)
    cloud_summaries: list[UserSummary] = []
    for eu in evstore.list_event_store_users():
        uid = str(eu["user"])
        if uid in parquet_ids:
            continue  # already represented
        ae_live = ae_scorer.score_user(uid, peer_means=None) or 0.0
        if ae_live >= 0.7:
            rl = "High"
        elif ae_live >= 0.4:
            rl = "Medium"
        else:
            rl = "Low"
        # Apply risk filter if requested
        if risk is not None and rl != risk:
            continue
        cloud_summaries.append(UserSummary(
            user=uid,
            ae_score=round(ae_live, 6),
            risk_level=rl,
            is_insider=0,
            scenario=0,
            data_source="cloud",
        ))

    # Merge: cloud users first (sorted by score desc), then parquet users
    cloud_summaries.sort(key=lambda u: u.ae_score, reverse=True)
    return cloud_summaries + parquet_users


def _event_store_user_detail(user_id: str) -> UserDetail | None:
    """
    Build a synthetic UserDetail for a user that exists only in the event store
    (e.g. a cloud/CloudTrail user not in the CERT parquet dataset).

    Returns None if the user has no stored events at all.
    """
    total = evstore.get_total_event_count(user_id)
    if total == 0:
        return None

    # Compute live AE score (no peer means available for cloud-only users)
    ae_live = ae_scorer.score_user(user_id, peer_means=None) or 0.0

    # Determine risk tier from AE score
    if ae_live >= 0.7:
        risk_level = "High"
    elif ae_live >= 0.4:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    return UserDetail(
        user=user_id,
        ae_score=round(ae_live, 6),
        risk_level=risk_level,
        is_insider=0,
        scenario=0,
        if_score=0.0,
        rule_score=0.0,
        wa_score=0.0,
        lgbm_score=0.0,
        ensemble_score=round(ae_live, 6),
        top_features=[],
        peer_group=None,
        peer_size=None,
        peer_deviations=None,
    )


@app.get(
    "/users/{user_id}",
    response_model=UserDetail,
    summary="Full user detail with score breakdown and top-5 SHAP features",
)
async def get_user(user_id: str) -> UserDetail:
    """
    Return detailed anomaly scores for a single user plus the five most
    influential SHAP features driving their risk rating.

    Falls back to a live-scoring-only profile for cloud users (CloudTrail,
    Azure AD, etc.) that are not present in the CERT parquet dataset.
    """
    _guard_loaded()

    row = store.get_user(user_id)
    if row is None:
        # Fallback: synthesise a profile from the live event store
        cloud_detail = _event_store_user_detail(user_id)
        if cloud_detail is None:
            raise HTTPException(status_code=404, detail=f"User {user_id!r} not found.")
        return cloud_detail

    # Fetch SHAP and build top-5
    shap_data = store.get_user_shap(user_id)
    top_features: list[ShapFeature] = []
    if shap_data:
        top_features = _build_shap_features(shap_data["features"], top_n=5)

    peer_context = store.get_user_peer_context(user_id)
    return _row_to_detail(row, top_features, peer_context)


@app.get(
    "/users/{user_id}/shap",
    response_model=UserShap,
    summary="Full SHAP breakdown with plain-English reason",
)
async def get_user_shap(user_id: str) -> UserShap:
    """
    Return SHAP feature-importance values for a single user.

    - Returns the top **10** features sorted by |value| descending.
    - `direction` is `'increases_risk'` for positive SHAP values and
      `'decreases_risk'` for negative ones.
    - `reason` is a plain-English summary built from the top 3 positive features.
    """
    _guard_loaded()

    # Confirm user exists in scores table first
    row = store.get_user(user_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found.")

    shap_data = store.get_user_shap(user_id)
    if shap_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"SHAP values for user {user_id!r} not found.",
        )

    features   = _build_shap_features(shap_data["features"], top_n=SHAP_TOP_N)
    risk_level = str(row.get("risk", "Low"))
    reason     = _build_reason(features, risk_level)

    return UserShap(
        user=user_id,
        features=features,
        reason=reason,
    )


@app.get(
    "/stats",
    response_model=Stats,
    summary="Dataset-level summary statistics",
)
async def get_stats() -> Stats:
    """
    Return aggregate counts used by the dashboard header:
    total users, risk distribution, and confirmed insider count.
    """
    _guard_loaded()

    try:
        raw = store.get_stats()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Count ground-truth insiders from the scores DataFrame
    insiders = 0
    if store.scores_df is not None and "is_insider" in store.scores_df.columns:
        insiders = int((store.scores_df["is_insider"] == 1).sum())

    # Count cloud-only users (live-ingested, not in CERT CSV)
    cert_ids = set(store.scores_df["user"].astype(str)) if store.scores_df is not None else set()
    cloud_user_count = sum(
        1 for eu in evstore.list_event_store_users()
        if str(eu["user"]) not in cert_ids
    )

    return Stats(
        total_users=raw["total_users"] + cloud_user_count,
        high_risk=raw["risk_counts"]["High"],
        medium_risk=raw["risk_counts"]["Medium"],
        low_risk=raw["risk_counts"]["Low"],
        insiders=insiders,
        high_threshold=raw["high_threshold"],
        medium_threshold=raw["medium_threshold"],
    )


@app.post(
    "/investigations/bulk",
    summary="Add all High-risk users to the queue (skips users already queued)",
)
async def bulk_import_high_risk() -> dict:
    """
    Fetch every High-risk user from the scores table and create a 'Pending'
    investigation record for each one that doesn't already have a record.

    Returns the counts of created vs skipped records.
    """
    _guard_loaded()

    result  = store.get_users(risk="High", limit=10_000)
    created, skipped = [], []

    for row in result["users"]:
        uid = str(row["user_id"])
        if inv_store.get(uid) is None:
            inv_store.upsert(uid, "Pending", "System",
                             f"Auto-imported: High-risk user (ae_score={row['ae_score']:.4f})")
            created.append(uid)
        else:
            skipped.append(uid)

    return {
        "created": len(created),
        "skipped": len(skipped),
        "total_high_risk": result["total"],
    }


@app.get(
    "/investigations",
    response_model=List[InvestigationRecord],
    summary="List all investigation records (optionally filtered by status)",
)
async def list_investigations(
    status: Optional[str] = Query(
        None,
        description="Filter: Pending | Under Investigation | Cleared | Confirmed Insider",
    ),
) -> list[InvestigationRecord]:
    records = inv_store.list_all(status=status)
    return [InvestigationRecord(**r) for r in records]


@app.get(
    "/users/{user_id}/investigation",
    response_model=InvestigationRecord,
    summary="Get the investigation record for a user",
)
async def get_investigation(user_id: str) -> InvestigationRecord:
    record = inv_store.get(user_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No investigation record for user {user_id!r}.",
        )
    # PostgreSQL SELECT * includes user_id in the row; pop it before unpacking
    # to avoid "TypeError: got multiple values for keyword argument 'user_id'".
    record.pop("user_id", None)
    return InvestigationRecord(user_id=user_id, **record)


@app.put(
    "/users/{user_id}/investigation",
    response_model=InvestigationRecord,
    summary="Create or update an investigation record",
)
async def upsert_investigation(
    user_id: str,
    body: InvestigationUpdate,
) -> InvestigationRecord:
    _guard_loaded()
    # Accept both CERT parquet users and event-store-only (cloud) users
    if store.get_user(user_id) is None and evstore.get_total_event_count(user_id) == 0:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found.")
    try:
        record = inv_store.upsert(
            user_id=user_id,
            status=body.status,
            analyst=body.analyst,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return InvestigationRecord(**record)


@app.delete(
    "/users/{user_id}/investigation",
    status_code=204,
    summary="Delete an investigation record",
)
async def delete_investigation(user_id: str) -> None:
    deleted = inv_store.delete(user_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"No investigation record for user {user_id!r}.",
        )


@app.post(
    "/users/{user_id}/investigation/suggest",
    summary="Generate an AI investigation guide for this user",
)
async def suggest_investigation(user_id: str) -> dict:
    """
    Query all configured free AI providers in parallel (Gemini, OpenRouter models,
    DeepSeek, Groq) then synthesise the results into one authoritative investigation
    plan when >=2 providers succeed.

    Returns:
        user_id     - the requested user
        suggestion  - final synthesised (or single-provider) investigation plan
        sources     - dict of {provider_label: raw_suggestion} for transparency
        synthesized - true when >=2 providers were merged

    The final suggestion is cached in the investigation record.
    """
    _guard_loaded()

    row = store.get_user(user_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found.")

    shap_data = store.get_user_shap(user_id)
    features  = shap_data["features"] if shap_data else []

    try:
        result = ai_suggest.generate_ensemble(
            user_id    = user_id,
            risk_level = str(row.get("risk", "Low")),
            ae_score   = float(row.get("ae_score", 0.0)),
            if_score   = float(row.get("if_score", 0.0)),
            rule_score = float(row.get("rule_score", 0.0)),
            scenario   = int(row.get("scenario", 0)),
            features   = features,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Cache only the final synthesised text in the investigation record
    inv_store.save_suggestion(user_id, result["final"])

    return {
        "user_id":     user_id,
        "suggestion":  result["final"],
        "sources":     result["sources"],
        "synthesized": result["synthesized"],
    }


@app.post(
    "/ingest",
    response_model=PipelineResult,
    status_code=200,
    summary="Normalize → extract features → store → live score (full pipeline)",
)
async def ingest_event(body: IngestRequest) -> PipelineResult:
    """
    Full ingestion pipeline for a raw log event.

    **Stage 1 — Normalize**
    Routes the raw event through the source-specific parser and maps it to
    the unified 8-field internal schema.

    **Stage 2 — Extract Features**
    Detects which behavioral features this event contributes to
    (e.g. a cert_email with external recipients → external_emails +1).

    **Stage 3 — Store**
    Persists the normalized event in the SQLite event store so it contributes
    to the user's rolling behavioral baseline.

    **Stage 4 — Live Score**
    Aggregates all stored events in the last 24 hours for this user and
    computes a rule-based risk score using the same feature weights as the
    training pipeline's rule_score component.
    """
    # ── Stage 1: Normalize ───────────────────────────────────────────────
    try:
        normalised = normalize(body.event, body.source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # ── Stage 2: Feature extraction ──────────────────────────────────────
    features = fex.extract(normalised)

    user_id = normalised["user"]

    # ── Stage 2b: Snapshot history BEFORE inserting the current event ─────
    # Rarity flags must compare against PRIOR history only; fetching after
    # insert would suppress first_time_action / new_ip / geo_rarity on the
    # very first occurrence because the just-inserted event is already in DB.
    history_events = evstore.get_user_events_full(user_id, limit=500)

    # ── Stage 3: Persist ─────────────────────────────────────────────────
    evstore.insert_event(normalised)

    # ── Stage 4: Live score (24-hour rolling window, rule-based) ──────────
    window_events    = evstore.get_user_events_window(normalised["user"], hours=24)
    cumulative       = fex.aggregate(window_events)
    score            = fex.live_score(cumulative)
    total_events     = evstore.get_total_event_count(normalised["user"])

    # ── Stage 5: Live AE score (trained model, all stored events) ─────────
    # Route to the appropriate AE based on event source:
    #   • Cloud sources (aws_cloudtrail, azure_ad, cloudflare_access, github_events)
    #     → cloud_ae_scorer (12-dim cloud behavioral features, trained on CloudTrail)
    #   • CERT sources (cert_logon, cert_file, cert_email, cert_http, cert_device)
    #     → ae_scorer (71-dim CERT behavioral features, trained on CERT r6.2)
    event_source = normalised.get("source", "")
    if event_source in CLOUD_SOURCES:
        ae_live = cloud_ae_scorer.score_user(user_id)
    else:
        peer_context = store.get_user_peer_context(user_id) if store.loaded else None
        peer_means   = peer_context.get("cluster_means") if peer_context else None
        ae_live      = ae_scorer.score_user(user_id, peer_means=peer_means)

    # ── Stage 6: Rarity flags (source-agnostic anomaly signals) ──────────
    # Uses pre-insert history snapshot from Stage 2b (correct semantics).
    r_flags = compute_rarity_flags(normalised, history_events)
    r_score = calc_rarity_score(r_flags)

    # ── Stage 7: Persist live scores ─────────────────────────────────────
    evstore.upsert_live_score(
        user_id     = user_id,
        ae_live     = ae_live if ae_live is not None else 0.0,
        rule_live   = score,
        rarity      = r_score,
        event_count = total_events,
    )

    # ── Stage 8: Auto-create alerts (deduplicated — one per type/user/hour) ──
    flags_fired = sum(1 for v in r_flags.values() if v)

    if total_events == 1:
        # First event ever for this user
        _maybe_alert(
            user_id, "new_user", "Low",
            f"New user observed: {user_id}",
            {"total_events": total_events, "source": normalised["source"]},
        )

    if ae_live is not None and ae_live >= 0.7:
        _maybe_alert(
            user_id, "ae_critical", "Critical",
            f"Critical AE anomaly score ({ae_live:.3f}) for {user_id}",
            {"ae_live": ae_live, "rule_live": score, "rarity_score": r_score},
        )
    elif ae_live is not None and ae_live >= 0.5:
        _maybe_alert(
            user_id, "ae_critical", "High",
            f"Elevated AE anomaly score ({ae_live:.3f}) for {user_id}",
            {"ae_live": ae_live, "rule_live": score},
        )

    if r_score >= 0.6:
        severity = "Critical" if r_score >= 0.8 else "High"
        _maybe_alert(
            user_id, "rarity_spike", severity,
            f"Multi-signal anomaly: {flags_fired} rarity flags fired for {user_id}",
            {"rarity_score": r_score, "flags": r_flags, "source": normalised["source"]},
        )

    if r_flags.get("first_time_action") and r_flags.get("off_hours"):
        _maybe_alert(
            user_id, "anomalous_behavior", "High",
            f"First-time action outside business hours for {user_id}",
            {"action": normalised["action"], "resource": normalised["resource"],
             "timestamp": normalised["timestamp"]},
        )

    return PipelineResult(
        **normalised,
        extracted_features  = features,
        live_score          = score,
        ae_live_score       = ae_live,
        event_count_24h     = len(window_events),
        cumulative_features = cumulative,
        total_events        = total_events,
        rarity_flags        = r_flags,
        rarity_score        = r_score,
    )


@app.get(
    "/users/{user_id}/events",
    response_model=List[LiveEvent],
    summary="Recent ingested events for a user (live activity feed)",
)
async def get_user_events(
    user_id: str,
    limit: int = Query(20, ge=1, le=100, description="Max events to return"),
) -> list[LiveEvent]:
    """
    Return the most recently ingested events for *user_id* from the live
    event store, newest first.

    Events are populated by POST /ingest calls — they represent logs that
    have been normalised and stored through the ingestion pipeline.
    """
    rows = evstore.get_user_events(user_id, limit=limit)
    return [LiveEvent(**r) for r in rows]


@app.get(
    "/users/{user_id}/live-score",
    response_model=LiveScore,
    summary="Current live risk scores for a user (persisted from last /ingest call)",
)
async def get_live_score(user_id: str) -> LiveScore:
    """
    Return the most recently persisted live risk scores for *user_id*.

    Scores are updated every time a new event is ingested via POST /ingest.
    Always returns HTTP 200 — fields are null / 0 when the user has never
    had an event ingested.

    Fields
    ------
    ae_live     : live autoencoder score (0–1), None when model unavailable
    rule_live   : rule-based live score from last 24-hour window
    rarity      : fraction of rarity flags that fired (0–1)
    event_count : all-time event count for this user
    updated_at  : ISO timestamp of last ingest for this user
    """
    row = evstore.get_live_score(user_id)
    if row is None:
        return LiveScore(
            user_id     = user_id,
            ae_live     = None,
            rule_live   = 0.0,
            rarity      = 0.0,
            event_count = 0,
            updated_at  = None,
        )
    return LiveScore(
        user_id     = str(row["user_id"]),
        ae_live     = float(row["ae_live"]) if row.get("ae_live") is not None else None,
        rule_live   = float(row.get("rule_live", 0.0)),
        rarity      = float(row.get("rarity", 0.0)),
        event_count = int(row.get("event_count", 0)),
        updated_at  = str(row.get("updated_at", "")),
    )


# ---------------------------------------------------------------------------
# Alert endpoints
# NOTE: /alerts/summary MUST be defined before /alerts/{alert_id} so FastAPI
# does not try to match the literal string "summary" as an integer alert_id.
# ---------------------------------------------------------------------------

@app.get(
    "/alerts/summary",
    response_model=AlertStats,
    summary="Counts of alerts by status (for nav badge + stats bar)",
)
async def get_alert_summary() -> AlertStats:
    """Return counts of alerts grouped by status. Polled every 15 s by the nav bar."""
    stats = astore.get_stats()
    return AlertStats(**stats)


@app.get(
    "/alerts",
    response_model=List[Alert],
    summary="List security alerts (newest first)",
)
async def list_alerts(
    status: Optional[str] = Query(
        None,
        description="Filter: Open | Acknowledged | Resolved | False Positive",
    ),
    limit:  int = Query(50, ge=1, le=200),
    offset: int = Query(0,  ge=0),
) -> list[Alert]:
    """
    Return security alerts from the auto-generated alert queue.

    Alerts are created by the /ingest pipeline when anomaly thresholds are
    crossed (rarity spike, critical AE score, first-time off-hours action, etc.)
    """
    rows = astore.list_alerts(status=status, limit=limit, offset=offset)
    return [Alert(**r) for r in rows]


@app.patch(
    "/alerts/{alert_id}",
    response_model=Alert,
    summary="Update alert status (Acknowledge / Resolve / False Positive)",
)
async def update_alert(alert_id: int, body: AlertStatusUpdate) -> Alert:
    """
    Transition an alert to a new status.

    Valid transitions:
      Open → Acknowledged  (analyst is working on it)
      Open / Acknowledged → Resolved  (threat confirmed and contained)
      Open / Acknowledged → False Positive  (benign activity confirmed)
      Resolved / False Positive → Open  (re-open if needed)
    """
    updated = astore.update_status(alert_id, body.status)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found.")
    return Alert(**updated)
