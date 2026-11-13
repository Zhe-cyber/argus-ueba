# Competition claims audit: Argus

Date: 25 October 2026, Asia/Kuala_Lumpur.
Scope: the organizer introduction supplied in chat, current local master
0d45b4ef81d279d4d728582cae8bea4d0432a7bf, local feature-branch specifications,
training notebooks, saved metrics and NIST's publication page.

This is a claim/evidence assessment, not a security certification or live deployment
test. Real account access, collector deployment and live detection have not been
verified in this assessment. Local changes and unpublished branches are not treated
as shipped features.

## Overall verdict

The problem framing and Prototype status are defensible. The implementation contains
more than a CERT demonstration: it has a separate 12-feature cloud autoencoder and
cloud event normalization/scoring. However, the submitted feature list overstates
GitHub audit coverage and the fidelity/completeness of SHAP explanations. Normalizer
support does not establish live integration, and a model trained on CloudTrail does
not establish validated detection on all supported feeds.

## Claim-by-claim assessment

| Organizer claim | Evidence and verdict | Accurate current wording / release requirement |
|---|---|---|
| Legitimate credentials can conceal suspicious behavior; evidence is distributed | Reasonable problem framing. An anomaly score is not proof of compromise or malicious intent. | Keep the problem statement; describe alerts as investigation leads. |
| NIST's 2026 multi-cloud draft highlights identity and telemetry/logging | Verified on the NIST page: initial draft published 21 August 2026; identity/access management and telemetry/logging are explicitly identified. | Keep the citation and the word draft. It motivates the problem, not proof that Argus solves it. |
| Normalizes AWS CloudTrail, Entra sign-ins, Cloudflare Access and GitHub audit events | AWS/Entra/Cloudflare parsers exist. GitHub parser expects Events API actor/repo/payload fields, not organization audit-log schema. | Say four-source normalization including GitHub activity events. Label Entra as parser support, not a connected live source. |
| Builds behavioral features and user baselines | CERT aggregate features, cloud daily-window features and prior-history rarity comparisons exist. Cloud off-hours is fixed UTC; rarity history at ingest is capped at 500 events; high-volume threshold is fixed. | Say behavioral aggregation and prior-history comparisons. Learned personal working hours, adaptive volume and continuously learned personal models remain incomplete. |
| Detects unusual behavior without labelled attack data | AE training excludes attacker rows. Historical evaluation uses labels to select normal cohorts, evaluate detection and select the CERT alert threshold. | Say one-class autoencoder trained on selected normal activity without attack examples in the fitting objective. Do not call the entire evaluated pipeline label-free. |
| Uses a deep autoencoder trained on normal activity | Architecture/training paths support this for both 71-feature CERT and 12-feature cloud AEs. Cloud dataset builder is CloudTrail/flaws.cloud based despite broader docstrings. | Keep, with training provenance and cloud generalization limitations. Do not imply the CERT model was validated as a cloud detector. |
| Six interpretable rarity signals | Six functions exist and return first-time action, new IP, off-hours, high-volume, sensitive-resource and geo-rarity flags. Signals need available fields/history. GitHub Events parser leaves IP empty. | Keep as six supported signals, with per-source availability and cold-start status. A missing input is not evidence that a signal is normal. |
| SHAP shows which behavioral features contributed to an alert | CERT notebook cell 23 (zero-based) uses TreeExplainer on Isolation Forest, not the AE. Cloud seeding script uses signed squared reconstruction residuals stored as shap_value; these are not SHAP. Live ingest does not populate fresh cloud explanations. | Current wording must distinguish IF SHAP from cloud reconstruction diagnostics. To retain the intended AE SHAP claim, implement attribution of the actual AE score and test its baseline, model version, feature vector and additivity tolerance. |
| LLM translates SHAP/context into plain-language guidance; human decides | LLM provider/prompt pipeline and suggestion endpoint exist; route returns text and saves a suggestion. Inspected route does not execute remediation. Prompt is CERT-oriented, contains benchmark scenario hints, IF/rule scores and assumes peer-relative interpretations. Live cloud inputs may lack explanation features. | Say AI-assisted investigation suggestions, subject to review. Require source-aware prompts, evidence provenance, no ground-truth scenario input, no invented missing evidence, explicit limitations and graceful unavailability. Live usefulness is unverified. |
| Analyst dashboard for review and triage | User, alert and investigation views/APIs exist. Current user/stats surfaces combine benchmark and cloud records. | Keep as prototype capability, separate benchmark exploration from real live monitoring. Do not display benchmark ground truth as discovered live incidents. |
| Proposed identity linking and cross-cloud timeline | W6-A branch/spec exists; master lacks its identity module. Current design has source scoping limitations and no provider-account/tenant key. | Correctly labelled proposed. Completion requires authorized, reversible verified mappings, exact account-scoped timeline membership and collision tests. |
| Proposed data coverage and baseline-history indicators | No implemented coverage/cold-start status found in the inspected mainline paths. | Keep labelled proposed. Implement source connectivity, last successful fetch, newest event, history span/count and insufficient-evidence status. |
| Target SME administrators/generalists/analysts | Target audience is a product choice, not a validated usability outcome. | Keep intended audience; usefulness/time-saving remains an evaluation question. |
| Functional outcome across connected sources | Reasonable target; current parser/model code alone does not prove real connected deployment or operational detection quality. | Phrase as intended outcome until the live acceptance scenario is recorded. |
| Integrated evidence-led workflow is the contribution | A defensible intended contribution, not evidence of novelty over every competitor. Components are established methods. | Keep the modest integration claim. Evaluate the workflow with actual users/scenarios before claiming investigation improvement. |
| Current status / demonstration type: Prototype | Consistent with the observed state. | Keep. Do not substitute production-ready until release criteria have evidence. |

## Findings that affect credibility most

### 1. Benchmark dependence remains in the live application

backend/config.py selects CERT score/SHAP/daily-feature artifacts outside demo mode.
backend/main.py uses _guard_loaded() in user detail, SHAP, stats and AI suggestion
routes. The combined users/stats paths mix benchmark records with live cloud records.
Thus DEMO_MODE=false does not mean cloud-only operation.

Competition acceptance: start a dedicated live deployment with no CERT score CSV,
SHAP parquet or seeded attacker users. Ingest real provider events, show real cloud
identities, retrieve details and investigate an alert. Put benchmark exploration in
a visibly separate mode with its own labels and metrics.

### 2. Explanation method and explained detector do not match

- cert_ae_full_pipeline.ipynb, code cell 23: shap.TreeExplainer(best_if_model), with
  output written to shap_values_v4.parquet. This generation path explains IF; negating
  its output does not turn it into an explanation of autoencoder reconstruction error.
  The current exported file's full provenance should be recorded/recomputed before reuse.
- scripts/seed_cloud_users.py:101-138 computes sign(diff) * diff**2, rescales by its
  largest magnitude and writes shap_value/direction. For a squared-error anomaly
  score, a negative residual still adds positive squared error. Its sign does not
  establish that a feature decreases risk. Even the report's term decomposition
  needs care: the signed/rescaled values do not sum to the actual MSE/normalized score.
- backend/main.py:416 persists cloud explanations only through the administrative
  seeding route. The normal ingest path scores and persists live scores but does not
  compute fresh attributions. Saved explanations may therefore be missing or stale.
- _build_paper.py:323 claims every flagged event uses KernelExplainer. The inspected
  implementation does not support that statement. Technical-report prose and the
  paper generator disagree and must be reconciled before regenerating deliverables.

Two defensible choices: implement real SHAP for the scored cloud vector; or present
accurate per-feature reconstruction-error diagnostics and rarity evidence under
those names. The organizer's current SHAP sentence needs correction until the first
choice is implemented and verified. No explanation should imply proof of causation.

### 3. No attack examples in fitting is narrower than no labels anywhere

cert_ae_full_pipeline.ipynb selects normal users with is_insider==0, fits scaler/AE
on the normal subset, and builds peer groups using the normal cohort. backend/loader.py
uses is_insider and precision_recall_curve to choose its benchmark High threshold.
scripts/evaluate.py reports best F1 at a label-selected threshold. Cloud training
also identifies the normal cohort using is_attacker, though its saved score bounds
use normal validation reconstruction errors.

For a live installation: use a documented baseline collection/contamination policy,
freeze model/scaler/threshold versions before scenario testing, and tune alert budgets
from non-attack operational data. Keep scenario truth for evaluation only. Do not
claim that an unsupervised fitting loss eliminates all baseline-selection assumptions.

### 4. Different feeds have different available evidence

Cloudflare Access authentication records support login investigation, not all actions
inside the protected application. GitHub activity is not a login/audit feed and the
current normalized events have no IP or country. Missing fields must not appear as
negative evidence for takeover. A shared schema does not make source distributions
or semantic features equivalent.

AWS data access demonstrations must use events actually collected: management-event
collection alone does not prove visibility into every S3 object download. Select and
verify the necessary event coverage before promising a mass-download scenario.

## What existing metrics establish

| Saved artifact | Result | Claim boundary |
|---|---|---|
| results/metrics.json | CERT AUROC .9763, AUPRC .8508, best-threshold F1 .7874 | Historical benchmark setup; not measured competition deployment accuracy |
| results/kfold_inductive_metrics.json | CERT out-of-fold AUROC .9588, AUPRC .7657 | Stronger held-out evaluation than the .9763 reference, still CERT |
| results/cloud_kfold_inductive_metrics.json | flaws.cloud mean fold AUROC .7230 +/- .0392; pooled .7098 | File explicitly warns of very limited attacker diversity; not a broad production benchmark |
| results/github_semisynthetic_metrics.json | Rarity detector AUROC .9923 on real background plus injected attacks | Semi-synthetic rarity study; not cloud AE accuracy on real GitHub compromise |

These files were inspected, not rerun. Keep detector, dataset, scoring unit, split,
threshold selection and injected-vs-observed status next to every number used.

## Verification performed in this assessment

A small dependency-light synthetic smoke check passed:

- AWS, Entra, Cloudflare and GitHub sample events normalize to the shared eight fields.
- The rarity function returns all six supported keys.
- Cloud feature aggregation returns the declared 12-feature vector.
- GitHub normalization provides no IP for the Events API sample.

This validates basic parser/feature behavior only. It does not validate completeness,
adversarial inputs, live credentials, the model artifacts, SHAP fidelity or end-to-end
delivery. The earlier full-suite attempts did not produce a current green baseline;
see specs/C1-competition-readiness.md for the environment/setup failure and interrupted rerun.

## Suggested organizer clarification (accurate to present evidence)

Argus is a prototype for investigating unusual account behavior across cloud and SaaS
services. It supports normalization of AWS CloudTrail, Microsoft Entra sign-in,
Cloudflare Access and GitHub activity event formats. Live integration is being
validated for AWS, Cloudflare Access and GitHub; Entra remains supported at parser
level in the current competition scope.

The prototype combines autoencoder anomaly scoring with six interpretable behavioral
signals and an analyst investigation dashboard. Its models are fitted on selected
normal activity without attack examples in the training objective; benchmark labels
have been used for evaluation and some threshold selection. Historical CERT and
CloudTrail evaluations are reported separately from live deployment results.

Current explanation methods differ by detector: the CERT notebook includes SHAP for
an Isolation Forest baseline, while seeded cloud views use reconstruction-residual
diagnostics. Faithful explanations of live autoencoder scores, source-aware AI
guidance, analyst-approved account linking, a cross-source timeline and evidence
coverage indicators are release work in progress. The AI provides suggestions for
human review and does not execute response actions in the inspected workflow.

The intended contribution is a usable, evidence-led investigation workflow for
teams with limited security capacity. Current status and demonstration type: Prototype.

## Release priority to make the intended claims true

1. Independent live mode: no CERT startup requirement, seeded identities or benchmark
   labels in the live dashboard; versioned model/feature/threshold provenance.
2. Protected, real AWS and Cloudflare collectors with duplicate/restart recovery and
   visible source health; GitHub activity accurately named and scoped.
3. Faithful live score explanations and source-aware AI input, with explicit missing
   evidence and no benchmark scenario hints.
4. Verified account mappings and an exact, source-labelled timeline; no automatic
   email-prefix merging or unscoped risk inheritance.
5. Timestamped end-to-end records of benign/suspicious scenarios, separate false-alert
   counts, per-source latency, baseline sufficiency and failure recovery. Small local
   scenarios support a prototype demonstration, not universal detection claims.

## Sources

- NIST IR 8613 initial draft (verified 25 October):
  https://csrc.nist.gov/pubs/ir/8613/ipd
- Cloudflare Access authentication log semantics:
  https://developers.cloudflare.com/cloudflare-one/insights/logs/dashboard-logs/access-authentication-logs/
- GitHub organization audit-log access and webhook alternatives:
  https://docs.github.com/en/enterprise-cloud%40latest/organizations/keeping-your-organization-secure/managing-security-settings-for-your-organization/reviewing-the-audit-log-for-your-organization

The provider documentation links above were checked during this chat. Implementation
evidence comes from the named local sources. No code, deployment or organizer submission
was changed by this audit.
