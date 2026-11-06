# Q7: Triage-time user-study designs with tiny n (<5) — what's defensible for W8 ECLOGIC study

## Answer

Small-n (n=2–5), within-subject, think-aloud usability studies are standard, publishable practice
in both the general HCI/usability literature and specifically in security-alert-triage research —
the closest domain precedent (NDSS USEC 2025) used exactly 5 SOC analysts with a think-aloud
protocol on a real SOC's alerts, and the field's own methodology papers (Caine 2016, Nielsen 2000)
establish that n as low as 1–5 is routine and accepted at top venues *provided the study is framed
as a formative/qualitative case study, not a powered hypothesis test*. At n=2–3 (ECLOGIC's realistic
headcount), the honest and defensible move is: within-subject counterbalanced design (each engineer
does both WITH and WITHOUT SHAP+LLM conditions on matched alert batches), report per-participant
paired results and descriptive statistics (median/IQR, direction-of-effect consistency) as the
primary evidence, supplement with think-aloud/interview qualitative coding, and report any
Wilcoxon/effect-size numbers explicitly labelled as *not powered for significance* rather than
citing a p-value as if it means anything — because at n<6 a paired Wilcoxon signed-rank test cannot
mathematically reach p<.05 two-tailed, so presenting one without that caveat would be a viva
liability, not an asset. This is a well-trodden, low-risk framing: it is exactly what Nielsen's
"discount usability" tradition and the closest security-alert-triage precedents already do.

## Precedents (n, task, metrics, venue/date)

| Study | n | Task | Metrics | Statistical treatment | Venue/date |
|---|---|---|---|---|---|
| Nielsen & Landauer (1993); Nielsen "Why You Only Need to Test with 5 Users" (2000) | 5 (rule of thumb; formula models diminishing returns from 1–15) | General usability testing, any product | Problem-detection count (qualitative) | None — explicitly argues against powered stats; positions as discovery/discount testing | NN/g, 2000 (foundational, cited constantly in 2024–2026 UX lit — [Trymata 2025 recap](https://trymata.com/blog/5-user-rule-for-user-testing/), [NN/g via Aguayo 2025](https://aguayo.co/en/blog-aguayo-user-experience/nielsen-norman-theory-usability-testing-5-users/)) |
| Caine, "Local Standards for Sample Size at CHI" | Survey of all CHI 2014 papers: range 1–916,000; **qualitative-study average n=14**, but single-digit n common | N/A (meta-methodology) | N/A | Argues for "local standards" (what's normal *for this method/venue*) over a universal rule; legitimizes small n when method-appropriate | CHI 2016 ([ACM DL](https://dl.acm.org/doi/10.1145/2858036.2858498), [PDF](https://hatlab.org/wp-content/uploads/2017/09/caine-2016.pdf)) |
| "A Field Study to Uncover and a Tool to Support the Alert Investigation Workflow" | **5** junior Tier-1 SOC analysts, real commercial SOC, 400 total alert investigations | Real alert triage/investigation | Think-aloud transcripts, investigation steps/time, qualitative workflow coding | Qualitative/thematic — no inferential stats reported at this n | USEC (NDSS workshop) 2025 ([PDF](https://www.ndss-symposium.org/wp-content/uploads/usec25-34.pdf)) |
| "A Security Alert Investigation Tool Supporting Tier 1 Analysts" | Small number of T1 analysts at one commercial SOC (two qualitative studies) | Tool evaluation for alert investigation | Conformity to analyst workflow (qualitative) | Qualitative case-study evaluation | ACSAC 2024 ([PDF](https://www.catrin.nl/wp-content/uploads/2024/12/AISS_ACSAC24.pdf)) |
| "A Human-Grounded Evaluation of SHAP for Alert Processing" | 159 (not tiny, but the closest **design-level** precedent — with/without-SHAP-explanation alert triage) | Alert-processing correctness judgement, with vs. without SHAP | Task accuracy, "qualitative analysis of recorded reflections" alongside significance testing | Found **no significant quantitative difference**, but reported and discussed the qualitative signal anyway — precedent that a security-XAI paper can lead with qualitative insight when the quantitative test is null/underpowered | KDD XAI Workshop 2019 ([arXiv 1907.03324](https://arxiv.org/abs/1907.03324)) |
| "99% False Positives: A Qualitative Study of SOC Analysts' Perspectives" | 20 (survey) + 21 (qualitative interviews) | Alarm quality/trust perceptions | Thematic/qualitative coding, no small-n inferential stats | Pure qualitative | USENIX Security 2022 ([paper](https://www.usenix.org/system/files/sec22summer_alahmadi.pdf)) |
| "Unjustified Sample Sizes and Generalizations in Explainable AI Research" | Meta-review of **220** published XAI user studies (2012–2022) | N/A (methodology critique) | N/A | Finds most XAI user studies **do not justify their n** and routinely **over-generalize** beyond their sample — cautionary precedent: it is standard-but-criticized practice, so Argus should do the opposite (justify n, scope claims tightly) to be *more* defensible than the field average | 2023, IEEE Trans. on AI ([arXiv 2305.09477](https://arxiv.org/abs/2305.09477), [IEEE Xplore](https://ieeexplore.ieee.org/document/10268316/)) |

Metrics that recur across the table and map directly onto FYP2_PLAN item #13 (time + confidence):
**time-to-triage**, **decision accuracy vs. ground truth**, **confidence rating (Likert)**,
**NASA-TLX-style workload**, and — the load-bearing one at tiny n — **think-aloud/qualitative
coding**, which is what every genuinely tiny-n precedent above actually leans on for its
evidentiary weight, not the numbers.

## Statistical treatment for n=2–4 (what's honest, not what's impressive)

- **Wilcoxon signed-rank vs. paired t:** within-subject data (each analyst does both conditions)
  is naturally paired, so *if* a test is reported at all, Wilcoxon signed-rank (non-parametric,
  no normality assumption) is the correct choice over a paired t-test at this n — but the key fact
  to state explicitly in the write-up is that **a two-tailed paired Wilcoxon signed-rank test
  cannot reach p<.05 with fewer than 6 pairs** (minimum n for the exact distribution to permit
  p<.05 is 6). At n=2–4, any p-value reported is mathematically incapable of being "significant";
  reporting one without that caveat reads as either a viva red flag or a naive mistake.
- **What to report instead:** (1) per-participant paired differences (with − without) shown
  individually, not just averaged — the single-case-design tradition (Kratochwill et al. 2010;
  Parker & Vannest's Non-overlap-of-All-Pairs, 2009) argues visual/individual-level inspection is
  the primary analysis at tiny n, with any test statistic only a supplement; (2) direction-of-effect
  consistency ("3 of 3 participants triaged faster / rated higher confidence with explanations");
  (3) descriptive stats — median, range, IQR per condition; (4) an effect size regardless of
  significance (matched-pairs rank-biserial r = Z/√N from the Wilcoxon statistic, or simply Cohen's
  d on the paired differences) reported as a magnitude estimate, explicitly labelled
  "descriptive, not inferential — study is underpowered for hypothesis testing."
- **Honest framing:** position the whole exercise as a **formative case study / pilot**, per Yin's
  case-study methodology tradition and explicitly following the precedent set by the NDSS 2025 (n=5)
  and ACSAC 2024 SOC studies above — i.e. "this is what happened with these N ECLOGIC engineers on
  this system," not "SOC analysts in general triage X% faster with SHAP." The 2023 "Unjustified
  Sample Sizes" meta-review found this scoping discipline is what most published XAI studies
  *fail* to do — doing it correctly is a defensible, citable improvement on field norms, not a
  weakness to hide.

## Design choices that maximize validity at tiny n

1. **Within-subject, counterbalanced:** each of the 2–3 ECLOGIC engineers triages **both**
   conditions (WITH SHAP+LLM explanation panel, WITHOUT — raw score/features only). This removes
   between-subject variance, the single biggest lever available when n is tiny.
2. **Two matched alert batches (A/B):** same count of true-positive/false-positive alerts, same mix
   of scenario types (phished-account + departing-insider), same rough anomaly-score distribution,
   so no participant gets an easier batch under either condition.
3. **Counterbalance order across participants and batches** (partial Latin square, e.g. P1: A-WITHOUT
   → B-WITH; P2: B-WITH → A-WITHOUT; P3 repeats one cell and this asymmetry is *disclosed*, not
   hidden) — cancels out learning effects and batch-difficulty confounds as far as n=2–3 allows.
4. **Wash-out between conditions** (short break / unrelated task) to reduce carryover.
5. **Multi-method triangulation:** quantitative (time, accuracy, confidence, NASA-TLX) *plus*
   think-aloud transcripts *plus* a short semi-structured post-study interview ("which did you
   trust more and why") — this is what every real tiny-n precedent above (NDSS 2025, ACSAC 2024,
   KDD 2019) actually relies on for its argumentative weight, not the numbers.
6. **Publish per-participant raw data** in an appendix table so an examiner can inspect the pattern
   directly rather than trusting an aggregate.

## Recommended W8 design skeleton

- **Participants:** 2–3 ECLOGIC engineers (whatever headcount the NDA/LOI yields — do not treat
  this as a study weakness; cite the precedent table above in the methodology section).
- **Design:** within-subject, 2×2 counterbalanced (condition × batch order).
- **Conditions:** WITH (SHAP top-feature chart + LLM plain-English narrative, current Argus UI) vs.
  WITHOUT (raw anomaly score + feature values only, explanation panel hidden).
- **Materials:** two matched alert batches (~8–12 alerts each) drawn from replay/demo data, mixing
  true insider/phished-account cases with clean false-positive-shaped alerts, matched on count and
  scenario mix.
- **Per-trial metrics:** time-to-triage (timestamped), triage decision (TP/FP/escalate) scored
  against ground truth, decision confidence (1–5 Likert immediately after each decision).
- **Per-condition metrics:** NASA-TLX (raw/unweighted short form — acceptable given time
  constraints), optional SUS on the explanation UI specifically.
- **Qualitative layer:** think-aloud during triage (recorded) + 10-min semi-structured interview
  after both conditions; thematically code for trust, perceived speed, confidence-in-errors.
- **Analysis & write-up:**
  - Lead with per-participant paired plots/tables and direction-of-effect consistency.
  - Report descriptive stats (median/IQR/range) per condition.
  - Report Wilcoxon signed-rank statistic + rank-biserial effect size *only* as a labelled
    "descriptive, underpowered" supplement — never as a claimed significance result.
  - Lead the argument with the qualitative theme coding, matching how the closest published
    precedents (NDSS 2025, KDD 2019 SHAP-alert paper) actually make their case.
  - Explicitly frame as: "a formative case study with N=[2/3] ECLOGIC SOC engineers, following
    the discount-usability tradition (Nielsen 2000; Caine 2016) and precedent set by tiny-n SOC
    alert-triage studies (NDSS 2025, ACSAC 2024)" — scope every claim to "these participants, this
    system," per the caution in the 2023 sample-size meta-review.

## Citations (strongest 4 for "tiny-n usability studies are standard practice")

1. Nielsen, J. (2000), "Why You Only Need to Test with 5 Users" (building on Nielsen & Landauer
   1993) — the canonical discount-usability citation for n≈5 being sufficient for qualitative
   problem discovery. [nngroup.com](https://www.nngroup.com/articles/why-you-only-need-to-test-with-5-users/) (referenced via [Trymata 2025](https://trymata.com/blog/5-user-rule-for-user-testing/))
2. Caine, K. (2016), "Local Standards for Sample Size at CHI," CHI '16 — empirical survey showing
   published HCI sample sizes span 1 to 916,000 with qualitative-study norms around n=14 but
   single-digit n routinely accepted; argues for method-local, not universal, standards.
   [ACM DL](https://dl.acm.org/doi/10.1145/2858036.2858498)
3. "A Field Study to Uncover and a Tool to Support the Alert Investigation Workflow," USEC (NDSS
   workshop) 2025 — n=5 SOC analysts, think-aloud, real alerts; the closest true security-domain
   tiny-n precedent, published in 2025. [PDF](https://www.ndss-symposium.org/wp-content/uploads/usec25-34.pdf)
4. "A Human-Grounded Evaluation of SHAP for Alert Processing," KDD XAI Workshop 2019 — the closest
   *design-level* precedent (with-vs-without-SHAP alert triage in a security context); shows the
   field accepts a null/non-significant quantitative result paired with qualitative analysis as a
   legitimate publishable outcome. [arXiv 1907.03324](https://arxiv.org/abs/1907.03324)
   (Supplementary caution citation: Unwer/Roy et al., "Unjustified Sample Sizes and Generalizations
   in Explainable AI Research," 2023, [arXiv 2305.09477](https://arxiv.org/abs/2305.09477) — use to
   justify *why* Argus scopes its claims narrowly instead of generalizing.)

## Confidence

**Medium-high.** High confidence that (a) tiny-n, within-subject, qualitatively-supplemented
studies are standard and defensible in HCI generally (Nielsen, Caine — long-settled, frequently
re-cited through 2025), and (b) the security-alert-triage sub-field specifically has already
published at n=5 with think-aloud methodology in 2025 (NDSS), so n=2–3 is a small, defensible step
further, not an outlier. Medium confidence on the *exact* best statistical write-up recipe, because
no source found is a security-XAI paper published at n=2–3 specifically with a fully worked
statistical presentation — the precedents cluster at n=5–21 and mostly avoid inferential stats
entirely rather than showing how to *frame* an underpowered test. What would change this: finding a
published security or XAI user study at n=2–3 that includes a worked statistical section (would let
us copy its exact framing instead of synthesizing one from adjacent single-case-design literature).
