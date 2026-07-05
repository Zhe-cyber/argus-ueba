# Q2: Has Wazuh/OpenUBA/HELK (or a new entrant) shipped ML-based or multi-source UEBA since mid-2025, invalidating Table 2?

## Answer

No row in the paper's Table 2 (Wazuh / OpenUBA / HELK vs. Argus) is invalidated as of July 2026.
Wazuh shipped four minor releases since mid-2025 (4.12.0 May 2025 through 4.14.6 July 2026) adding
an IT Hygiene dashboard, endpoint/user/group inventory, hot-reload rules, and — most relevant to
this question — a Microsoft Graph dashboard for ingesting Azure/Entra ID and M365 logs, but none of
these add per-user ML behavioural baselining, cross-source identity-unified scoring, or alert
explanation; Wazuh's own community still has an open, unresolved "add UEBA" feature request, and
its "anomaly detection" is a generic OpenSearch/Random-Cut-Forest plugin over aggregate metrics
(unchanged since 2023), not a per-user behavioural model. OpenUBA and HELK are both effectively
stalled — OpenUBA is still tagged [BETA]/v0.0.2 with no substantive commit activity found past
December 2024, and HELK's own README still self-describes as "Alpha," with its last meaningful
stack-update PR merged May 2024 and its most recent release tag dating to 2019 — so the "Partial /
Limited" ratings the paper gives them remain accurate, if anything now understating their neglect.
The one finding worth carrying into the paper/plan is outside Table 2's three named rows: Splunk
formally announced end-of-sale for standalone Splunk UBA on 2025-12-12 (end-of-life 2027-01-31),
folding UEBA into Splunk Enterprise Security Premier — the differentiation table in FYP2_PLAN.md
names "Splunk UBA" by product name, and that product is now being sunset as a standalone SKU, which
is a factual staleness risk (not a capability-parity risk) an examiner could raise. No new
open-source, SHAP-explainable, SME-priced UEBA entrant was found; the one plausible "why not X"
candidate is Graylog Security's UEBA/anomaly-detection module, but it is a paid Enterprise/Security
add-on (from ~US$1,550/month), not free, so it does not undercut Argus's cost/deployability
differentiation — it does, however, strengthen the case for explicitly naming Graylog in the related-
work discussion so a viva examiner can't claim it was overlooked.

## Evidence

- Wazuh 4.x release cadence since mid-2025: 4.12.0 (2025-05-07), 4.13.0 (2025-09-18), 4.13.1
  (2025-09-24), 4.14.0 (2025-10-23), 4.14.1–4.14.6 (Nov 2025–Jul 2026, patch releases). Source:
  [Wazuh 4.x release notes index](https://documentation.wazuh.com/current/release-notes/index-4x.html) (accessed 2026-07-04).
- Wazuh 4.13.0 headline features: IT Hygiene dashboard, threat-intel CDB lists, hot-reload of
  decoders/rules, Windows UNC/NetNTLMv2 hardening — no UBA/ML/behavioural-baseline feature. Source:
  [Introducing Wazuh 4.13.0](https://wazuh.com/blog/introducing-wazuh-4-13-0/) (2025-09/10, accessed 2026-07-04).
- Wazuh 4.14.0 headline features: unified inventory model (incl. users/groups), agent config
  hot-reload, and a new **Microsoft Graph dashboard** for M365/Azure cloud service activity — a
  log-visualisation add, confirmed (via Wazuh's own Graph-API docs) to land ingested events in the
  generic "Security Events" tab, not a per-user behavioural model or cross-source identity join.
  Source: [Wazuh 4.14.0 release notes](https://documentation.wazuh.com/current/release-notes/release-4-14-0.html);
  [Monitoring Microsoft Graph services with Wazuh](https://documentation.wazuh.com/current/cloud-security/azure/monitoring-ms-graph.html) (accessed 2026-07-04).
- Wazuh's "Anomaly Detection" capability is the OpenSearch Random Cut Forest plugin bundled since
  Wazuh 4.8 — operates on aggregate index metrics (avg/count/sum/min/max per field), not identity-
  scoped user profiles; the descriptive blog post predates the review window (dated 2023-10-12) and
  has not been materially updated since. Source:
  [Enhancing IT security with anomaly detection in Wazuh](https://wazuh.com/blog/enhancing-it-security-with-anomaly-detection/) (accessed 2026-07-04).
- A Wazuh community feature request explicitly asking for User Behavior Analytics support
  (web/email/session/command monitoring with anomaly detection against behavioural baselines)
  remains open with no maintainer commitment. Source:
  [wazuh/wazuh GitHub issue #14446](https://github.com/wazuh/wazuh/issues/14446) (opened 2022-07-28,
  status open as of 2026-07-04).
- Wazuh's own AI initiatives in 2025–2026 (LLM threat-hunting chatbot via self-hosted Llama3/Ollama,
  June 2025; "agentic AI" preview) are community/DIY tutorials or early previews, not shipped
  per-user behavioural-scoring product features. Source:
  [Leveraging AI for threat hunting in Wazuh](https://wazuh.com/blog/leveraging-artificial-intelligence-for-threat-hunting-in-wazuh/) (2025-06-13);
  [A Sneak Peak at Agentic AI in Wazuh](https://wazuh.com/blog/a-sneak-peak-at-agentic-ai-in-wazuh/) (accessed 2026-07-04).
- OpenUBA (GACWR/OpenUBA): still labelled `[BETA]`, version v0.0.2 in its README; forks mirror a
  `[PRE-ALPHA]` label; most recent visible issue-tracker activity is 2024-12-15; no archived banner,
  but no evidence of substantive commits/releases in 2025–2026. It remains a model-agnostic
  scaffold (sklearn/PyTorch/TensorFlow template models a user must register and train themselves),
  not a working out-of-the-box behavioural-baseline product — consistent with the paper's "Partial"
  rating. Source: [github.com/GACWR/OpenUBA](https://github.com/GACWR/OpenUBA) and its
  [README](https://github.com/GACWR/OpenUBA/blob/master/README.md) (accessed 2026-07-04).
- HELK (Cyb3rWard0g/HELK): README self-describes current status as "Alpha" ("we haven't yet tested
  the system with large data sources and in many scenarios"); last substantive stack-update PR
  (#592, ELK upgrade to 8.13.4) merged 2024-05-20; most recent release tag found dates to 2019; no
  archived banner but activity has effectively stalled. Source:
  [github.com/Cyb3rWard0g/HELK](https://github.com/Cyb3rWard0g/HELK),
  [PR #592](https://github.com/Cyb3rWard0g/HELK/pull/592) (accessed 2026-07-04).
- Splunk formally announced end-of-sale for standalone Splunk User Behavior Analytics (UBA) on
  **2025-12-12**, with end-of-life/support on **2027-01-31**; UEBA capability is being folded into
  Splunk Enterprise Security Premier rather than sold as a separate product going forward. Source:
  [Splunk UBA end-of-sale/EOL announcement](https://help.splunk.com/en/security-offerings/splunk-user-behavior-analytics/release-notes/5.4.5/additional-resources/splunk-announces-end-of-sale-and-end-of-life-for-standalone-splunk-user-behavior-analytics-software)
  and [Splunk UBA EOL FAQ PDF](https://www.splunk.com/en_us/pdfs/product-briefs/splunk-uba-end-of-sale-faq.pdf) (accessed 2026-07-04).
- Exabeam remains commercially priced with no free/SME tier: pricing starts around US$250/monitored-
  user/year, with UEBA sold as a 20–35% premium module on top of a Foundation/Analytics tier —
  materially unchanged in structure from a "black-box, enterprise-priced" positioning. Source:
  [Exabeam Pricing 2026](https://siemcostcalculator.com/exabeam-pricing) (accessed 2026-07-04).
- Graylog Security/Enterprise ships genuine ML-based UEBA/anomaly detection (continuous behavioural
  baselining, insider-threat/credential-misuse detection) but this is explicitly a **paid** tier —
  Graylog Security starts at ~US$1,550/month for 10 GB/day — while "Graylog Open" (free) does not
  include UEBA/anomaly detection. This is a legitimate open-source-adjacent tool an examiner could
  name, but it does not undercut Argus's free/SME-cost differentiation. Source:
  [Graylog UEBA Anomaly Detection](https://graylog.org/feature/anomaly-detection/);
  [Graylog Pricing](https://graylog.org/pricing/) (accessed 2026-07-04).
- No new open-source, actively-maintained, SHAP/XAI-native UEBA project with real adoption was
  found. The closest hits are single-author academic/portfolio repos (e.g. Isolation Forest +
  XGBoost + SHAP on CERT r4.2, no ongoing maintenance, no multi-source ingestion, no deployment
  story) — not comparable products, and not something a well-prepared examiner would cite as a
  missed competitor. Source: search sweep of GitHub topics `ueba`/`user-behavior-analytics` and
  aimultiple.com's "Top Open Source UEBA Tools" survey (updated 2026-03-26), which itself still
  lists only OpenUBA, Graylog, and Wazuh (as "complementary") as open-source-adjacent options.
  [aimultiple: Top Open Source UEBA Tools](https://aimultiple.com/open-source-ueba) (accessed 2026-07-04).

## Impact on Argus

- **No change required to the three Table 2 rows (Wazuh, OpenUBA, HELK)** — all six capability
  ratings ("No"/"Partial"/"Limited"/"Yes") remain accurate as of 2026-07. No row needs a value flip.
- **FYP2_PLAN.md differentiation table, row 1 ("Splunk UBA / Exabeam")**: the product name "Splunk
  UBA" is now stale — it is end-of-sale (Dec 2025) and being retired as a standalone product by
  Jan 2027. Recommend the planner either (a) relabel the column "Splunk ES Premier UEBA / Exabeam"
  or (b) add a footnote acknowledging the Splunk UBA→ES Premier consolidation, so a viva examiner
  reading the slide can't flag it as outdated. This is a labelling fix, not a capability-parity
  concession — Splunk's successor product is still enterprise-priced and black-box.
  I have not edited FYP2_PLAN.md or the paper — that call belongs to the planner per protocol.
- **Related-work / literature-review section of the paper**: worth the planner considering an
  explicit one-sentence mention of Graylog Security's paid UEBA module alongside Wazuh/OpenUBA/HELK,
  specifically to pre-empt the "why didn't you compare against Graylog?" viva question — the answer
  ("it's a commercial paid add-on with enterprise SIEM-tier pricing, not free/SME-deployable") is
  favourable to Argus's positioning but only if it's stated rather than left for the examiner to
  raise cold.
- **No change to Table 2's underlying claims about explainability or per-user baselining** — still
  true that none of Wazuh/OpenUBA/HELK ship SHAP-style attribution or an LLM explanation layer.
- **No new dataset or evaluation implication** — this question is about competitor capability, not
  evaluation methodology; no action needed in results/.

## Confidence

**High** for Wazuh, OpenUBA, HELK, Exabeam, and the Splunk UBA end-of-sale finding — each is
corroborated by either a primary vendor source (Wazuh's own release notes/docs, Splunk's own EOL
announcement page + FAQ PDF) or repo-level evidence (README self-description, issue tracker, PR
history) checked directly, and cross-checked against at least one independent secondary source
(aimultiple.com survey, pricing aggregators) for consistency.

**Medium** for "no new open-source UEBA entrant exists" — this is an absence claim from a search
sweep, not an exhaustive registry check; a genuinely new, low-visibility project could exist that
didn't surface in search. What would change my mind: a GitHub repo with >500 stars, commits within
the last 3 months, and a documented per-user ML scoring pipeline that the current sweep missed —
worth a re-check in another 6–12 months as part of the standing beat rather than treating this as
permanently closed.
