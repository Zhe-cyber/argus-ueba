# W33 validation-only feature descriptives (features 6–9)

Validation evidence only (original days 27 November–3 December 2017), not independent
evaluation. Descriptive: no scenario recall, method selection, feature change or threshold
tuning may be based on this report. Quantiles use NumPy `method="higher"`. No account
identifiers are reported.

Observed validation account-days: 326 across 61 accounts; status counts: {"eligible": 320, "invalid_input": 6}.

| Feature | Available | Unavailable (reason: rows) | Nonfinite | Accounts | Distinct | Min | P05 | P25 | Median | P75 | P95 | Max | =0 | =1 |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| volume_log_ratio | 320 | {"invalid_input": 6} | 0 | 61 | 287 | -6.03249 | -2.60269 | -0.588943 | -0.0165293 | 0.182322 | 1.26133 | 5.39425 | — | — |
| new_resource_share | 275 | {"invalid_input": 6, "no_resource_today": 45} | 0 | 57 | 17 | 0 | 0 | 0 | 0 | 0 | 0.5 | 1 | 0.858182 | 0.0181818 |
| action_mix_js_distance | 320 | {"invalid_input": 6} | 0 | 61 | 304 | 0 | 0.00130242 | 0.107632 | 0.234157 | 0.442086 | 0.796582 | 0.888859 | 0.05 | 0 |
| hour_profile_js_distance | 320 | {"invalid_input": 6} | 0 | 61 | 311 | 0.0270292 | 0.078966 | 0.410057 | 0.647038 | 0.756449 | 0.860001 | 0.937977 | 0 | 0 |

## Bindings

- export_manifest_sha256: `b430d536676baa0031de84a649689611d36239d6a8d1d4c374718dc7e9011086`
- feature_contract_sha256: `6dcf941133fd2c4b935715b1bd2d5e50534871eadec342f987ef17e88c2b5ced`
- validation_rows_sha256: `6e12a957307ee0b1a79ebc639bebb2ef341ae9ea72a96f208be1743ae3ed8e3d`
- source scripts/clue_features.py: `63456a7639a12e6f3e786fe50443e54590c9fcbe988f048350664bcbf2741b10`
- source scripts/clue_v2_access.py: `f4b5823e4469d4b7139f228aeb9f3b50e7f2eb894c175beacf66a955b315b235`
- source scripts/clue_v2_features.py: `b1d8a97a8d60292ad6497e37ca56a3892e508318dc7c06dc2c41248099c81b00`
- source scripts/clue_v2_reader.py: `ac5b6cc1285a5d2208cfaf91934ac5c25f8f2744c103224f0962dfe945fbd84e`
- source scripts/report_clue_v2_validation.py: `f3833384912bc90f7c7e20cf16c68f8e02c8fdca4f1894480dac4f70404d368b`
- source scripts/shared_core_features.py: `f302d361e461de33561a9ce92c11eee67c549d045cd446a5a74e194fe848dd7d`
- source scripts/shared_core_reader.py: `22395b2454897b7471a1a637bc910a7f161bc2224c98eee0a440058a10218969`
- source scripts/tests/test_clue_v2_validation_report.py: `155209a8c60f28c04fb75f9f142f73ae756243a22d459c189af557e46ea6976a`
