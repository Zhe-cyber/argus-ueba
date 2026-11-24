# AI1: on-demand AI suggestion per finding (Gemini / DeepSeek / Groq)

**Goal:** an analyst clicks "Suggest next steps" on a baseline finding and gets a short plain-English plan (what it
means, three places to check, harmless-if / escalate-if, suggested status). Advisory only.

- `workspace_next/ai_assist.py`: prompt built ONLY from the finding's title, source, day, score/tier, the signal
  breakdown (weights imported from `backend.baseline_scorer.WEIGHTS`) and fact strings; masked (12-digit ids, IPs,
  e-mails, uuids/hex ids). Providers via existing `backend.ai_suggest._collect_tasks` (Gemini → DeepSeek → Groq),
  first success wins; in-process cache per (finding, prompt hash). Never the Anthropic API.
- `POST /workspace/findings/{id}/ai-suggestion`: CHANGING method → session + analyst role + X-Argus-Request (viewers
  cannot spend quota). 422 non-baseline, 503 no provider / all failed.
- Keys: `ARGUS_LLM_ENV` names an env file; `load_keys` copies only GEMINI/DEEPSEEK/GROQ key lines (never
  DATABASE_URL). Cloud server: put a key-only file in /etc/argus/secrets and point ARGUS_LLM_ENV at it.
- UI: `AiSuggestion` in BaselinePanel.js, rendered in the finding drawer for baseline findings; labelled advisory,
  shows the model, "check against the facts above".

**Checks:** backend/tests/test_ai_assist.py (fallback, masking, cache, baseline-only, key loading) + module self-check.
Real call on finding #164: Gemini-2.5, 10.8 s, grounded in the facts.
**Review:** outbound data path → needs an independent security pass before the cloud deploy (Codex or reviewer agent).
