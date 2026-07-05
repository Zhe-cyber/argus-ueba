# Q5 — Label-free threshold calibration methods for W4's anomaly-score cutoff

**Question:** What is citable for W4's method choice on setting a risk threshold over an
anomaly score without labels? Cover alert-budget/percentile, EVT/POT (SPOT/DSPOT),
Gaussian/robust-statistics tail methods, and contamination-rate assumptions
(IsolationForest-style). What do SOTA UEBA/anomaly papers use for their operating point,
and is any of this "best practice" vs. just "pick a percentile"?

## Answer

There is no single agreed-upon, provably-optimal way to set a threshold on an unlabelled
anomaly score — the honest state of the field (both academic and commercial) is that
**percentile/alert-budget thresholding is the de facto operational default**, EVT/POT
methods (SPOT/DSPOT, Siffer et al., KDD 2017) are the most theoretically principled
label-free alternative and are explicitly designed for exactly this streaming,
no-ground-truth setting, robust-statistics tail rules (MAD-based modified z-score,
Iglewicz & Hoaglin 1993) are a defensible closed-form fallback when a distributional
tail model isn't worth the engineering cost, and contamination-rate parameters (as in
scikit-learn's `IsolationForest`) are a special case of percentile thresholding that
inherits all its weaknesses (a rate you must still guess) without any of its
transparency (the number is buried in model fitting rather than exposed as an
analyst-tunable knob). Commercial UEBA products (Exabeam, Microsoft Sentinel) do not
use anything more principled than a tunable default score threshold with guidance to
"adjust based on operational feedback" — i.e., production practice already is
percentile/budget-style calibration, not EVT. For W4, a percentile / top-N alert-budget
threshold as the primary configurable knob, validated against the CERT label-optimal F1
threshold gap (already planned), with an EVT/POT (SPOT) method as a cited "more
principled" alternative discussed in the study (implemented if time allows, or left as
future work with the theory correctly attributed) is the defensible, citable position.

## Method families, assumptions, and citations

### 1. Alert-budget / top-K% percentile thresholding

- **What it is:** pick the threshold as the Nth percentile of the observed score
  distribution (e.g., flag the top 1-5% highest-scoring user-days) so alert volume is
  capped to what analysts can triage, independent of the score's absolute scale.
- **Assumptions:** none about the score's parametric distribution; implicitly assumes
  the *rate* of true anomalies in the scored population is roughly stable and close to
  the chosen percentile, and that recent history is a fair baseline for "normal."
- **When appropriate for per-user UEBA:** very appropriate as an *operational* cap —
  it directly encodes the SOC's real constraint (finite analyst hours) rather than a
  statistical property of the score. Well suited when different users have different
  raw score scales, since ranking bypasses that problem. Weak when the true anomaly
  rate shifts over time (a fixed top-K% will always alert on K%, masking a period of
  organisation-wide compromise where more than K% of users are genuinely anomalous, or
  wasting analyst time when the true rate is near zero).
- **Canonical citation / grounding:** this is not attributed to one paper — it is
  standard IDS/SOC operating practice. Closest formal treatment: percentile-of-training-
  distribution thresholding is explicitly named as the standard label-free baseline in
  anomaly-detection benchmarking literature, e.g. discussion of "classify a test sample
  as anomalous if its score exceeds a fixed percentile (e.g., 95th) of the training
  score distribution" in recent unsupervised-threshold-selection work (arXiv:2210.01078,
  *Unsupervised Model Selection for Time-Series Anomaly Detection*, 2022, still cited as
  the reference framing as of 2025-2026 benchmarking papers such as arXiv:2506.20574,
  *Benchmarking Unsupervised Strategies for Anomaly Detection in Multivariate Time
  Series*, June 2025). For the SOC/alert-budget framing specifically, cite general
  SOC-capacity literature (analyst alert fatigue / triage-capacity studies) rather than
  a single anomaly-detection paper — the "top-K% to cap alert volume" framing is an
  operations constraint, not a statistical method, and should be cited as such in the
  paper (do not over-claim a formal citation exists for the budget-capping rationale
  itself).

### 2. Extreme Value Theory / Peaks-Over-Threshold — SPOT / DSPOT

- **Canonical citation:** Siffer, A., Fouque, P.-A., Termier, A., & Largouët, C.
  "Anomaly Detection in Streams with Extreme Value Theory." *Proceedings of the 23rd ACM
  SIGKDD International Conference on Knowledge Discovery and Data Mining (KDD '17)*,
  Halifax, Nova Scotia, Canada, August 2017. DOI: 10.1145/3097983.3098144.
  (verified via ACM DL listing and the KDD 2017 program page, 2026-07-04)
- **What it assumes:** the tail of the score distribution above a (moderate) initial
  threshold follows a Generalized Pareto Distribution (GPD) — this is the
  Pickands–Balkema–de Haan theorem's asymptotic result, not an assumption on the whole
  distribution. SPOT fits the GPD tail online via the initial batch, then updates
  incrementally. DSPOT extends SPOT with a moving-average drift term to handle
  non-stationary streams (local trend removed before applying SPOT to the residual).
  The only user-set parameter is a risk level `q` (target false-alarm probability), from
  which the algorithm *derives* the numeric threshold — this is the "no hand-set
  threshold" pitch of the paper.
- **When appropriate for a per-user UEBA anomaly score:** well matched to a streaming,
  non-stationary per-user score series (exactly Argus's setting: one score/day per
  user, drifting baseline). DSPOT specifically targets concept drift, which matches the
  W5 "active hours drift over time" problem. Caveat: GPD tail-fitting needs a
  reasonable amount of tail data per stream to be stable — for a UEBA score computed
  *per user* with only weeks of history, fitting a per-user GPD tail is likely too
  data-hungry; it is more defensible fit *globally* across all users' scores (pooled
  tail) or per user-cohort, which changes what "anomalous" means (population-relative
  vs. self-relative). This is a real design decision W4 needs to make explicit, not
  paper over.
- **Adoption signal:** SPOT/DSPOT is the most-cited EVT-for-streaming-anomalies paper
  (KDD 2017, cited in numerous later time-series anomaly papers, e.g. it is used as a
  benchmark POT baseline in TranAD (arXiv:2201.07284) and multiple 2023-2025 time-series
  anomaly benchmarks) — it is the correct "principled" citation to reach for, but note
  it targets univariate streaming series, so applying it to a scalar per-user anomaly
  score (already a 1-D reduction of the 71-dim AE reconstruction error) is a natural fit
  architecturally.

### 3. Gaussian / robust-statistics tail rules (mean+kσ, MAD-based modified z-score)

- **Mean+kσ:** assumes (approximate) normality of the score distribution; threshold =
  μ + kσ (commonly k=2 or 3). Fails badly if the score distribution is heavy-tailed or
  skewed — which reconstruction-error-style AE scores typically are (bounded below at
  0, right-skewed) — because the mean and σ are themselves inflated/distorted by the
  very outliers you're trying to detect (no robustness to contamination).
- **MAD-based modified z-score:** z_m = 0.6745 × (x − median) / MAD; flag |z_m| > 3.5.
  **Canonical citation:** Iglewicz, B., & Hoaglin, D. C. (1993). *How to Detect and
  Handle Outliers*. ASQC Basic References in Quality Control, Vol. 16, American Society
  for Quality Control. The 3.5 cutoff and the 0.6745 consistency constant come from this
  reference (confirmed via multiple statistics references, 2026-07-04); it is the
  standard formal citation for the "modified z-score" rule used across outlier-detection
  tooling.
- **When appropriate for per-user UEBA:** the *median/MAD* robust version is
  legitimate and cheap when you need a fast, distribution-light closed-form rule with a
  known breakdown point (MAD tolerates up to 50% contamination before breaking, i.e. is
  far more contamination-resistant than mean/σ). It is a reasonable **fallback for
  early days of a user's history** before enough data exists for either a percentile
  rank or a GPD tail fit to be stable (cold-start problem — directly relevant to Argus's
  per-user cold-start weeks). Plain mean+kσ should not be used on a right-skewed,
  non-negative reconstruction-error score without first log-transforming or otherwise
  correcting skew; if cited at all in the paper, cite it as the naive baseline being
  improved upon, not the chosen method.

### 4. Contamination-rate assumptions (e.g. `sklearn.ensemble.IsolationForest(contamination=...)`)

- **What it assumes:** the practitioner supplies (or the default `'auto'` heuristic
  estimates) the fraction of the dataset that is anomalous; the model then sets its
  internal `offset_` so that exactly that fraction of *training* scores fall below the
  decision threshold. This is mathematically identical to percentile thresholding —
  `contamination=0.05` is the same operation as "threshold = 95th percentile of
  training scores" — just applied at fit time and hidden inside the estimator API
  rather than exposed as a separate analyst knob.
- **Pitfalls (documented, 2025-2026 sources):** (a) there is no principled way to know
  the true contamination rate in a UEBA setting — insider-threat base rates are not
  observable without labels, which is the exact problem threshold calibration is trying
  to solve, so `contamination` just relocates the unknown rather than resolving it; (b)
  scikit-learn's own docs and multiple practitioner guides (2025) warn that setting
  contamination too high or too low directly and linearly distorts precision/recall,
  with no cross-validation possible without labels; (c) recent academic work explicitly
  treats "contamination factor estimation" as its own open research problem — e.g.
  Perini, L., Vercruyssen, V., & Davis, J., *Estimating the Contamination Factor's
  Distribution in Unsupervised Anomaly Detection*, ICML 2023 (arXiv:2210.10487) proposes
  a Bayesian posterior over the unknown contamination factor precisely because no
  reliable point-estimate method existed — this is the strongest citation to use in the
  paper for "the contamination-rate assumption is itself an open problem, not a solved
  input," directly supporting why Argus does not adopt a contamination-parameter model
  as its threshold method.
- **When (not) appropriate for Argus:** not recommended as W4's primary method — it
  offers no advantage over directly-specified percentile thresholding (same math) while
  adding a layer of indirection that is harder to explain in the viva ("why 5%
  contamination and not 2%?" has no better answer than "why the 95th percentile and not
  the 98th?", but the percentile framing is more legible to a non-ML audience and maps
  directly onto the "alert budget" business framing Argus already uses).

## What SOTA UEBA / anomaly-detection papers actually use for their operating point

- **Commercial UEBA (not academic, but the closest thing to "production ground
  truth"):** Exabeam's documented risk-scoring uses a sigmoid-normalised composite risk
  score (0-100) with a **default alert/incident threshold of 90**, explicitly tuned by
  "adjust based on operational feedback and incident analysis" (Exabeam Threat Center
  docs, accessed 2026-07-04). Microsoft Sentinel UEBA emits a 0-1 anomaly deviation
  score plus a separate 0-10 "investigation priority" score blending self-deviation,
  peer comparison, and blast radius, with no published statistical calibration method
  disclosed publicly (Microsoft Learn, *Anomalies detected by the Microsoft Sentinel
  machine learning engine*, accessed 2026-07-04). Neither vendor publishes a
  statistically principled label-free calibration method — both use a fixed default
  threshold with a "tune it operationally" disclaimer. This is directly citable
  evidence that **percentile/budget-style manual or semi-manual thresholding, not EVT,
  is current production practice** in the commercial UEBA space.
- **Academic anomaly-detection benchmarks:** the closest thing to a "best practice"
  consensus in 2024-2025 literature is to report a *label-free* threshold (fixed
  percentile of the training-score distribution, or a parametric-tail rule) *alongside*
  a "F1-optimal"/"F1-max" threshold computed by cheating with test labels, explicitly to
  quantify the gap between what's achievable label-free and the theoretical ceiling
  (see framing in arXiv:2210.01078 and echoed in 2025 benchmarking work, arXiv:2506.20574).
  **This is exactly the design W4 already has planned** — "measured gap vs the
  label-optimal F1 threshold (0.0662) on CERT" — which matches current benchmarking best
  practice for how to present a label-free threshold choice honestly, rather than
  claiming the label-free threshold itself is optimal.
- **Insider-threat-specific papers on CERT:** none of the CERT-dataset papers surveyed
  (Bayesian GMM unsupervised approach, arXiv:2211.14437; transformer/user-sequencing
  approach, arXiv:2506.23446; Facade deep contextual AD, arXiv:2412.06700) report using
  EVT/POT for their operating point — they report metrics (AUROC, recall at a fixed
  FPR, or precision/recall curves) without necessarily committing to one deployed
  threshold, or they pick a threshold via a fixed percentile of the anomaly-score
  distribution. **No CERT-benchmark paper found citing SPOT/DSPOT for the threshold
  step** — EVT/POT adoption in insider-threat literature specifically appears to be
  effectively zero as of 2026-07; it is much more established in network/infrastructure
  streaming-metrics anomaly detection (its original KDD 2017 use case) than in
  per-user behavioural UEBA. This should be stated as a gap/opportunity in the paper,
  not implied to be already standard in insider-threat detection.
- **Verdict on "principled label-free calibration vs. pick-a-percentile":** the
  honest answer is **contested/no consensus** — EVT/POT is the more theoretically
  grounded method and is cited as such in general streaming-anomaly literature, but it
  is not adopted as standard practice in either commercial UEBA or the CERT-benchmark
  academic literature specifically; percentile/budget thresholding remains the
  dominant real-world choice precisely because it is simpler to explain, tune, and
  audit (all properties that matter for an SME-facing, glass-box product like Argus).
  Do not claim in the paper that EVT/POT is "best practice" in UEBA — it is "the more
  principled research-grade alternative, under-adopted in this specific sub-field."

## Recommendation for W4's method choice

1. **Primary, ship this:** top-K% alert-budget percentile thresholding over the
   `_live_risk_tier` score, exactly as already scoped in UPGRADE_PLAN.md W4 item 1
   (configurable N without retraining, no distributional assumption, directly maps to
   the SOC-capacity narrative already in the paper). Cite the percentile-of-training-
   distribution framing from arXiv:2210.01078 / arXiv:2506.20574 for the "this is the
   standard label-free baseline in the anomaly-detection literature" claim, and cite
   Exabeam/Microsoft Sentinel documentation as evidence this matches current commercial
   UEBA practice (not a weaker option than what's already deployed in the market).
2. **Study the CERT gap as already planned (W4 item 2):** report the label-free
   percentile threshold's F1 against the label-optimal 0.0662 threshold, framed exactly
   as the benchmarking literature above frames it (gap-to-optimal, not "we found the
   best threshold").
3. **If time budget allows, add SPOT (not DSPOT) as a secondary/contrasting method in
   the study**, applied on the pooled (not per-user) score distribution to have enough
   tail data, explicitly cited to Siffer et al. (KDD 2017), to let the paper say "we
   also evaluated the more theoretically principled EVT/POT approach and quantify how
   it compares to the simpler percentile rule" — this materially strengthens the W4
   section for the viva (shows awareness of the SOTA alternative rather than picking
   the easy option by default) even if percentile thresholding is what ships in the
   product.
4. **Explicitly reject** contamination-parameter-style thresholding as the *chosen*
   method (cite Perini et al., ICML 2023, arXiv:2210.10487, for why the contamination
   rate is itself an unresolved estimation problem) and **cite but do not adopt** plain
   mean+kσ (present only as the naive baseline the MAD-based or percentile method
   improves on). MAD/modified-z-score (Iglewicz & Hoaglin, 1993) is worth keeping in
   the back pocket specifically for the **per-user cold-start** case (first 1-2 weeks
   of a new user's history, too little data for a stable percentile rank or GPD tail
   fit) — flag this as a design note for W4/W5, not a separate deliverable.

## Confidence

**Medium-high** on the *taxonomy and citations* (all four families and their canonical
papers are well-attested across 2+ independent sources each, dated 2026-07-04 search).
**Medium** on the *"no consensus / contested" verdict for UEBA specifically* — this is
based on a survey of the most-searchable CERT-dataset papers and two commercial UEBA
vendors' public docs, not an exhaustive systematic review; it is possible a niche
insider-threat paper using SPOT/DSPOT exists but simply doesn't surface in general web
search. What would change this assessment: a discovered CERT-benchmark or production
UEBA paper that explicitly reports EVT/POT as its deployed threshold method with
quantified results — this would upgrade EVT/POT from "principled but under-adopted" to
"emerging best practice," which would argue for making SPOT the primary rather than
secondary method in W4.

## Sources

- Siffer, A., Fouque, P.-A., Termier, A., Largouët, C. (2017). *Anomaly Detection in
  Streams with Extreme Value Theory*. KDD '17. https://dl.acm.org/doi/10.1145/3097983.3098144
  and https://www.kdd.org/kdd2017/papers/view/anomaly-detection-in-streams-with-extreme-value-theory
- Iglewicz, B., Hoaglin, D. C. (1993). *How to Detect and Handle Outliers*. ASQC —
  summarised via https://metricgate.com/docs/iglewicz-hoaglin-modified-z-outliers/ and
  https://standarddeviationcalculator.app/learn/modified-z-score-outlier-detection
  (accessed 2026-07-04)
- Perini, L., Vercruyssen, V., Davis, J. (2023). *Estimating the Contamination Factor's
  Distribution in Unsupervised Anomaly Detection*. ICML 2023. https://arxiv.org/abs/2210.10487
- *Unsupervised Model Selection for Time-Series Anomaly Detection* (2022).
  https://arxiv.org/pdf/2210.01078 — percentile-of-training-distribution framing
- *Benchmarking Unsupervised Strategies for Anomaly Detection in Multivariate Time
  Series* (June 2025). https://arxiv.org/html/2506.20574v1
- scikit-learn `IsolationForest` docs (contamination parameter):
  https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html
  (accessed 2026-07-04)
- Exabeam Threat Center — risk score threshold docs:
  https://docs.exabeam.com/en/threat-center/all/threat-center-guide/get-started-with-threat-center/threat-center-risk-score.html
  and https://community.exabeam.com/s/article/Understanding-Risk-Score (accessed 2026-07-04)
- Microsoft Learn — *Anomalies detected by the Microsoft Sentinel machine learning
  engine*: https://learn.microsoft.com/en-us/azure/sentinel/anomalies-reference
  (accessed 2026-07-04)
- CERT-dataset unsupervised approaches surveyed: Bayesian GMM
  (https://arxiv.org/pdf/2211.14437), Transformer user-sequencing
  (https://arxiv.org/html/2506.23446v1), Facade deep contextual AD
  (https://arxiv.org/pdf/2412.06700) — none report EVT/POT for threshold selection
  (accessed 2026-07-04)
