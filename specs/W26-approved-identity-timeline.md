# W26: approved account ownership and timeline

Status: implemented and locally released, 30 October 2026.
Details: docs/IDENTITY_MAPPINGS.md.

Acceptance:
- Visible identity directory, manual link approval, evidence/recorder/expiry.
- Native account keys only; no automatic same-name identity resolution.
- One active identity per account, audit-preserving revocation/reassignment.
- Only active approved observed links contribute to the timeline.
- Timestamps, account/source provenance, caps and missing sources remain visible.
- Detector baselines/scores and original event evidence do not change.
- Initial GitHub/Cloudflare owner mapping follows explicit user confirmation.
- AWS root, lab roles and services remain outside the human mapping.
