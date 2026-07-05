# Q1 — Published CERT r4.2 SOTA (2026 snapshot) vs. Argus

## Answer

Argus's label-free autoencoder result (AUROC 0.976, AUPRC 0.851, F1 0.787 at **user-level**, 1000
users / 70 insiders) is still competitive **once granularity is controlled for** — but almost all
recently published "beats" it in raw AUROC/F1 are not doing the same task. The overwhelming
majority of 2024-2026 CERT r4.2 papers report **session-, day-, or week-aggregated** metrics
(effectively hundreds of thousands of mostly-easy-to-separate rows), not one-score-per-user
metrics; several explicitly show that user-level accuracy on Scenario 2 collapses to ~5% even
where session-level accuracy exceeds 95%. No paper found evaluates unsupervised/label-free
detection at the same 1000-user / 70-insider user-level granularity with a higher AUROC than
Argus's 0.976. The closest true label-free comparator (Le & Zincir-Heywood, unsupervised
ensemble, TNSM 2021) reports ~0.90 AUC. On Scenario 2 specifically, no paper — supervised or
unsupervised — reports a strong, credible, user-level result; every source that discusses it
(including Argus's own supervised-ensemble comparison) treats it as the persistently hard,
low-and-slow case, consistent with Argus's own 12/30 (unsupervised) vs. 27/30 (supervised
ensemble) finding. Recommendation: keep the 0.976 claim, but strengthen the paper's positioning
by explicitly calling out the granularity mismatch as the reason raw-number comparisons to most
2024-2026 papers are invalid — this is a defensible, citable point for the viva, not just a
hedge.

## Evidence

- **Granularity is the dominant confound across nearly every recent CERT r4.2 paper found.**
  A 2025 Transformer + User-Based-Sequencing paper reports Accuracy 99.0%, F1 99.29%, AUROC
  100.00% on r4.2 — but this is **session-level** granularity (fixed-size vectors per session, 100
  users total in the test split), not one score per user across the full population. arXiv
  preprint, submitted 30 Jun 2025, not yet published at a venue.
  (https://arxiv.org/html/2506.23446v1, accessed 2026-07-03)
- **A second, independently-confirmed case of the same pattern**: a federated-learning + behavior
  log analysis paper (Scientific Reports, published 1 Jun 2025, vol. 15, article 19214) explicitly
  tested granularity as a variable: **weekly aggregation** gave P/R/F1 ≈ 0.9997 and AUC 0.99,
  beating session-based (4-hour) and daily granularity. The same paper states that on Scenario 2
  specifically, **accuracy was ~5%** without a hand-added rule-based patch — i.e., even a
  near-perfect aggregate score hides near-total failure on the low-and-slow scenario.
  (https://pmc.ncbi.nlm.nih.gov/articles/PMC12127438/, https://www.nature.com/articles/s41598-025-04029-w, accessed 2026-07-03)
- **RMSL (weakly-supervised, robust multi-sphere learning)**, arXiv preprint Aug 2025, reports AUC
  0.9701 and Detection Rate 0.9142 on r4.2, but at **behavior/sequence level**, not user level;
  paper gives no per-scenario breakdown and no user/insider count for the evaluation split. Not
  yet published at a venue. (https://arxiv.org/html/2508.11472v1, accessed 2026-07-03)
- **Insight-LLM** (multi-view LLM fusion), arXiv preprint Sep 2025, reports Precision 0.9631,
  Detection Rate 0.9683, F1 0.9712 nominally as "user-level," but the fetched preprint text did not
  surface the exact evaluation-split definition (user count, per-scenario numbers) in the accessible
  sections — flagged as **unverified granularity claim**, needs primary-source confirmation before
  citing as a true apples-to-apples user-level comparator.
  (https://arxiv.org/pdf/2509.01509, accessed 2026-07-03)
- **Closest genuine label-free/unsupervised comparator**: Le & Zincir-Heywood, "Anomaly Detection
  for Insider Threats Using Unsupervised Ensembles" (IEEE TNSM, 2021) — combines AE, Isolation
  Forest, LODA, LOF on CERT r4.2, reports **~0.90 AUC**, which is below Argus's 0.976. This is the
  most-cited genuinely-unsupervised prior work found across all searches, and it predates and is
  still cited by 2024-2025 papers as the unsupervised baseline to beat.
  (https://web.cs.dal.ca/~lcd/pubs/TNSM2021.pdf; corroborated via search snippet reporting "90% AUC on CERT R4.2," accessed 2026-07-03)
- **Meta-ensemble classifier (Hall et al. 2019)**, day-level, supervised stacked ensemble: Accuracy
  96.2%, TPR 0.78, FPR 0.03, AUC 0.988 — higher AUC than Argus but (a) day-level not user-level and
  (b) supervised (uses ground-truth labels for training), so not a like-for-like comparison to a
  label-free method. (via emergentmind.com/topics/cert-insider-threat-dataset survey summary, accessed 2026-07-03; original Hall et al. 2019 not independently re-verified this session — single-source, flag as medium confidence)
- **No paper found publishes a strong, credible Scenario-2-specific result** (supervised or
  unsupervised) at user-level granularity. Every source that discusses Scenario 2 in detail
  (the Scientific Reports 2025 federated-learning paper, and Argus's own TECHNICAL_REPORT.md
  §"Per-scenario detection is uneven") converges on the same finding: Scenario 2 (job-site
  browsing + gradual thumb-drive IP theft) is a low-and-slow, relative-deviation pattern that
  aggregate/session-level scores mask and that user-level unsupervised methods substantially
  under-detect. Argus's own internal comparison: unsupervised AE 12/30 (recall ≈0.40) vs.
  supervised stacking ensemble 27/30 on the same user population — this is an **internal Argus
  result, not an external published benchmark**; it should not be cited as "prior work beats
  Scenario 2," since it's Argus's own ablation. (TECHNICAL_REPORT.md lines 471-479, QNA_PREP.md
  Q7/Q24, checked 2026-07-03)
- **Sivakrishna et al., "An Efficient Insider Threat Detection Framework Using Bayesian-Optimized
  XGBoost," Security and Privacy (Wiley), 2025**: reports very high numbers (Acc 99.0%, F1 96.6%,
  AUC 99.7%) but per a companion 2026 paper by the same authors, their evaluation dataset is
  **CERT r5.2, not r4.2** — different scenario set (4 scenarios, 2000 users, 30 insiders) — so this
  is **not directly comparable** to Argus's r4.2 result at all, despite superficially resembling a
  "beats Argus" headline number. Full text paywalled (HTTP 402); granularity not independently
  confirmed — flag low confidence on this entry specifically.
  (https://onlinelibrary.wiley.com/doi/abs/10.1002/spy2.70122, search-snippet corroboration only, accessed 2026-07-03)

## Impact on Argus

- No change needed to the headline 0.976 AUROC / 0.851 AUPRC / 0.787 F1 claim — it remains
  defensible and, on a like-for-like (label-free, user-level) basis, is at or above the strongest
  comparator found (Le & Zincir-Heywood ~0.90 AUC).
- Strengthen TECHNICAL_REPORT.md / viva prep with an explicit **granularity caveat paragraph**:
  most recent (2024-2026) CERT r4.2 papers report session/day/week-aggregated metrics that are not
  comparable to user-level scores, and cite the Scientific Reports 2025 paper's own internal
  ablation (weekly > daily > session granularity, all ≫ true per-user difficulty) as third-party
  confirmation that this confound is real and known in the literature, not an Argus rationalization.
- Do NOT cite "27/30 supervised Scenario 2" as beating any external published work — QNA_PREP.md
  and TECHNICAL_REPORT.md already correctly scope this as an internal ablation; confirmed correct,
  no edit needed, but worth double-checking in the viva that this is presented as "our own
  supervised comparison," not "the published SOTA for Scenario 2."
- Flag for future work / defensive citation: no one has published a strong Scenario 2 result at
  user-level granularity as of this search (2026-07-03) — this is a genuine open gap in the
  literature that supports Argus's positioning of Scenario 2 / low-and-slow as future work (CUSUM,
  time-aware detection) rather than a solved problem Argus failed to match.

## Confidence

**Medium-high** on the central claim (granularity mismatch invalidates most head-to-head AUROC
comparisons; Argus is competitive among genuine label-free/user-level comparators). **Medium** on
completeness — CERT r4.2 literature is large and fast-moving (new arXiv preprints roughly monthly);
this brief covers the results surfaced by ~10 targeted searches plus 6 full-text fetches, not an
exhaustive systematic review. Two entries are flagged individually as lower confidence: Insight-LLM's
"user-level" framing (granularity unverified from accessible preprint text) and the Sivakrishna
XGBoost paper (r5.2 vs r4.2 distinction relies on a companion-paper cross-reference, not the
paywalled primary source). What would change my mind: a peer-reviewed (non-arXiv) paper explicitly
stating "one prediction per user, evaluated against the 70 known insiders out of 1000 users" with
AUROC > 0.976, or a credible Scenario-2-only user-level result above ~0.60 recall — neither was
found in this search.
