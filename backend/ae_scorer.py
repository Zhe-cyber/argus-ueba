"""
ae_scorer.py — Load the trained PyTorch autoencoder and compute live AE scores.

The model was trained in notebook Cell 10 and saved to Google Drive at:
    /content/drive/MyDrive/fyp-ueba/ml/models/autoencoder_v4.pt
    /content/drive/MyDrive/fyp-ueba/ml/models/scaler_v4.pkl

Download both files to  ml/models/  in the project root to enable live AE scoring.
If the files are absent the scorer silently returns None and the pipeline falls
back to the rule-based live_score already computed by feature_extractor.py.

Feature contract
----------------
The 71-element input vector must be built in the exact column order produced by
training notebook Cells 7–8:

    for each of the 21 BEHAV_FEATURES, in order:
        {feature}_mean, {feature}_max, {feature}_sum
    then:
        files_accessed_burst_ratio
        usb_events_burst_ratio
        after_hours_count_burst_ratio
        usb_file_interaction
        login_count_sum_peer_ratio
        files_accessed_sum_peer_ratio
        usb_events_sum_peer_ratio
        email_count_sum_peer_ratio
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------

_BASE        = Path(__file__).parent.parent
_MDL_DIR     = _BASE / "ml" / "models"
_AE_PATH     = _MDL_DIR / "autoencoder_v4.pt"
_SCALER_PATH = _MDL_DIR / "scaler_v4.pkl"

# ---------------------------------------------------------------------------
# Feature layout — must exactly match training notebook Cells 7–8
# ---------------------------------------------------------------------------

_BEHAV_FEATURES: List[str] = [
    "login_count", "after_hours_count", "unique_pcs",
    "files_accessed", "n_archive_files", "n_exe_files", "n_afterhours_file",
    "usb_events", "has_usb", "n_afterhours_usb",
    "email_count", "total_attachments", "external_emails",
    "n_afterhours_email", "n_bcc_email",
    "http_count", "suspicious_http", "n_job_site",
    "n_cloud_storage", "n_afterhours_http",
    "usb_and_file",
]

# Build MODEL_FEATURES in training order: (21 × 3) + 3 burst + 1 interaction + 4 peer = 71
MODEL_FEATURES: List[str] = []
for _f in _BEHAV_FEATURES:
    for _s in ("mean", "max", "sum"):
        MODEL_FEATURES.append(f"{_f}_{_s}")

MODEL_FEATURES += [
    "files_accessed_burst_ratio",
    "usb_events_burst_ratio",
    "after_hours_count_burst_ratio",
    "usb_file_interaction",
    "login_count_sum_peer_ratio",
    "files_accessed_sum_peer_ratio",
    "usb_events_sum_peer_ratio",
    "email_count_sum_peer_ratio",
]

INPUT_DIM = len(MODEL_FEATURES)   # 71


# ---------------------------------------------------------------------------
# Autoencoder definition — must exactly match training notebook Cell 10
# ---------------------------------------------------------------------------

def _build_autoencoder(input_dim: int):
    """Construct the Autoencoder nn.Module with the training-time architecture."""
    import torch.nn as nn

    class Autoencoder(nn.Module):
        def __init__(self, d: int) -> None:
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Linear(d, 128),
                nn.BatchNorm1d(128), nn.LeakyReLU(0.1), nn.Dropout(0.3),
                nn.Linear(128, 64),
                nn.BatchNorm1d(64),  nn.LeakyReLU(0.1), nn.Dropout(0.2),
                nn.Linear(64, 32),
                nn.BatchNorm1d(32),  nn.LeakyReLU(0.1),
                nn.Linear(32, 16),   nn.LeakyReLU(0.1),
            )
            self.decoder = nn.Sequential(
                nn.Linear(16, 32),   nn.LeakyReLU(0.1),
                nn.Linear(32, 64),
                nn.BatchNorm1d(64),  nn.LeakyReLU(0.1), nn.Dropout(0.2),
                nn.Linear(64, 128),
                nn.BatchNorm1d(128), nn.LeakyReLU(0.1),
                nn.Linear(128, d),
            )

        def forward(self, x):
            return self.decoder(self.encoder(x))

    return Autoencoder(input_dim)


# ---------------------------------------------------------------------------
# Singleton scorer
# ---------------------------------------------------------------------------

class _AEScorer:
    """
    Lazy-loading singleton that wraps the trained autoencoder.

    The model is loaded once on first use.  If the model files are absent
    every call returns None — the rest of the pipeline is unaffected.
    """

    def __init__(self) -> None:
        self._model   = None
        self._scaler  = None
        self._ae_min: float = 0.0
        self._ae_max: float = 1.0
        self._ready   = False
        self._tried   = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> bool:
        if self._tried:
            return self._ready
        self._tried = True

        if not _AE_PATH.exists():
            logger.warning(
                "autoencoder_v4.pt not found in ml/models/ — live AE scoring disabled. "
                "Download from Google Drive: /content/drive/MyDrive/fyp-ueba/ml/models/"
            )
            return False

        if not _SCALER_PATH.exists():
            logger.warning(
                "scaler_v4.pkl not found in ml/models/ — live AE scoring disabled."
            )
            return False

        try:
            import torch
            import joblib

            checkpoint  = torch.load(str(_AE_PATH), map_location="cpu")
            input_dim   = int(checkpoint.get("input_dim", INPUT_DIM))
            ae_net      = _build_autoencoder(input_dim)
            ae_net.load_state_dict(checkpoint["state_dict"])
            ae_net.eval()

            self._model  = ae_net
            self._scaler = joblib.load(str(_SCALER_PATH))
            self._ae_min = float(checkpoint.get("ae_min", 0.0))
            self._ae_max = float(checkpoint.get("ae_max", 1.0))
            self._ready  = True
            logger.info(
                "AE model loaded (%s, input_dim=%d, ae_min=%.6f, ae_max=%.6f)",
                _AE_PATH.name, input_dim, self._ae_min, self._ae_max,
            )
            return True

        except Exception as exc:
            logger.error("Failed to load AE model: %s", exc, exc_info=True)
            return False

    @staticmethod
    def _build_feature_vector(
        events: list,
        peer_means: Optional[Dict[str, float]] = None,
    ) -> Optional[np.ndarray]:
        """
        Convert a list of stored events into the 71-element feature vector
        using the same aggregation logic as training notebook Cell 7.

        Parameters
        ----------
        events      : rows from event_store (dicts with 'timestamp', 'source', …)
        peer_means  : optional dict mapping feature name → peer group mean value
                      (from loader.get_user_peer_context).  Defaults to 1.0 for
                      each peer-ratio feature when not supplied.
        """
        from backend.feature_extractor import extract as fex_extract

        if not events:
            return None

        # ── 1. Group per-event feature increments by calendar day ─────────
        daily: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        # unique_pcs is a per-day DISTINCT count of logon PCs — it cannot be a
        # per-event increment (extract() sees one event at a time), so collect
        # the set of PCs per day here and fold the count into `daily` below.
        daily_pcs: Dict[str, set] = defaultdict(set)
        for ev in events:
            day = str(ev.get("timestamp", ""))[:10]   # YYYY-MM-DD
            if not day or day == "":
                continue
            for k, v in fex_extract(ev).items():
                daily[day][k] += float(v)
            if str(ev.get("source", "")) == "cert_logon":
                meta = ev.get("metadata", {})
                if isinstance(meta, str):
                    import json as _json
                    try:
                        meta = _json.loads(meta)
                    except Exception:
                        meta = {}
                pc = ev.get("resource") or (meta or {}).get("pc")
                if pc:
                    daily_pcs[day].add(str(pc))

        for day, pcs in daily_pcs.items():
            daily[day]["unique_pcs"] = float(len(pcs))

        if not daily:
            return None

        num_days = float(len(daily))

        # ── 2. User-level mean / max / sum for each behavioural feature ───
        vec: Dict[str, float] = {}
        for feat in _BEHAV_FEATURES:
            vals = [daily[d].get(feat, 0.0) for d in daily]
            s    = sum(vals)
            vec[f"{feat}_sum"]  = s
            vec[f"{feat}_mean"] = s / num_days
            vec[f"{feat}_max"]  = float(max(vals))

        # ── 3. Burst ratios (max / mean, clipped to [0, 50]) ─────────────
        for feat in ("files_accessed", "usb_events", "after_hours_count"):
            ratio = vec[f"{feat}_max"] / max(vec[f"{feat}_mean"], 0.001)
            vec[f"{feat}_burst_ratio"] = min(ratio, 50.0)

        # ── 4. USB × file interaction ─────────────────────────────────────
        vec["usb_file_interaction"] = vec["has_usb_sum"] * vec["files_accessed_max"]

        # ── 5. Peer ratios ────────────────────────────────────────────────
        # Use peer_means from the CERT peer-group computation if available;
        # fall back to 1.0 (neutral, no amplification / suppression).
        pm = peer_means or {}
        for feat in (
            "login_count_sum", "files_accessed_sum",
            "usb_events_sum", "email_count_sum",
        ):
            vec[f"{feat}_peer_ratio"] = vec[feat] / max(pm.get(feat, 1.0), 1.0)

        # ── 6. Assemble vector in MODEL_FEATURES order ────────────────────
        x = np.array([vec.get(f, 0.0) for f in MODEL_FEATURES], dtype=np.float32)
        return x

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score_user(
        self,
        user_id: str,
        peer_means: Optional[Dict[str, float]] = None,
    ) -> Optional[float]:
        """
        Compute a live AE anomaly score (0–1) for *user_id* from their stored events.

        Returns
        -------
        float in [0, 1] — higher means more anomalous.
        None  — model files missing, no events, or inference error.
        """
        if not self._load():
            return None

        try:
            from backend import event_store as evstore

            events = evstore.get_user_events(user_id, limit=50_000)
            x_raw  = self._build_feature_vector(events, peer_means)
            if x_raw is None:
                return None

            return self._infer(x_raw)

        except Exception as exc:
            logger.error("AE score_user(%s) failed: %s", user_id, exc, exc_info=True)
            return None

    def _infer(self, x_raw: np.ndarray) -> Optional[float]:
        """Scale → forward pass → normalise reconstruction error to [0, 1]."""
        try:
            import torch

            x_scaled = self._scaler.transform(x_raw.reshape(1, -1)).astype(np.float32)
            x_t      = torch.tensor(x_scaled)

            self._model.eval()
            with torch.no_grad():
                recon = self._model(x_t)
                error = float(((x_t - recon) ** 2).mean().item())

            # Same normalisation as training: (error - ae_min) / (ae_max - ae_min)
            ae_range = self._ae_max - self._ae_min
            if ae_range > 0:
                score = (error - self._ae_min) / ae_range
            else:
                score = 0.0

            return float(np.clip(score, 0.0, 1.0))

        except Exception as exc:
            logger.error("AE inference error: %s", exc, exc_info=True)
            return None

    @property
    def is_ready(self) -> bool:
        """True once the model files have been successfully loaded."""
        return self._load()


# ---------------------------------------------------------------------------
# Cloud AE scorer — second model for cloud-source events
# ---------------------------------------------------------------------------

_CLOUD_AE_PATH     = _MDL_DIR / "cloud_ae_v1.pt"
_CLOUD_SCALER_PATH = _MDL_DIR / "cloud_scaler_v1.pkl"

# Sources that use the cloud AE instead of the CERT AE
CLOUD_SOURCES = {"aws_cloudtrail", "azure_ad", "cloudflare_access", "github_events"}


class _CloudAEScorer:
    """
    Lazy-loading singleton for the cloud-native autoencoder.

    Trained on cloud behavioral features (12 dimensions) from AWS CloudTrail,
    Azure AD, GitHub Events, and Cloudflare Access events.
    Falls back to None when model files are absent.
    """

    def __init__(self) -> None:
        self._model   = None
        self._scaler  = None
        self._ae_min: float = 0.0
        self._ae_max: float = 1.0
        self._features: List[str] = []
        self._ready   = False
        self._tried   = False

    def _load(self) -> bool:
        if self._tried:
            return self._ready
        self._tried = True

        if not _CLOUD_AE_PATH.exists():
            logger.info(
                "cloud_ae_v1.pt not found in ml/models/ — cloud AE scoring disabled. "
                "Run: python scripts/build_cloud_dataset.py && python scripts/train_cloud_ae.py"
            )
            return False
        if not _CLOUD_SCALER_PATH.exists():
            logger.info("cloud_scaler_v1.pkl not found — cloud AE scoring disabled.")
            return False

        try:
            import torch
            import joblib
            from backend.cloud_feature_extractor import CLOUD_FEATURES, CLOUD_INPUT_DIM

            ckpt      = torch.load(str(_CLOUD_AE_PATH), map_location="cpu")
            input_dim = int(ckpt.get("input_dim", CLOUD_INPUT_DIM))

            # Rebuild the cloud AE architecture (must match train_cloud_ae.py)
            import torch.nn as nn

            class _CloudAE(nn.Module):
                def __init__(self, d: int) -> None:
                    super().__init__()
                    self.encoder = nn.Sequential(
                        nn.Linear(d, 32),  nn.LeakyReLU(0.1),
                        nn.Linear(32, 16), nn.LeakyReLU(0.1),
                        nn.Linear(16, 8),  nn.LeakyReLU(0.1),
                    )
                    self.decoder = nn.Sequential(
                        nn.Linear(8, 16),  nn.LeakyReLU(0.1),
                        nn.Linear(16, 32), nn.LeakyReLU(0.1),
                        nn.Linear(32, d),
                    )
                def forward(self, x):
                    return self.decoder(self.encoder(x))

            net = _CloudAE(input_dim)
            net.load_state_dict(ckpt["state_dict"])
            net.eval()

            self._model    = net
            self._scaler   = joblib.load(str(_CLOUD_SCALER_PATH))
            self._ae_min   = float(ckpt.get("ae_min", 0.0))
            self._ae_max   = float(ckpt.get("ae_max", 1.0))
            self._features = ckpt.get("features", CLOUD_FEATURES)
            self._ready    = True
            logger.info(
                "Cloud AE loaded (input_dim=%d, ae_min=%.6f, ae_max=%.6f)",
                input_dim, self._ae_min, self._ae_max,
            )
            return True
        except Exception as exc:
            logger.error("Failed to load cloud AE: %s", exc, exc_info=True)
            return False

    @staticmethod
    def _day_of(ts_raw: str) -> str:
        """
        Return the UTC calendar day (YYYY-MM-DD) for a timestamp, or "" on
        failure.

        Mirrors scripts/build_cloud_dataset.py::_day_of — the training contract
        groups each user's events by UTC calendar day, so serving must derive
        the day the same way (naive timestamps assumed UTC; tz-aware timestamps
        converted to UTC before taking the date).
        """
        if not ts_raw:
            return ""
        try:
            clean = ts_raw.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(clean)
            except ValueError:
                dt = None
                for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                    try:
                        dt = datetime.strptime(ts_raw, fmt)
                        break
                    except ValueError:
                        continue
                if dt is None:
                    # Last-resort: a bare YYYY-MM-DD prefix, matching training's
                    # `return ts[:10]` fallback. Reject anything that is not a
                    # plausible date so malformed rows are skipped, not scored.
                    head = ts_raw[:10]
                    if (len(head) == 10 and head[4] == "-" and head[7] == "-"
                            and head[:4].isdigit() and head[5:7].isdigit()
                            and head[8:10].isdigit()):
                        return head
                    return ""
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            return ""

    @classmethod
    def _split_latest_day(cls, events: list) -> Tuple[list, list]:
        """
        Split a user's cloud events into (window, history), mirroring the
        training-time day grouping (scripts/build_cloud_dataset.py:207-233).

        Training scored each user-day as
        ``aggregate_window(day_events, history=all_events_before_that_day)``.
        The live serving path produces a single score per user, so we score the
        user's LATEST UTC calendar day as the window, with every strictly
        earlier cloud event as history (which feeds new_action_count).

        Events whose timestamps cannot be parsed to a UTC day are dropped, so a
        malformed row can never crash scoring or leak into the wrong bucket.

        Returns ([], []) when no event has a usable timestamp.
        """
        dated = [(cls._day_of(str(e.get("timestamp", ""))), e) for e in events]
        dated = [(d, e) for (d, e) in dated if d]
        if not dated:
            return [], []

        latest_day = max(d for (d, _) in dated)
        window  = [e for (d, e) in dated if d == latest_day]
        history = [e for (d, e) in dated if d < latest_day]
        return window, history

    def score_user(self, user_id: str) -> Optional[float]:
        """
        Score a user's cloud events using the cloud AE.

        Fetches the user's cloud-source events from the event store (up to
        50,000, i.e. effectively their full history) and mirrors the training
        contract's day-window semantics: the LATEST UTC calendar day present is
        the scoring *window*; every strictly earlier cloud event is *history*.
        The 12 behavioural features are aggregated as
        ``aggregate_window(window, history=history)`` — exactly how each
        user-day was built for training in
        scripts/build_cloud_dataset.py:207-233 — so new_action_count is now
        populated at serving time (previously history=None zeroed it). The
        result is a normalised anomaly score in [0, 1].

        Returns None if the model is unavailable or the user has no cloud events.
        """
        if not self._load():
            return None

        try:
            import torch
            import numpy as np
            from backend import event_store as evstore
            from backend.cloud_feature_extractor import CLOUD_FEATURES, aggregate_window

            # Fetch all events for this user
            all_events = evstore.get_user_events(user_id, limit=50_000)
            # Keep only cloud-source events
            cloud_events = [e for e in all_events if e.get("source", "") in CLOUD_SOURCES]
            if not cloud_events:
                return None

            # Mirror training: score the latest UTC day; prior days are history.
            window, history = self._split_latest_day(cloud_events)
            if not window:
                return None

            feats = aggregate_window(window, history=history)
            x_raw = np.array([feats.get(f, 0.0) for f in CLOUD_FEATURES], dtype=np.float32)

            if x_raw.sum() == 0:
                return None

            x_scaled = self._scaler.transform(x_raw.reshape(1, -1)).astype(np.float32)
            x_t      = torch.tensor(x_scaled)

            self._model.eval()
            with torch.no_grad():
                recon = self._model(x_t)
                error = float(((x_t - recon) ** 2).mean().item())

            ae_range = self._ae_max - self._ae_min
            score    = (error - self._ae_min) / ae_range if ae_range > 0 else 0.0
            return float(np.clip(score, 0.0, 1.0))

        except Exception as exc:
            logger.error("Cloud AE score_user(%s) failed: %s", user_id, exc, exc_info=True)
            return None

    @property
    def is_ready(self) -> bool:
        return self._load()


# ---------------------------------------------------------------------------
# Module-level singletons — imported once, shared across all requests
# ---------------------------------------------------------------------------

ae_scorer       = _AEScorer()        # CERT behavioral AE (71-dim)
cloud_ae_scorer = _CloudAEScorer()   # Cloud-native AE (12-dim)
