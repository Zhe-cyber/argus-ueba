# W25: native account keys

Status: implemented and locally released, 30 October 2026.
Details and evidence: docs/ACCOUNT_IDENTITY_KEYS.md.

Acceptance:
- Source/namespace/native-principal tuple determines the internal key; label does not.
- Renames retain history; AWS sessions from one role share a role account.
- Missing identity is retained as unattributed evidence without guessed ownership.
- Account histories, rule aggregation, details and case references are scope-isolated.
- Existing evidence/receipts remain immutable under additive migration.
- Only unambiguous legacy alert/case references migrate; no case merges or resets.
- Dashboard labels stay readable, with type, namespace and expandable identity basis.
- No change to model activation, frozen studies, cloud permissions or human mappings.
