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
from pathlib import Path
from typing import Dict, List, Optional

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
        for ev in events:
            day = str(ev.get("timestamp", ""))[:10]   # YYYY-MM-DD
            if not day or day == "":
                continue
            for k, v in fex_extract(ev).items():
                daily[day][k] += float(v)

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
# Module-level singleton — imported once, shared across all requests
# ---------------------------------------------------------------------------

ae_scorer = _AEScorer()
