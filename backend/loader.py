"""
loader.py — DataStore singleton for anomaly scores and SHAP data.

Reads CSV/parquet files exactly once at startup, pre-computes
percentile thresholds, then serves all API endpoints from memory.

Usage
-----
    from backend.loader import store

    store.load()                        # call once at app startup
    users = store.get_users(risk="High")
    detail = store.get_user("alice")
    shap   = store.get_user_shap("alice")
    stats  = store.get_stats()
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve

from backend.config import DEMO_MODE, SCORES_PATH, SHAP_PATH, DAILY_FEATURES_PATH

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Accepted column names for the anomaly score (same value, different headers)
_SCORE_COL_CANDIDATES: tuple[str, ...] = ("ae_score", "ensemble_score")

# Accepted column names for the user identifier
_USER_COL_CANDIDATES: tuple[str, ...] = ("user", "user_id", "userId", "username", "User")

# Peer-group clustering (mirrors Cell 7 of the training notebook)
_CLUSTER_FEATURES: tuple[str, ...] = (
    "login_count_sum", "files_accessed_sum", "usb_events_sum", "email_count_sum",
    "external_emails_sum", "n_bcc_email_sum", "suspicious_http_sum",
    "n_job_site_sum", "http_count_sum", "after_hours_count_sum",
)
_PEER_RATIO_FEATURES: tuple[str, ...] = _CLUSTER_FEATURES + (
    "total_attachments_sum", "n_cloud_storage_sum",
    "n_afterhours_email_sum", "n_afterhours_usb_sum",
)
_N_PEER_CLUSTERS = 8


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_col(df: pd.DataFrame, candidates: tuple[str, ...], label: str) -> str:
    """Return the first candidate column present in *df*, or raise ValueError."""
    for col in candidates:
        if col in df.columns:
            return col
    raise ValueError(
        f"No {label} column found. "
        f"Expected one of {candidates}. "
        f"Got: {list(df.columns)}"
    )


def _nan_safe(value: Any) -> Any:
    """Convert float NaN to None so JSON serialisation doesn't choke."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


# ---------------------------------------------------------------------------
# DataStore
# ---------------------------------------------------------------------------

class DataStore:
    """
    Singleton that loads scores and SHAP data once at startup and
    exposes query methods used by every API endpoint.

    Attributes (all set by load())
    ----------
    scores_df          : pd.DataFrame  — full scores table
    shap_df            : pd.DataFrame  — full SHAP table
    loaded             : bool
    _score_col         : str           — e.g. "ae_score"
    _user_col          : str           — e.g. "user"
    _shap_user_col     : str | None    — user column in shap_df, or None if indexed
    _feature_cols      : list[str]     — SHAP feature column names (excludes user col)
    _high_threshold    : float         — p90 score value
    _medium_threshold  : float         — p70 score value
    """

    def __init__(self) -> None:
        self.scores_df:  pd.DataFrame | None = None
        self.shap_df:    pd.DataFrame | None = None
        self.loaded:     bool = False

        self._score_col:        str         = ""
        self._user_col:         str         = ""
        self._shap_user_col:    str | None  = None
        self._feature_cols:     list[str]   = []
        self._high_threshold:   float       = 0.0
        self._medium_threshold: float       = 0.0

        # Peer group data (None when daily_features file is absent)
        self._peer_df:    pd.DataFrame | None = None
        self._peer_sizes: dict[int, int]      = {}

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self) -> None:
        """
        Read scores CSV and SHAP parquet from paths defined in config.py.
        Pre-computes risk thresholds so every subsequent call is O(1).

        Raises
        ------
        FileNotFoundError  if either data file is missing
        ValueError         if required columns cannot be found
        """
        print(f"Loading data ({'DEMO' if DEMO_MODE else 'LOCAL'} mode)")
        print(f"  scores -> {SCORES_PATH}")
        print(f"  SHAP   -> {SHAP_PATH}")

        self.scores_df = pd.read_csv(SCORES_PATH)
        self.shap_df   = pd.read_parquet(SHAP_PATH)

        # Normalise column names (strip surrounding whitespace)
        self.scores_df.columns = self.scores_df.columns.str.strip()
        self.shap_df.columns   = self.shap_df.columns.str.strip()

        # Detect which column holds the score and which holds the user id
        self._score_col = _detect_col(self.scores_df, _SCORE_COL_CANDIDATES, "score")
        self._user_col  = _detect_col(self.scores_df, _USER_COL_CANDIDATES,  "user")

        # Detect user column in SHAP table (may be absent if df is user-indexed)
        for candidate in _USER_COL_CANDIDATES:
            if candidate in self.shap_df.columns:
                self._shap_user_col = candidate
                break

        self._feature_cols = [
            c for c in self.shap_df.columns
            if c != self._shap_user_col
        ]

        # Compute risk thresholds from the data.
        #
        # High  — F1-optimal threshold from precision_recall_curve, replicating
        #         the evaluate() strategy used in training (Cell 13).
        #         Requires is_insider ground-truth labels in the CSV.
        #
        # Medium — 99th percentile of normal-user scores: flags users who deviate
        #          significantly from normal behaviour but haven't crossed the
        #          confident-anomaly boundary.
        scores_arr = self.scores_df[self._score_col].values

        if "is_insider" in self.scores_df.columns:
            y_true = self.scores_df["is_insider"].values
            p, r, t = precision_recall_curve(y_true, scores_arr)
            f1s     = np.where((p + r) > 0, 2 * p * r / (p + r), 0)
            best    = int(f1s.argmax())
            self._high_threshold = float(t[best]) if best < len(t) else 0.5

            normal_scores          = scores_arr[y_true == 0]
            self._medium_threshold = float(np.percentile(normal_scores, 99))
        else:
            # Fallback when no ground-truth labels are available
            mean = float(scores_arr.mean())
            std  = float(scores_arr.std())
            self._high_threshold   = min(mean + 3.0 * std, 1.0)
            self._medium_threshold = min(mean + 2.0 * std, 1.0)

        # Guard: medium must be strictly below high
        self._medium_threshold = min(
            self._medium_threshold, self._high_threshold - 1e-6
        )

        self.loaded = True
        self._compute_peer_groups()

        print(f"  Scores : {len(self.scores_df):,} users  |  col={self._score_col!r}")
        print(f"  SHAP   : {len(self._feature_cols)} features")
        print(
            f"  Thresholds — High >= {self._high_threshold:.4f}  "
            f"Medium >= {self._medium_threshold:.4f}"
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require_loaded(self) -> None:
        if not self.loaded:
            raise RuntimeError(
                "DataStore.load() has not been called. "
                "Call store.load() during application startup."
            )

    def _assign_risk(self, score: float) -> str:
        """Map a single score to a risk label using pre-computed thresholds."""
        if score >= self._high_threshold:
            return "High"
        if score >= self._medium_threshold:
            return "Medium"
        return "Low"

    def _row_to_dict(self, row: pd.Series) -> dict[str, Any]:
        """
        Convert a scores_df row to a clean JSON-serialisable user dict.

        Always exposes:
          user_id, ae_score (normalised name), risk
        Plus every other column in the row, with NaN → None.
        """
        score = float(row[self._score_col])
        result: dict[str, Any] = {
            "user_id":  str(row[self._user_col]),
            "ae_score": round(score, 6),
            "risk":     self._assign_risk(score),
        }
        # Append remaining columns (skip the two already handled above)
        skip = {self._user_col, self._score_col}
        for col, val in row.items():
            if col not in skip:
                result[col] = _nan_safe(val)
        return result

    # ------------------------------------------------------------------
    # Peer group computation
    # ------------------------------------------------------------------

    def _compute_peer_groups(self) -> None:
        """
        Cluster users into behavioural peer groups using K-Means.

        Replicates Cell 7 of the training notebook:
          - Aggregate daily features → per-user totals
          - Fit K-Means on NORMAL users only
          - Assign every user (including insiders) to nearest cluster
          - Compute peer_ratio = user_value / peer_group_mean for each feature
        """
        if not DAILY_FEATURES_PATH.exists():
            print("  [warn] daily_features not found — peer groups skipped")
            return

        from sklearn.cluster import KMeans
        from sklearn.preprocessing import RobustScaler

        daily_df = pd.read_parquet(DAILY_FEATURES_PATH)

        # --- aggregate per user ------------------------------------------
        src_map = {
            "login_count_sum":        ("login_count",        "sum"),
            "files_accessed_sum":     ("files_accessed",     "sum"),
            "usb_events_sum":         ("usb_events",         "sum"),
            "email_count_sum":        ("email_count",        "sum"),
            "external_emails_sum":    ("external_emails",    "sum"),
            "n_bcc_email_sum":        ("n_bcc_email",        "sum"),
            "suspicious_http_sum":    ("suspicious_http",    "sum"),
            "n_job_site_sum":         ("n_job_site",         "sum"),
            "http_count_sum":         ("http_count",         "sum"),
            "after_hours_count_sum":  ("after_hours_count",  "sum"),
            "total_attachments_sum":  ("total_attachments",  "sum"),
            "n_cloud_storage_sum":    ("n_cloud_storage",    "sum"),
            "n_afterhours_email_sum": ("n_afterhours_email", "sum"),
            "n_afterhours_usb_sum":   ("n_afterhours_usb",   "sum"),
        }
        agg_kwargs = {
            out_col: pd.NamedAgg(column=src, aggfunc=fn)
            for out_col, (src, fn) in src_map.items()
            if src in daily_df.columns
        }
        user_agg = daily_df.groupby("user").agg(**agg_kwargs).reset_index()
        user_agg["user"] = user_agg["user"].astype(str)

        # Fill any missing feature columns with zeros
        for col in _PEER_RATIO_FEATURES:
            if col not in user_agg.columns:
                user_agg[col] = 0.0

        # --- determine normal users (same logic as training notebook) -----
        if "is_insider" in self.scores_df.columns:
            normal_ids = set(
                self.scores_df[self.scores_df["is_insider"] == 0][self._user_col].astype(str)
            )
        else:
            normal_ids = set(user_agg["user"])

        normal_mask = user_agg["user"].isin(normal_ids).values

        # --- scale + cluster ---------------------------------------------
        cluster_cols = [c for c in _CLUSTER_FEATURES if c in user_agg.columns]
        X = user_agg[cluster_cols].fillna(0).values
        scaler  = RobustScaler()
        X_scaled = scaler.fit_transform(X)

        km = KMeans(n_clusters=_N_PEER_CLUSTERS, random_state=42, n_init=10, max_iter=300)
        km.fit(X_scaled[normal_mask])
        user_agg["peer_group"] = km.predict(X_scaled).astype(int)

        # --- compute peer_ratio and peer_mean per feature ----------------
        for feat in _PEER_RATIO_FEATURES:
            if feat not in user_agg.columns:
                continue
            peer_mean = user_agg.groupby("peer_group")[feat].transform("mean").clip(lower=1)
            user_agg[f"{feat}_peer_ratio"] = (user_agg[feat] / peer_mean).round(3)
            user_agg[f"{feat}_peer_mean"]  = peer_mean.round(2)

        self._peer_df    = user_agg.set_index("user")
        self._peer_sizes = user_agg.groupby("peer_group")["user"].count().to_dict()
        print(
            f"  Peer groups: {_N_PEER_CLUSTERS} clusters  |  "
            f"fitted on {int(normal_mask.sum())} normal users"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_users(
        self,
        risk:   str | None = None,
        limit:  int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Return a paginated, risk-sorted list of users.

        Parameters
        ----------
        risk   : 'High' | 'Medium' | 'Low' | None  (None = all)
        limit  : maximum records per page            (default 100)
        offset : records to skip before the page     (default 0)

        Returns
        -------
        {
            "total":  int,        # matching record count before paging
            "limit":  int,
            "offset": int,
            "thresholds": {"high": float, "medium": float},
            "users":  list[dict]  # each dict has user_id, ae_score, risk, …
        }

        Raises
        ------
        ValueError  if risk is not a recognised label
        RuntimeError if store is not loaded
        """
        self._require_loaded()

        if risk is not None and risk not in {"High", "Medium", "Low"}:
            raise ValueError(f"risk must be 'High', 'Medium', 'Low', or None — got {risk!r}")

        df = self.scores_df.copy()

        # Assign risk column for filtering / sorting stability
        df["_risk"] = df[self._score_col].map(self._assign_risk)

        if risk is not None:
            df = df[df["_risk"] == risk]

        # Sort highest score first so most suspicious users appear at top
        df = df.sort_values(self._score_col, ascending=False).reset_index(drop=True)

        total = len(df)
        page  = df.iloc[offset : offset + limit]

        # Drop the temporary helper column before serialising
        page = page.drop(columns=["_risk"])
        users = [self._row_to_dict(row) for _, row in page.iterrows()]

        return {
            "total":  total,
            "limit":  limit,
            "offset": offset,
            "thresholds": {
                "high":   round(self._high_threshold,   6),
                "medium": round(self._medium_threshold, 6),
            },
            "users": users,
        }

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        """
        Return full detail for a single user, or None if not found.

        The returned dict includes all score columns plus a risk badge.
        """
        self._require_loaded()

        mask = self.scores_df[self._user_col].astype(str) == str(user_id)
        rows = self.scores_df[mask]
        if rows.empty:
            return None
        return self._row_to_dict(rows.iloc[0])

    def get_user_shap(self, user_id: str) -> dict[str, Any] | None:
        """
        Return SHAP feature-importance values for one user.

        Looks up the user in shap_df either by a user column (if present)
        or by the DataFrame index. Returns features sorted by |shap_value|
        descending so the most influential features come first.

        Returns
        -------
        {
            "user_id":  str,
            "features": [
                {"feature": str, "shap_value": float},
                ...                                       # sorted by |value|
            ]
        }
        or None if the user does not appear in the SHAP table.
        """
        self._require_loaded()

        if self._shap_user_col:
            # Column-based lookup
            mask = self.shap_df[self._shap_user_col].astype(str) == str(user_id)
            rows = self.shap_df[mask]
        else:
            # Index-based lookup (user is the DataFrame index)
            try:
                rows = self.shap_df.loc[[user_id]]
            except KeyError:
                return None

        if rows.empty:
            return None

        row = rows.iloc[0]
        features = sorted(
            [
                {"feature": col, "shap_value": round(float(row[col]), 8)}
                for col in self._feature_cols
            ],
            key=lambda x: abs(x["shap_value"]),
            reverse=True,
        )
        return {"user_id": str(user_id), "features": features}

    def get_user_peer_context(self, user_id: str) -> dict[str, Any] | None:
        """
        Return peer group assignment + top behavioural deviations for one user.

        Returns
        -------
        {
            "peer_group":  int,          # cluster index 0–7
            "peer_size":   int,          # number of users in this cluster
            "deviations":  [             # sorted by |ratio – 1| descending
                {"feature": str, "user_value": float, "peer_mean": float, "ratio": float},
                ...
            ]
        }
        or None if peer groups were not computed.
        """
        self._require_loaded()
        if self._peer_df is None:
            return None

        uid = str(user_id)
        if uid not in self._peer_df.index:
            return None

        row = self._peer_df.loc[uid]
        pg   = int(row["peer_group"])
        size = int(self._peer_sizes.get(pg, 0))

        deviations: list[dict[str, Any]] = []
        for feat in _PEER_RATIO_FEATURES:
            ratio_col = f"{feat}_peer_ratio"
            mean_col  = f"{feat}_peer_mean"
            if ratio_col not in row.index:
                continue
            deviations.append({
                "feature":    feat,
                "user_value": round(float(row.get(feat, 0)), 2),
                "peer_mean":  round(float(row.get(mean_col, 1)), 2),
                "ratio":      round(float(row[ratio_col]), 3),
            })

        # Biggest deviations from peer-group mean first
        deviations.sort(key=lambda x: abs(x["ratio"] - 1.0), reverse=True)

        # Peer-group mean values for the 4 AE role-features (used by ae_scorer)
        _ROLE_FEATS = (
            "login_count_sum", "files_accessed_sum",
            "usb_events_sum",  "email_count_sum",
        )
        cluster_means: dict[str, float] = {}
        for feat in _ROLE_FEATS:
            mean_col = f"{feat}_peer_mean"
            if mean_col in row.index:
                cluster_means[feat] = float(row[mean_col])

        return {
            "peer_group":    pg,
            "peer_size":     size,
            "deviations":    deviations[:8],
            "cluster_means": cluster_means,   # consumed by ae_scorer.score_user()
        }

    def get_stats(self) -> dict[str, Any]:
        """
        Return dataset-level summary statistics.

        Returns
        -------
        {
            "total_users":      int,
            "demo_mode":        bool,
            "score_col":        str,
            "high_threshold":   float,
            "medium_threshold": float,
            "risk_counts":      {"High": int, "Medium": int, "Low": int},
            "score_stats": {
                "mean": float, "std": float,
                "min":  float, "p50": float, "p90": float, "max": float
            },
            "feature_count":    int,
        }
        """
        self._require_loaded()

        scores      = self.scores_df[self._score_col]
        risk_series = scores.map(self._assign_risk)

        return {
            "total_users":      int(len(self.scores_df)),
            "demo_mode":        DEMO_MODE,
            "score_col":        self._score_col,
            "high_threshold":   round(self._high_threshold,   6),
            "medium_threshold": round(self._medium_threshold, 6),
            "risk_counts": {
                "High":   int((risk_series == "High").sum()),
                "Medium": int((risk_series == "Medium").sum()),
                "Low":    int((risk_series == "Low").sum()),
            },
            "score_stats": {
                "mean": round(float(scores.mean()),             6),
                "std":  round(float(scores.std()),              6),
                "min":  round(float(scores.min()),              6),
                "p50":  round(float(scores.quantile(0.50)),     6),
                "p90":  round(float(scores.quantile(0.90)),     6),
                "max":  round(float(scores.max()),              6),
            },
            "feature_count": len(self._feature_cols),
        }


# ---------------------------------------------------------------------------
# Module-level singleton — import and use directly in API endpoints:
#
#     from backend.loader import store
# ---------------------------------------------------------------------------
store = DataStore()
