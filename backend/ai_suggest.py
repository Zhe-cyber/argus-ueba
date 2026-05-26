"""
ai_suggest.py — Ensemble AI investigation suggestions for Argus UEBA.

Ensemble strategy
-----------------
All configured providers are queried in **parallel**.
  GEMINI_API_KEY     -> Google Gemini 2.5 / 2.0 Flash  (direct)
  OPENROUTER_API_KEY -> 3 free models via openrouter.ai
                        (Llama-3.3-70B, Gemini-Flash, DeepSeek-V3)
  DEEPSEEK_API_KEY   -> DeepSeek Chat  (direct)
  GROQ_API_KEY       -> Groq / Llama-3.3-70b  (direct)

If >=2 providers succeed, results are fed into a synthesis prompt and
a single authoritative plan is returned alongside the raw source outputs.
If only 1 provider succeeds, that result is returned directly.

Set at least one key in your .env (or HuggingFace Space secrets):
  GEMINI_API_KEY     - https://aistudio.google.com/apikey   (free, no card)
  OPENROUTER_API_KEY - https://openrouter.ai/keys           (free models available)
  DEEPSEEK_API_KEY   - https://platform.deepseek.com        (free credits)
  GROQ_API_KEY       - https://console.groq.com             (free tier, fast)
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any


# ---------------------------------------------------------------------------
# Prompt builder  (shared across all providers)
# ---------------------------------------------------------------------------

_SCENARIO_LABELS = {
    0: "No confirmed scenario",
    1: "Scenario 1 -- USB / file exfiltration (sudden burst activity)",
    2: "Scenario 2 -- Gradual email / cloud exfiltration (disgruntled employee)",
    3: "Scenario 3 -- IT sabotage",
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
        f"  * {f['feature']}: {f['shap_value']:+.5f} "
        f"({'above' if f['shap_value'] > 0 else 'below'} normal peer-group baseline)"
        for f in features[:8]
    )

    return f"""You are a SOC (Security Operations Center) analyst assistant.
A UEBA system flagged the following user as potentially anomalous.
Your job: give the analyst a concise, actionable investigation plan.

USER PROFILE
User ID       : {user_id}
Risk Level    : {risk_level}
AE Score      : {ae_score:.4f}  (autoencoder reconstruction error, higher = more anomalous)
IF Score      : {if_score:.4f}  (Isolation Forest)
Rule Score    : {rule_score:.4f} (rule-based heuristics)
Dataset hint  : {_SCENARIO_LABELS.get(scenario, 'Unknown')}

Top behavioural anomalies (positive = deviates above normal peer group):
{feat_lines}

Feature naming guide:
  *_peer_ratio  = user value / peer-group mean (>1 means elevated vs peers)
  after_hours_* = activity outside 07:00-18:00
  usb_*         = USB device activity
  external_*    = emails sent outside the organisation
  n_job_site    = visits to job-search websites
  suspicious_http = visits to flagged/unusual URLs
  burst_ratio   = max daily activity / mean daily activity (spike indicator)

Respond with these four sections -- be specific to the features shown, under 260 words total:

**Priority:** What to investigate first and why (1-2 sentences).

**Evidence to pull:** Specific log sources and time windows (3 bullet points).

**Confirm vs Clear:**
  - Confirm insider: 2-3 patterns that would escalate this
  - Clear: 2-3 patterns that would mark this as benign

**Recommendation:** One of -- Escalate to IR / Continue Monitoring / Clear -- with a one-sentence rationale."""


def _build_synthesis_prompt(user_id: str, suggestions: dict[str, str]) -> str:
    """Meta-prompt that synthesises multiple provider outputs into one plan."""
    parts = "\n\n".join(
        f"--- {label} ---\n{text}"
        for label, text in suggestions.items()
    )
    return f"""You are a senior SOC analyst. Multiple AI models independently analysed the same \
UEBA-flagged user ({user_id}). Synthesise their investigation suggestions into ONE definitive, \
actionable plan.

Rules:
- Extract the strongest, most specific insights from each source
- Remove duplicate recommendations
- When sources disagree on risk level, be conservative (higher risk wins)
- Keep the same 4-section format (**Priority**, **Evidence to pull**, **Confirm vs Clear**, **Recommendation**)
- Total response: under 300 words
- Do NOT mention the individual sources or that this is a synthesis

=== RAW SUGGESTIONS FROM MULTIPLE MODELS ===
{parts}

=== SYNTHESISED INVESTIGATION PLAN ==="""


# ---------------------------------------------------------------------------
# Provider: Gemini (direct via google-genai SDK)
# ---------------------------------------------------------------------------

_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


_CALL_TIMEOUT = 35  # seconds — per-provider HTTP timeout


def _call_gemini(prompt: str) -> str:
    from google import genai  # noqa: PLC0415
    from google.genai import types as genai_types  # noqa: PLC0415
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    last_err: Exception | None = None
    for model in _GEMINI_MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    http_options=genai_types.HttpOptions(timeout=_CALL_TIMEOUT * 1000),
                ),
            )
            return resp.text.strip()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    raise RuntimeError(
        f"All Gemini models failed. Last error: {last_err}"
    ) from last_err


# ---------------------------------------------------------------------------
# Provider: OpenRouter (3 free models — one OPENROUTER_API_KEY covers all)
# ---------------------------------------------------------------------------

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# (display_label, model_id) — verified :free tier models on OpenRouter
# Deliberately chosen from different upstream providers (NVIDIA/Alibaba/MiniMax)
# to avoid shared rate-limit exhaustion across popular Google/Meta endpoints.
# Last verified against GET /api/v1/models (2025-05-26)
_OPENROUTER_MODELS: list[tuple[str, str]] = [
    ("Nemotron-120B",  "nvidia/nemotron-3-super-120b-a12b:free"),   # NVIDIA
    ("Qwen3-80B",      "qwen/qwen3-next-80b-a3b-instruct:free"),    # Alibaba
    ("MiniMax-M2.5",   "minimax/minimax-m2.5:free"),                # MiniMax
]


def _call_openrouter(prompt: str, model: str) -> str:
    from openai import OpenAI  # noqa: PLC0415
    client = OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url=_OPENROUTER_BASE,
        timeout=_CALL_TIMEOUT,
        default_headers={
            "HTTP-Referer": "https://argus-ueba.vercel.app",
            "X-Title": "Argus UEBA",
        },
    )
    resp = client.chat.completions.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Provider: DeepSeek (direct) and Groq (direct)
# ---------------------------------------------------------------------------

def _call_openai_compat(prompt: str, base_url: str, api_key: str, model: str) -> str:
    from openai import OpenAI  # noqa: PLC0415
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=_CALL_TIMEOUT)
    resp = client.chat.completions.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


def _call_groq(prompt: str) -> str:
    from groq import Groq  # noqa: PLC0415
    client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=_CALL_TIMEOUT)
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Ensemble dispatcher
# ---------------------------------------------------------------------------

def _collect_tasks(prompt: str) -> dict[str, Any]:
    """Build a {label: callable} dict for every configured provider."""
    tasks: dict[str, Any] = {}

    if os.environ.get("GEMINI_API_KEY"):
        tasks["Gemini-2.5"] = lambda: _call_gemini(prompt)

    if os.environ.get("OPENROUTER_API_KEY"):
        for label, model in _OPENROUTER_MODELS:
            # Use default-argument capture to avoid closure-over-loop-variable bug
            tasks[label] = lambda p=prompt, m=model: _call_openrouter(p, m)

    if os.environ.get("DEEPSEEK_API_KEY"):
        tasks["DeepSeek"] = lambda: _call_openai_compat(
            prompt,
            "https://api.deepseek.com",
            os.environ["DEEPSEEK_API_KEY"],
            "deepseek-chat",
        )

    if os.environ.get("GROQ_API_KEY"):
        tasks["Groq-Llama"] = lambda: _call_groq(prompt)

    return tasks


def _synthesize(user_id: str, successful: dict[str, str]) -> str:
    """Call the best available provider to synthesise multiple suggestions."""
    synth_prompt = _build_synthesis_prompt(user_id, successful)

    # Try providers in preference order for synthesis
    if os.environ.get("GEMINI_API_KEY"):
        try:
            return _call_gemini(synth_prompt)
        except Exception:  # noqa: BLE001
            pass

    if os.environ.get("OPENROUTER_API_KEY"):
        try:
            return _call_openrouter(synth_prompt, _OPENROUTER_MODELS[0][1])
        except Exception:  # noqa: BLE001
            pass

    if os.environ.get("GROQ_API_KEY"):
        try:
            return _call_groq(synth_prompt)
        except Exception:  # noqa: BLE001
            pass

    # Last resort: return the longest single suggestion (most detailed)
    return max(successful.values(), key=len)


def generate_ensemble(
    user_id:    str,
    risk_level: str,
    ae_score:   float,
    if_score:   float,
    rule_score: float,
    scenario:   int,
    features:   list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Run all configured providers in parallel, then synthesise into one plan.

    Returns:
        {
            "final":       str,           # synthesised (or single) suggestion
            "sources":     {label: str},  # raw per-provider output
            "synthesized": bool,          # True when >=2 sources were merged
        }

    Raises:
        RuntimeError  if no provider key is configured, or all calls fail.
    """
    prompt = _build_prompt(
        user_id, risk_level, ae_score, if_score, rule_score, scenario, features
    )
    tasks = _collect_tasks(prompt)

    if not tasks:
        raise RuntimeError(
            "No AI provider API key found. Set at least one of:\n"
            "  GEMINI_API_KEY     - https://aistudio.google.com/apikey  (free)\n"
            "  OPENROUTER_API_KEY - https://openrouter.ai/keys          (free models)\n"
            "  DEEPSEEK_API_KEY   - https://platform.deepseek.com       (free credits)\n"
            "  GROQ_API_KEY       - https://console.groq.com            (free tier)"
        )

    # Run all providers concurrently.
    # Each provider has a _CALL_TIMEOUT (35s) HTTP-level timeout.
    # as_completed timeout = 40s so slow stragglers are skipped,
    # then we mark any futures that didn't finish as timed-out errors.
    raw_results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(len(tasks), 6)) as ex:
        future_map = {ex.submit(fn): label for label, fn in tasks.items()}
        try:
            for fut in as_completed(future_map, timeout=40):
                label = future_map[fut]
                try:
                    raw_results[label] = fut.result()
                except Exception as exc:  # noqa: BLE001
                    raw_results[label] = f"[error: {exc}]"
        except TimeoutError:
            pass  # remaining futures are marked below
    # Mark any provider whose future never completed
    for fut, label in future_map.items():
        if label not in raw_results:
            raw_results[label] = "[error: timed out after 40s]"

    successful = {k: v for k, v in raw_results.items() if not v.startswith("[error:")}

    if not successful:
        errors = "; ".join(f"{k}: {v}" for k, v in raw_results.items())
        raise RuntimeError(f"All AI providers failed. Details: {errors}")

    if len(successful) == 1:
        final = next(iter(successful.values()))
        # Return raw_results so callers can see which providers failed and why
        return {"final": final, "sources": raw_results, "synthesized": False}

    # Synthesise from all successful outputs
    final = _synthesize(user_id, successful)
    return {"final": final, "sources": raw_results, "synthesized": True}


# ---------------------------------------------------------------------------
# Backward-compat shim
# ---------------------------------------------------------------------------

def generate(
    user_id:    str,
    risk_level: str,
    ae_score:   float,
    if_score:   float,
    rule_score: float,
    scenario:   int,
    features:   list[dict[str, Any]],
) -> str:
    """Thin wrapper that returns only the final string (backward compatibility)."""
    result = generate_ensemble(
        user_id, risk_level, ae_score, if_score, rule_score, scenario, features
    )
    return result["final"]
