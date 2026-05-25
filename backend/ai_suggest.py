"""
ai_suggest.py — Free-AI-powered investigation suggestions for SOC analysts.

Provider auto-detection (first key found wins):
  GEMINI_API_KEY   → Google Gemini 2.0 Flash  (free tier, no credit card)
  DEEPSEEK_API_KEY → DeepSeek Chat             (free credits on sign-up)
  GROQ_API_KEY     → Groq / Llama-3.3-70b      (free tier, fast)

Set one of the above in your .env file, then restart the backend.
"""

from __future__ import annotations

import os
from typing import Any


# ---------------------------------------------------------------------------
# Prompt builder  (shared across all providers)
# ---------------------------------------------------------------------------

_SCENARIO_LABELS = {
    0: "No confirmed scenario",
    1: "Scenario 1 — USB / file exfiltration (sudden burst activity)",
    2: "Scenario 2 — Gradual email / cloud exfiltration (disgruntled employee)",
    3: "Scenario 3 — IT sabotage",
}


def _build_prompt(
    user_id:    str,
    risk_level: str,
    ae_score:   float,
    if_score:   float,
    rule_score: float,
    scenario:   int,
    features:   list[dict[str, Any]],
) -> str:
    feat_lines = "\n".join(
        f"  • {f['feature']}: {f['shap_value']:+.5f} "
        f"({'above' if f['shap_value'] > 0 else 'below'} normal peer-group baseline)"
        for f in features[:8]
    )

    return f"""You are a SOC (Security Operations Center) analyst assistant.
A UEBA system flagged the following user as potentially anomalous.
Your job: give the analyst a concise, actionable investigation plan.

═══ USER PROFILE ═══
User ID       : {user_id}
Risk Level    : {risk_level}
AE Score      : {ae_score:.4f}  (autoencoder reconstruction error, higher = more anomalous)
IF Score      : {if_score:.4f}  (Isolation Forest)
Rule Score    : {rule_score:.4f} (rule-based heuristics)
Dataset hint  : {_SCENARIO_LABELS.get(scenario, 'Unknown')}

Top behavioural anomalies (positive = deviates above normal peer group):
{feat_lines}

Feature naming guide:
  *_peer_ratio  = user value ÷ peer-group mean (>1 means elevated vs peers)
  after_hours_* = activity outside 07:00–18:00
  usb_*         = USB device activity
  external_*    = emails sent outside the organisation
  n_job_site    = visits to job-search websites
  suspicious_http = visits to flagged/unusual URLs
  burst_ratio   = max daily activity ÷ mean daily activity (spike indicator)

Respond with these four sections — be specific to the features shown, under 260 words total:

**Priority:** What to investigate first and why (1–2 sentences).

**Evidence to pull:** Specific log sources and time windows (3 bullet points).

**Confirm vs Clear:**
  - Confirm insider: 2–3 patterns that would escalate this
  - Clear: 2–3 patterns that would mark this as benign

**Recommendation:** One of — Escalate to IR / Continue Monitoring / Clear — with a one-sentence rationale."""


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


def _call_gemini(prompt: str) -> str:
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    last_err: Exception | None = None
    for model in _GEMINI_MODELS:
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            return resp.text.strip()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    raise RuntimeError(
        f"All Gemini models failed. Last error: {last_err}\n"
        "Check your API key at https://aistudio.google.com/apikey"
    ) from last_err


def _call_openai_compat(prompt: str, base_url: str, api_key: str, model: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url)
    resp   = client.chat.completions.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


def _call_groq(prompt: str) -> str:
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    resp   = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Auto-detecting dispatcher
# ---------------------------------------------------------------------------

def _detect_provider() -> str:
    """Return the name of the first configured provider."""
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "deepseek"
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    return "none"


def generate(
    user_id:    str,
    risk_level: str,
    ae_score:   float,
    if_score:   float,
    rule_score: float,
    scenario:   int,
    features:   list[dict[str, Any]],
) -> str:
    """
    Call the configured free AI provider and return a plain-text investigation guide.

    Raises RuntimeError if no provider API key is set.
    """
    provider = _detect_provider()
    prompt   = _build_prompt(
        user_id, risk_level, ae_score, if_score, rule_score, scenario, features
    )

    if provider == "gemini":
        return _call_gemini(prompt)

    if provider == "deepseek":
        return _call_openai_compat(
            prompt,
            base_url="https://api.deepseek.com",
            api_key=os.environ["DEEPSEEK_API_KEY"],
            model="deepseek-chat",
        )

    if provider == "groq":
        return _call_groq(prompt)

    raise RuntimeError(
        "No AI provider API key found. Set one of these in your .env file:\n"
        "  GEMINI_API_KEY   — https://aistudio.google.com/apikey  (free, no card)\n"
        "  DEEPSEEK_API_KEY — https://platform.deepseek.com       (free credits)\n"
        "  GROQ_API_KEY     — https://console.groq.com            (free tier)"
    )
