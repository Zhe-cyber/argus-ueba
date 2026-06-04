#!/usr/bin/env python3
"""
github_semisynthetic_eval.py — Labelled evaluation of the rarity detector on a
REAL GitHub background with INJECTED ground-truth attacks.

Methodology (recognised "real background + injected attacks" design, the same
principle used to build CERT r4.2 itself):
  • Benign class  : real events from the GitHub public Events API (label 0).
  • Malicious class: synthetic attacker accounts (label 1) exhibiting realistic
                     account-takeover / malicious-insider GitHub patterns —
                     off-hours high-volume bursts, mass branch deletions, and
                     pushes to sensitively-named repositories.
Every event (benign and malicious) is scored by the SAME source-agnostic rarity
scorer used in production (`backend.rarity_scorer`). Because the injected attacks
carry known labels, we can compute precision / recall / F1 / AUROC / AUPRC — which
is impossible on unlabelled real GitHub data alone.

Outputs:
  results/github_semisynthetic_metrics.json
  results/github_semisynthetic_eval.png   (ROC + PR curves)
"""
from __future__ import annotations
import json, glob, random, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.normalizer import parse_github_events
from backend.rarity_scorer import compute_rarity_flags, rarity_score

SEED = 42
N_ATTACKERS_OVERT   = 10   # full attack pattern (off-hours + volume + sensitive)
N_ATTACKERS_STEALTH = 5    # low-and-slow (sensitive but quiet, business hours)
N_BENIGN_BOTS       = 8    # legitimate high-volume CI/bot accounts (24/7)

# Repos whose names trip the sensitive_resource flag (IAM/secret/key/admin/…)
SENSITIVE_REPOS = [
    "acme/prod-secrets", "acme/aws-credentials", "acme/ssh-keys",
    "internal/admin-tokens", "corp/password-vault", "victim/private-key-store",
    "ops/root-access", "finance/db-passwords",
]
NORMAL_REPOS = [
    "octo/web-app", "octo/api-server", "team/docs", "lib/utils",
    "data/pipeline", "ml/models", "infra/terraform", "site/frontend",
]
ATTACK_TYPES = ["DeleteEvent", "PushEvent", "DeleteEvent", "PushEvent", "CreateEvent"]
NORMAL_TYPES = ["PushEvent", "PullRequestEvent", "IssuesEvent", "IssueCommentEvent", "WatchEvent"]


def _gh(login, ev_type, repo, t):
    return parse_github_events({
        "id": f"{login}-{t.timestamp()}", "type": ev_type,
        "actor": {"login": login}, "repo": {"name": repo},
        "payload": {"ref": "refs/heads/main", "size": 0},
        "created_at": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })


def load_benign() -> dict[str, list[dict]]:
    """Real GitHub events grouped by actor → normalised events. Label 0."""
    users: dict[str, list[dict]] = {}
    for f in sorted(glob.glob(str(ROOT / "data/raw/github/*.json"))):
        for raw in json.load(open(f, encoding="utf-8")):
            try:
                n = parse_github_events(raw)
            except Exception:
                continue
            if n.get("user"):
                users.setdefault(n["user"], []).append(n)
    return users


def make_attackers(seed: int) -> dict[str, list[dict]]:
    """Synthetic attacker accounts (label 1) — overt + stealthy variants."""
    rng = random.Random(seed)
    out: dict[str, list[dict]] = {}

    # Overt: off-hours, high-volume burst, mass-delete on sensitive repos.
    for a in range(N_ATTACKERS_OVERT):
        login = f"redteam_overt_{a:02d}"
        cnt = rng.randint(55, 90)
        start = datetime(2026, 6, 4, rng.choice([1, 2, 3, 4]), 0, 0, tzinfo=timezone.utc)
        out[login] = [_gh(login, rng.choice(ATTACK_TYPES), rng.choice(SENSITIVE_REPOS),
                          start + timedelta(seconds=i * 45)) for i in range(cnt)]

    # Stealthy: low-and-slow — a few sensitive accesses during business hours,
    # no volume burst. Deliberately hard (models the missed-attack failure mode).
    for a in range(N_ATTACKERS_STEALTH):
        login = f"redteam_stealth_{a:02d}"
        cnt = rng.randint(3, 10)
        start = datetime(2026, 6, 4, rng.choice([10, 11, 13, 14]), 0, 0, tzinfo=timezone.utc)
        out[login] = [_gh(login, rng.choice(["PushEvent", "PullRequestEvent"]),
                          rng.choice(SENSITIVE_REPOS),
                          start + timedelta(minutes=i * 25)) for i in range(cnt)]
    return out


def make_benign_bots(seed: int) -> dict[str, list[dict]]:
    """Legitimate high-volume CI/bot accounts (label 0) — 24/7, normal repos.
    These can fire high_volume/off_hours and model the service-account
    false-positive failure mode."""
    rng = random.Random(seed + 1)
    out: dict[str, list[dict]] = {}
    for b in range(N_BENIGN_BOTS):
        login = f"ci-bot-{b:02d}[bot]"
        cnt = rng.randint(40, 120)
        start = datetime(2026, 6, 4, rng.choice([0, 6, 9, 15, 20]), 0, 0, tzinfo=timezone.utc)
        out[login] = [_gh(login, rng.choice(NORMAL_TYPES), rng.choice(NORMAL_REPOS),
                          start + timedelta(seconds=i * 50)) for i in range(cnt)]
    return out


def user_risk(events: list[dict]) -> float:
    """Per-user risk = mean rarity score over the user's events, scored
    incrementally with the same logic as the live pipeline."""
    evs = sorted(events, key=lambda e: e.get("timestamp", ""))
    history: list[dict] = []
    scores = []
    for ev in evs:
        flags = compute_rarity_flags(ev, history)
        scores.append(rarity_score(flags))
        history.append(ev)
    return sum(scores) / len(scores) if scores else 0.0


def main() -> None:
    try:
        import numpy as np
        from sklearn.metrics import (roc_auc_score, average_precision_score,
                                     precision_recall_curve, roc_curve,
                                     precision_score, recall_score, f1_score,
                                     confusion_matrix)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:
        print("pip install numpy scikit-learn matplotlib  —", e); sys.exit(1)

    benign    = load_benign()
    bots      = make_benign_bots(SEED)
    attackers = make_attackers(SEED)

    rows = []  # (user, label, score)
    for u, evs in benign.items():
        rows.append((u, 0, user_risk(evs)))
    for u, evs in bots.items():          # legitimate high-volume bots → label 0
        rows.append((u, 0, user_risk(evs)))
    for u, evs in attackers.items():     # planted attacks → label 1
        rows.append((u, 1, user_risk(evs)))

    y_true  = np.array([r[1] for r in rows])
    y_score = np.array([r[2] for r in rows])
    n_pos   = int(y_true.sum()); n_tot = len(y_true)

    auroc = roc_auc_score(y_true, y_score)
    auprc = average_precision_score(y_true, y_score)

    # F1-optimal threshold
    prec, rec, thr = precision_recall_curve(y_true, y_score)
    f1s = np.where((prec + rec) > 0, 2 * prec * rec / (prec + rec), 0)
    best = int(np.argmax(f1s[:-1])) if len(f1s) > 1 else 0
    t_opt = float(thr[best]) if len(thr) else 0.5
    y_pred = (y_score >= t_opt).astype(int)
    P = precision_score(y_true, y_pred, zero_division=0)
    R = recall_score(y_true, y_pred, zero_division=0)
    F1 = f1_score(y_true, y_pred, zero_division=0)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()

    metrics = {
        "design": "real GitHub background (label 0) + injected synthetic attacks (label 1)",
        "n_users": n_tot, "n_benign": n_tot - n_pos, "n_attackers": n_pos,
        "attacker_pct": round(100 * n_pos / n_tot, 2),
        "seed": SEED,
        "detector": "source-agnostic rarity scorer (mean per-user rarity score)",
        "auroc": round(float(auroc), 4), "auprc": round(float(auprc), 4),
        "f1": round(float(F1), 4), "precision": round(float(P), 4),
        "recall": round(float(R), 4), "threshold": round(t_opt, 4),
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }
    (ROOT / "results").mkdir(exist_ok=True)
    json.dump(metrics, open(ROOT / "results/github_semisynthetic_metrics.json", "w"), indent=2)

    # Plot ROC + PR
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    fpr, tpr, _ = roc_curve(y_true, y_score)
    ax1.plot(fpr, tpr, lw=2, label=f"Rarity detector (AUROC={auroc:.3f})")
    ax1.plot([0, 1], [0, 1], "k--", alpha=0.3)
    ax1.set_xlabel("False Positive Rate"); ax1.set_ylabel("True Positive Rate")
    ax1.set_title("ROC — GitHub real background + injected attacks"); ax1.legend(loc="lower right")
    ax2.plot(rec, prec, lw=2, label=f"AUPRC={auprc:.3f}")
    ax2.axhline(n_pos / n_tot, ls="--", color="grey", alpha=0.5, label=f"baseline={n_pos/n_tot:.3f}")
    ax2.set_xlabel("Recall"); ax2.set_ylabel("Precision")
    ax2.set_title("Precision–Recall"); ax2.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(ROOT / "results/github_semisynthetic_eval.png", dpi=140)

    print(json.dumps(metrics, indent=2))
    print("\n[SAVED] results/github_semisynthetic_metrics.json")
    print("[SAVED] results/github_semisynthetic_eval.png")


if __name__ == "__main__":
    main()
