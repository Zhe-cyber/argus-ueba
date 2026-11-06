# X8 / C11 — live diagnostic receipt consumer contract v1

1 November 2026, Codex. Owner implementation: `workspace_next/diagnostic_receipts.py`.
Claude may create new independent fixture/test files against this interface.
Do not edit the consumer, AWS bound sources or frozen W33 files for C11.

## Python interface

```python
index = load_bundle(directory, *, manifest_sha256, expected_provenance,
                    now=None, max_age_seconds=172800, recorded_mode=False)
result = index.lookup(source, scope, account, day)
```

`manifest_sha256` and `expected_provenance` are externally reviewed/configured trust
inputs. Do not obtain them by automatically trusting the manifest being loaded.
No automatic newest-directory selection. Client requests cannot supply paths/pins.
`ReceiptError.code` is a stable, non-sensitive failure reason. No provider calls,
training, inference, receipt generation or source-store writes occur.

Supported input schemas: `clue_v2_live_diagnostic_receipt_v1` and `..._v2`, with
matching `_manifest` schemas. Other versions fail closed. v1 is an explicit legacy
interpretation, never silently promoted to v2.

## Required validation

- Bounded file sizes and row count; strict JSON (no duplicate keys or NaN/Infinity).
- Trusted manifest SHA, exact expected provenance, `profile=clue_ae_v2`, valid hashes.
- Live mode also checks every declared source hash against its existing file below
  the checkout root. Escaping paths or stale code bindings fail closed. Recorded
  mode permits pinned historical code hashes without calling that old output live.
- Exact receipts content SHA and count; duplicate scoped account-day keys rejected.
- Every receipt's schema, provenance and cutoff agree with the manifest; its ID
  is the canonical digest of key/cutoff/provenance under the generator's rule.
- Only AWS/Cloudflare/GitHub source keys, native account-key format and valid closed
  MYT day; date strictly before cutoff's local day. Cutoff cannot be future.
- `live_activation=false`, `alert=false`, `risk_tier=null`; no live thresholds inferred.
- History dates are sorted/unique and strictly before the receipt day. K=5,
  window=28. v2 preserves `prior_accepted_days` and adds
  `expanding_history_days`, `rolling_window_days`, `feature_history_scope`.
  Expanding equals the legacy list; rolling is its last <=28 entries. Feature 5
  uses expanding history, features 6–9 rolling, features 1–4 current day only.
- Scored output requires input/history eligibility and coverage consistency.
  Unsupported/incomplete/cold-start days cannot carry detector scores.
- Detector B uses the first five named features; C uses all nine. All values and
  terms are finite. Squared residuals, additive terms and raw MSE are nonnegative;
  additive terms and shares reconcile with MSE within float32 tolerance.
- No receipt is treated as a validated risk score or evidence of compromise.

Default freshness limit is 48h. Stale output raises `stale_artifact` in live mode.
Explicit `recorded_mode=True` permits historical output, labelled recorded with its
cutoff; it is never presented as fresh live monitoring.

## Lookup result

Exact key lookup only; never substitute another account/source/day or the latest
available score. Returns `status=diagnostic`, `unscored`, or `unavailable` with the
cutoff, recorded/live mode, receipt fields and explicit history scopes. A missing
key yields `unavailable` and a reason, not a Low/zero score. Invalid query keys raise
`invalid_query`. Invalid bundles never produce a partial usable index.

Backend integration is read-only/opt-in and separate from display approval. The
UI must label raw MSE and contribution shares, keep rules separate, and retain
why-unscored and provenance detail. No alert/case writes on load.

## C11 independent tests requested

Valid v1/v2; >28 accepted days; missing key; zero-event gap receipt; corrupted
manifest/body hash; wrong source/scope/account/day; duplicate key; altered cutoff;
stale/future output; activation/tier violation; forged score eligibility; negative
or nonfinite terms; additive/share mismatch; model/projection/policy hash mismatch.
Use synthetic artifacts only. Tests must not read the January archive or real
models and must not weaken production validation to make a fixture pass.

The consumer implementation is now present, with its own tests in
`backend/tests/test_diagnostic_receipts.py`. Claude's independent C11 tests can
target this interface now. The opt-in preview route is `GET /workspace/diagnostics`
with `source`, `scope`, `account`, `day`; browser callers cannot pass configuration.
Actual diagnostic display remains disabled. See the X9/X8 handoff for verification.

### POC availability and case-context extension (1 November)

`availability_lookup(config, source=..., scope=..., account=..., day=..., now=None)`
uses the same whole-bundle validation, then exposes history/coverage/why-unscored
without numerical detector output. Features and generated behaviour facts are
also withheld. Eligible input is labelled ready with display approval pending;
it is never relabelled Low. Preview route:
`GET /workspace/diagnostic-availability` with the same scoped query.

`POST /cases/{case_id}/diagnostics` retains server-validated context, not a
browser-supplied receipt. It requires analyst/reason, expected case version,
request key, exact receipt ID and artifact manifest SHA. Changed artifacts or
versions return409. Stored snapshots retain provenance and the explicit
`account_day_context_not_trigger_attribution` association. Provider scopes are
masked in displayed snapshots, not changed in their stored identity keys.
