# -*- coding: utf-8 -*-
"""Fill the ST-AI-0122 LNCS template with the real Argus UEBA full paper.

Strategy: keep the template's styles.xml / numbering.xml / theme / settings,
rebuild only word/document.xml using the template's own paragraph styles, embed
three figures, and repack into a .docx that conforms to the LNCS template.
"""
import os, re, shutil
from PIL import Image

UNP = "_tpl_unpacked"
MEDIA = os.path.join(UNP, "word", "media")
EMU_PER_TWIP = 635
CONTENT_TWIP = 11906 - 2494 - 2494          # page width - L - R margins

def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

# ---- paragraph / run builders -------------------------------------------------
def run(text):
    sp = ' xml:space="preserve"' if (text != text.strip() or "  " in text) else ""
    return f"<w:r><w:t{sp}>{esc(text)}</w:t></w:r>"

def sup(text):
    return (f'<w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr>'
            f'<w:t>{esc(text)}</w:t></w:r>')

def para(style, *inner, runs=None):
    pPr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else "<w:pPr/>"
    body = "".join(inner) if inner else (run(runs) if runs else "")
    return f"<w:p>{pPr}{body}</w:p>"

def body(style, text):
    """A body paragraph: bold leading label allowed via run() only (plain text)."""
    return para(style, run(text))

# ---- figure embedding ---------------------------------------------------------
_img_rels, _img_files, _next = [], [], [100]
def add_image(png_path, width_twip, caption):
    """Copy png into media, register rel, return the figure+caption XML."""
    rid = f"rIdImg{_next[0]}"; _next[0] += 1
    fname = f"img{_next[0]}.png"
    os.makedirs(MEDIA, exist_ok=True)
    shutil.copy(png_path, os.path.join(MEDIA, fname))
    w, h = Image.open(png_path).size
    cx = width_twip * EMU_PER_TWIP
    cy = int(cx * h / w)
    _img_rels.append(
        f'<Relationship Id="{rid}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        f'Target="media/{fname}"/>')
    docpr = _next[0]
    drawing = (
      '<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
      f'<wp:extent cx="{cx}" cy="{cy}"/>'
      '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
      f'<wp:docPr id="{docpr}" name="Figure {docpr}"/>'
      '<wp:cNvGraphicFramePr><a:graphicFrameLocks '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>'
      '</wp:cNvGraphicFramePr>'
      '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
      '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
      '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
      '<pic:nvPicPr><pic:cNvPr id="0" name="Figure"/><pic:cNvPicPr/></pic:nvPicPr>'
      f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
      '<pic:spPr><a:xfrm><a:off x="0" y="0"/>'
      f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
      '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
      '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
    fig_para = (f'<w:p><w:pPr><w:pStyle w:val="image"/>'
                f'<w:jc w:val="center"/></w:pPr>{drawing}</w:p>')
    cap_para = para("figurecaption", run(caption))
    return fig_para + cap_para

# ---- table builder ------------------------------------------------------------
def table(headers, rows, col_twips):
    BORD = ('<w:tblBorders>'
            '<w:top w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
            '<w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/>'
            '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="808080"/>'
            '</w:tblBorders>')
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in col_twips)
    tblPr = (f'<w:tblPr><w:tblStyle w:val="TableNormal"/>'
             f'<w:tblW w:w="{sum(col_twips)}" w:type="dxa"/>{BORD}</w:tblPr>'
             f'<w:tblGrid>{grid}</w:tblGrid>')
    def cell(text, w, bold=False, center=False):
        rpr = "<w:rPr><w:sz w:val=\"18\"/>" + ("<w:b/>" if bold else "") + "</w:rPr>"
        jc = '<w:jc w:val="center"/>' if center else ""
        return (f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>'
                f'<w:vAlign w:val="center"/></w:tcPr>'
                f'<w:p><w:pPr><w:pStyle w:val="Normal"/>'
                f'<w:spacing w:before="20" w:after="20"/>'
                f'<w:ind w:firstLine="0"/>{jc}</w:pPr>'
                f'<w:r>{rpr}<w:t xml:space="preserve">{esc(text)}</w:t></w:r></w:p></w:tc>')
    hrow = ("<w:tr>" + "".join(cell(h, w, bold=True, center=(i>0))
            for i,(h,w) in enumerate(zip(headers, col_twips))) + "</w:tr>")
    trs = []
    for r in rows:
        trs.append("<w:tr>" + "".join(cell(v, w, center=(i>0))
                   for i,(v,w) in enumerate(zip(r, col_twips))) + "</w:tr>")
    return f"<w:tbl>{tblPr}{hrow}{''.join(trs)}</w:tbl>"

# ==============================================================================
# PAPER CONTENT
# ==============================================================================
P = []  # paragraph XML fragments in order
A = P.append

# --- Title ---
A(para("papertitle", run("Cloud-Native User and Entity Behaviour Analytics for "
        "Insider-Threat Detection Using Label-Free Unsupervised Learning")))

# --- Authors ---
A(para("author",
       run("Z.C Yap"), sup("1"), run(" and Firdaus Sahran"), sup("1,2")))

# --- Affiliations ---
A(para("address", sup("1"),
       run(" Faculty of Computer Science and Information Technology, "
           "Universiti Malaya, 50603 Kuala Lumpur, Malaysia")))
A(para("address", sup("2"),
       run(" Centre of Research for Cyber Security and Network, "
           "Universiti Malaya, 50603 Kuala Lumpur, Malaysia")))
A(para("address", run("23004982@siswa.um.edu.my")))

# --- Abstract ---
A(para("abstract", run(
  "Abstract. Cloud adoption has dissolved the traditional network perimeter and "
  "amplified the risk of insider threats — abuse committed with legitimate "
  "credentials that signature-based defences are structurally blind to. This paper "
  "presents a cloud-native User and Entity Behaviour Analytics (UEBA) platform that "
  "detects insider activity, account compromise and data exfiltration without any "
  "labelled attack data. Heterogeneous activity logs from four cloud sources — "
  "AWS CloudTrail, Microsoft Azure AD sign-ins, Cloudflare Access and GitHub audit "
  "events — are normalised into a single eight-field schema. Per-user behavioural "
  "baselines are built from 30-day rolling statistics over 71 engineered features. The "
  "final detector is a deep autoencoder trained only on normal user-days; its "
  "reconstruction error is the risk score, while an Isolation Forest, a rule scorer and "
  "a six-signal rarity scorer (including a geo-rarity flag derived from Cloudflare "
  "country data) are retained as interpretable baselines. Every alert is explained "
  "through SHAP feature attribution and a natural-language large-language-model "
  "assistant. On the CERT r4.2 benchmark (1,000 users, 70 insiders) the autoencoder "
  "attains AUROC 0.976, AUPRC 0.851 and F1 0.787 — within ~99% of a supervised "
  "stacking ensemble's AUROC (0.980) and ~90% of its F1, with zero labels — "
  "decisively outperforming the rule and isolation "
  "baselines. External validity is demonstrated on the flaws.cloud AWS dataset "
  "(AUROC 0.724) and a streaming live-replay (AUROC 0.917). The system is "
  "containerised and deployed on Docker, Hugging Face Spaces and Vercel.")))

A(para("keywords", run(
  "Keywords: UEBA · Insider threat detection · Unsupervised learning · "
  "Autoencoder · Explainable AI · SHAP · Cloud security · "
  "Log normalisation · Anomaly detection · Large language models.")))

# --- 1 Introduction ---
A(para("heading1", run("Introduction")))
A(para("p1a", run(
  "The migration of enterprise data and services to public cloud platforms such as "
  "Amazon Web Services (AWS) and Microsoft Azure has delivered scalability and "
  "accessibility, but it has also dissolved the network perimeter on which classical "
  "defences depend. Insider threats — attacks originating from users who already "
  "hold legitimate credentials and authorised access — are among the most damaging "
  "consequences of this shift.")))
A(body("Normal",
  "According to the Verizon 2025 Data Breach Investigations Report, the human element "
  "is involved in roughly 60% of breaches, and stolen or misused credentials remain the "
  "dominant initial-access vector [1]. The Ponemon Institute estimates that organisations "
  "now spend an average of USD 17.4 million per year addressing insider-related risk, a "
  "40% increase since 2019 [2]. Because insiders act within their granted privileges, "
  "signature- and rule-based tools such as intrusion-detection systems and SIEM "
  "platforms cannot reliably distinguish malicious from benign activity, and they "
  "generate excessive false positives when applied across diverse user populations "
  "without per-user context."))
A(body("Normal",
  "User and Entity Behaviour Analytics (UEBA) addresses these limitations by modelling "
  "each user's normal behaviour over time and flagging statistically significant "
  "deviations. However, prominent open-source UEBA and SIEM tools — Wazuh, OpenUBA "
  "and HELK — remain largely rule-based, operate on a single log source, and provide "
  "no explanation for why a user is flagged, leaving analysts with an opaque score and "
  "no actionable rationale."))
A(body("Normal",
  "This paper presents Argus, a cloud-native UEBA platform, and makes four contributions: "
  "(1) a normalisation layer that unifies four structurally distinct cloud log sources "
  "— AWS CloudTrail, Azure AD, Cloudflare Access and GitHub — into one eight-field "
  "schema; (2) a label-free detection pipeline whose final detector is a deep autoencoder, "
  "complemented by interpretable rarity signals; (3) per-alert explainability combining "
  "SHAP attribution with a large-language-model (LLM) analyst assistant; and (4) an "
  "evaluation that goes beyond the CERT benchmark to real cloud-breach data and a live "
  "streaming replay."))

# --- 2 Related Work ---
A(para("heading1", run("Related Work")))
A(para("p1a", run(
  "UEBA evolved from earlier User Behaviour Analytics systems, broadened to include "
  "non-human entities. Gartner formalised the category in 2015, recognising that "
  "monitoring only human activity left significant blind spots in organisational security "
  "posture [3].")))

A(para("heading2", run("Unsupervised Anomaly Detection")))
A(para("p1a", run(
  "Datta et al. demonstrated real-time insider-threat detection with unsupervised "
  "learning on the CERT dataset, showing competitive detection without labelled attacks "
  "[4]. Liu et al. introduced Isolation Forest, which partitions the feature space at "
  "random and isolates anomalies in fewer splits, making it well suited to "
  "high-dimensional behavioural data [5]. Autoencoder approaches instead learn to "
  "reconstruct normal behaviour; inputs unseen during training yield elevated "
  "reconstruction error that serves directly as an anomaly score [6].")))

A(para("heading2", run("Explainable AI in Security")))
A(para("p1a", run(
  "Lundberg and Lee proposed SHAP, a unified framework that explains model predictions "
  "using Shapley values from cooperative game theory [7]. Applied to intrusion detection, "
  "SHAP attributions have been shown to improve analyst trust by exposing each feature's "
  "contribution in an interpretable form [8]. The EU AI Act (2024) mandates explainability "
  "for high-risk AI systems in security-critical domains, further motivating the "
  "integration of explainable AI [9].")))

A(para("heading2", run("Limitations of Existing Tools")))
A(para("p1a", run(
  "Wazuh encodes its detection logic as static XML rules with no adaptive learning [10]. "
  "OpenUBA offers basic statistical profiling but no per-user rolling baselines, while "
  "HELK exposes Elasticsearch machine-learning primitives without a custom training "
  "pipeline or explanation layer. None of the evaluated tools normalise multiple cloud "
  "sources or provide per-alert explanations, which is precisely the gap this work "
  "addresses.")))

# --- 3 System Design ---
A(para("heading1", run("System Design and Methodology")))
A(para("p1a", run(
  "Argus implements a decoupled, layered pipeline: log ingestion and normalisation, "
  "feature engineering and baseline construction, label-free detection, rarity signalling, "
  "explainability, and an analyst dashboard. Each layer communicates through a "
  "well-defined interface so that the detection and presentation layers remain entirely "
  "source-agnostic. The overall architecture and tool stack are shown in Fig. 1.")))
A(add_image("results/report_png/architecture_logos.png", CONTENT_TWIP,
            "Fig. 1. Argus system architecture and tool stack: four cloud sources are "
            "normalised into one schema, scored by a label-free autoencoder with rarity "
            "and rule baselines, explained via SHAP and an LLM assistant, then surfaced "
            "on a web dashboard."))

A(para("heading2", run("Multi-Cloud Log Normalisation")))
A(para("p1a", run(
  "Cloud providers emit structurally distinct logs. AWS CloudTrail records API calls in "
  "JSON (eventTime, userIdentity.userName, eventName, sourceIPAddress); Azure AD "
  "sign-in logs use createdDateTime, userPrincipalName and ipAddress; Cloudflare Access "
  "uses created_at, user_email, app_domain and a country field; GitHub audit events use "
  "their own actor and action keys. A normalisation layer maps all four onto a single "
  "eight-field internal schema: {timestamp, user, action, source_ip, bytes, resource, "
  "country, source}.")))
A(body("Normal",
  "This design keeps the downstream pipeline source-agnostic: adding a new provider "
  "requires only a single parser function, with no change to feature extraction, "
  "detection or the dashboard. For the benchmark evaluation, the CERT r4.2 dataset is "
  "converted into the same schema, providing labelled ground truth across logon, file, "
  "email, device and HTTP activity [11]."))

A(para("heading2", run("Feature Engineering and Behavioural Baselines")))
A(para("p1a", run(
  "Normalised events are aggregated into daily behavioural vectors per user. For CERT "
  "data, a 71-dimensional feature vector is computed over a 30-day rolling window, "
  "capturing volume, timing, device, file and communication patterns; for live cloud "
  "data, a compact 12-dimensional per-user-day feature vector is used. A 30-day rolling "
  "window yields the per-user mean (μ) and standard deviation (σ) of each "
  "feature, and the daily deviation z = (x − μ)/σ quantifies how far a "
  "user's behaviour departs from their own established norm.")))

A(para("heading2", run("Label-Free Detection")))
A(para("p1a", run(
  "Two unsupervised models are trained exclusively on normal user-days, with labelled "
  "malicious users excluded from training. An Isolation Forest (scikit-learn) isolates "
  "structurally distinct points in fewer partitioning steps, producing a normalised "
  "anomaly score in [0, 1]. A deep autoencoder (PyTorch) learns to reconstruct normal "
  "behavioural vectors; the mean-squared reconstruction error, normalised to [0, 1], is "
  "the anomaly score for an input.")))
A(body("Normal",
  "Unlike the earlier ensemble formulation, the autoencoder reconstruction error is used "
  "as the final risk score, because it gave the strongest separation in our experiments. "
  "The Isolation Forest, a threshold-based rule scorer, and a weighted average of "
  "Isolation Forest and autoencoder are retained as transparent baselines for comparison "
  "rather than as the production detector."))

A(para("heading2", run("Rarity Signals")))
A(para("p1a", run(
  "Complementing the autoencoder, a rarity scorer emits six interpretable binary flags "
  "per event: first_time_action, new_ip, off_hours, high_volume, sensitive_resource and "
  "geo_rarity. The geo_rarity flag fires when an event originates from a country never "
  "previously observed for that user, derived from the Cloudflare Access country field "
  "— the only source with reliable geolocation. The rarity score is the fraction of "
  "the six flags that fire, giving analysts a fast, human-readable corroboration of the "
  "model score.")))

A(para("heading2", run("Explainability")))
A(para("p1a", run(
  "Every flagged event is passed to a SHAP KernelExplainer, which attributes the risk "
  "score to individual features and produces a ranked, human-readable reason string — "
  "for example, that after-hours activity and a first-seen IP address together account "
  "for the majority of an alert's score. A large-language-model assistant (configurable "
  "across Gemini, DeepSeek and Groq) then converts this attribution into a concise "
  "natural-language narrative for the analyst, turning opaque scores into investigable "
  "intelligence and directly addressing the explainability mandate of the EU AI Act [9].")))

# --- 4 Evaluation ---
A(para("heading1", run("Evaluation")))
A(para("heading2", run("Dataset and Experimental Setup")))
A(para("p1a", run(
  "The primary benchmark is the CERT Insider Threat Dataset r4.2 (Carnegie Mellon "
  "University), comprising roughly 32 million events from 1,000 simulated users over 17 "
  "months, of which 70 are designated malicious insiders [11]. The timeline is split "
  "chronologically: earlier activity (normal users only) trains the baselines and the "
  "autoencoder, while the held-out remainder, containing all 70 insiders, forms the test "
  "set. All experiments use a fixed random seed of 42 for reproducibility.")))

A(para("heading2", run("Detector Performance")))
A(para("p1a", run(
  "Table 1 reports AUROC, AUPRC and F1 (at the F1-optimal threshold) for the four "
  "configurations on the CERT r4.2 test set. Because insiders are a small minority, AUPRC "
  "is reported alongside AUROC, as AUROC alone can overstate performance on imbalanced "
  "data. The autoencoder dominates every metric, and the corresponding ROC curves are "
  "shown in Fig. 2.")))
A(para("tablecaption", run("Table 1. Detector performance on CERT r4.2 "
                           "(1,000 users, 70 insiders).")))
A(table(
  ["Model", "AUROC", "AUPRC", "F1"],
  [["Autoencoder (final)", "0.976", "0.851", "0.787"],
   ["Weighted average (IF + AE)", "0.951", "0.740", "0.726"],
   ["Isolation Forest", "0.860", "0.206", "0.379"],
   ["Rule-based", "0.859", "0.207", "0.367"]],
  [int(CONTENT_TWIP*0.46)] + [int(CONTENT_TWIP*0.18)]*3))
A(add_image("results/report_png/roc.png", int(CONTENT_TWIP*0.72),
            "Fig. 2. ROC curves for the autoencoder and the rule and isolation baselines "
            "on CERT r4.2."))

A(para("heading2", run("Real-World Validation")))
A(para("p1a", run(
  "Benchmarks on simulated data can flatter a detector, so two external checks are "
  "performed. First, the cloud feature autoencoder is evaluated on the flaws.cloud AWS "
  "CloudTrail dataset, where it separates the Level-5/Level-6 attacker activity from "
  "benign API calls at AUROC 0.724 despite being trained without any attack labels. "
  "Second, a streaming live-replay drives events through the production /ingest endpoint "
  "and scores them online; the live pipeline attains AUROC 0.917 against an offline "
  "0.976, confirming that the real-time path preserves most of the detector's accuracy.")))

A(para("heading2", run("Capability Comparison")))
A(para("p1a", run(
  "Table 2 compares Argus with three widely used open-source UEBA/SIEM platforms across "
  "capabilities relevant to insider-threat detection in cloud environments. Argus is the "
  "only system to combine multi-cloud normalisation, label-free learning and per-alert "
  "explainability. Figure 3 shows the mean absolute SHAP attribution across the most "
  "influential features, illustrating which behaviours most often drive an alert.")))
A(para("tablecaption", run("Table 2. Capability comparison with open-source UEBA tools.")))
A(table(
  ["Capability", "Wazuh", "OpenUBA", "HELK", "Argus"],
  [["Per-user baseline", "No", "Partial", "No", "Yes"],
   ["Multi-cloud normalisation", "No", "No", "No", "Yes"],
   ["Label-free ML detector", "No", "Partial", "Limited", "Yes"],
   ["Rarity signalling", "No", "No", "No", "Yes"],
   ["SHAP + LLM explainability", "No", "No", "No", "Yes"],
   ["Academic + real-world eval", "No", "No", "No", "Yes"]],
  [int(CONTENT_TWIP*0.40)] + [int(CONTENT_TWIP*0.15)]*4))
A(add_image("results/report_png/shap.png", int(CONTENT_TWIP*0.82),
            "Fig. 3. Mean absolute SHAP attribution for the most influential behavioural "
            "features."))

# --- 5 Discussion ---
A(para("heading1", run("Discussion")))
A(para("heading2", run("Strengths")))
A(para("p1a", run(
  "Training only on normal behaviour means Argus needs no labelled attacks, which are "
  "scarce and quickly stale in practice; yet it reaches roughly 99% of a supervised "
  "stacking ensemble's AUROC (0.980) and 90% of its F1. The rarity signals and SHAP "
  "attribution give analysts an immediate, "
  "human-readable rationale for each alert — a capability absent from every "
  "open-source tool evaluated — and the LLM assistant lowers cognitive load by "
  "narrating that rationale in plain language. The source-agnostic normalisation layer "
  "makes adding a new cloud provider a one-parser change.")))

A(para("heading2", run("Limitations and Future Work")))
A(para("p1a", run(
  "Several limitations remain. The CERT dataset, though the standard academic benchmark, "
  "is simulated; the flaws.cloud and live-replay results mitigate but do not fully remove "
  "this concern. Detection is also uneven across the three CERT insider scenarios: the "
  "autoencoder recovers the burst-like Scenario 1 (30/30) and Scenario 3 (10/10) but only "
  "the low-and-slow Scenario 2 (12/30), which a supervised stacking ensemble detects "
  "(27/30) — the signal is present in the features but missed by the per-day reconstruction "
  "objective. The principal planned extension is therefore a sequence / Transformer "
  "autoencoder over each user's daily timeline, modelling gradual temporal drift rather "
  "than single-day aggregates; an initial prototype did not yet improve Scenario 2 "
  "detection, plausibly constrained by only 70 insider entities, and remains the main "
  "direction for future work. The system does not yet detect model drift as legitimate "
  "behaviour evolves; future work will add KL-divergence drift detection with periodic retraining. "
  "A patient adversary could behave normally during baseline construction to poison it; "
  "adversarial-robustness evaluation is warranted. Finally, full streaming ingestion via "
  "a message bus such as Kafka is deferred as a scaling extension.")))

# --- 6 Conclusion ---
A(para("heading1", run("Conclusion")))
A(para("p1a", run(
  "This paper presented Argus, a cloud-native UEBA platform that detects insider threats "
  "without labelled attack data. A four-source normalisation layer unifies AWS, Azure, "
  "Cloudflare and GitHub logs into one schema; a label-free autoencoder serves as the "
  "final detector, supported by interpretable rarity and rule baselines; and SHAP "
  "attribution with an LLM assistant explains every alert. On CERT r4.2 the autoencoder "
  "achieves AUROC 0.976, AUPRC 0.851 and F1 0.787, and external validation on "
  "flaws.cloud (AUROC 0.724) and a live streaming replay (AUROC 0.917) confirms its "
  "real-world viability. The work shows that effective, explainable, cloud-native "
  "insider-threat detection is achievable with open-source tools and custom unsupervised "
  "learning, without reliance on costly commercial platforms.")))

# --- Acknowledgments ---
A(para("acknowlegments", run(
  "Acknowledgments. The author thanks the supervisor and the Faculty of Computer Science "
  "and Information Technology, Universiti Malaya, for their guidance and support, and "
  "Carnegie Mellon University for providing the CERT Insider Threat Dataset.")))
A(para("acknowlegments", run(
  "Disclosure of Interests. The authors declare that they have no competing interests.")))

# --- References ---
A(para("heading1", run("References")))
refs = [
  "Verizon: 2025 Data Breach Investigations Report. Verizon Enterprise Solutions (2025)",
  "Ponemon Institute: 2025 Cost of Insider Risks Global Report. Proofpoint (2025)",
  "Gartner: Market Guide for User and Entity Behavior Analytics. Gartner Research (2015)",
  "Datta, J., Dasgupta, S., Dasgupta, R., Reddy, K.R.: Real-time threat detection in "
  "UEBA using unsupervised learning algorithms. In: Proc. IEEE IEMENTech (2021)",
  "Liu, F.T., Ting, K.M., Zhou, Z.H.: Isolation forest. In: Proc. IEEE ICDM, pp. "
  "413–422 (2008)",
  "Inayat, U., Farzan, M., Mahmood, S., Zia, M.F., Hussain, S., Pallonetto, F.: Insider "
  "threat mitigation: a systematic literature review. Ain Shams Engineering Journal "
  "15(12) (2024)",
  "Lundberg, S.M., Lee, S.I.: A unified approach to interpreting model predictions. In: "
  "Advances in Neural Information Processing Systems, vol. 30 (2017)",
  "Sharma, G., Thakur, A., Tiwari, C.: Developing a comprehensive framework for UEBA: "
  "integrating advanced ML and contextual insights. Journal of Communication Engineering "
  "& Systems (2024)",
  "European Parliament: Regulation (EU) 2024/1689 — Artificial Intelligence Act. "
  "Official Journal of the European Union (2024)",
  "Wazuh: The Open Source Security Platform. GitHub repository, "
  "https://github.com/wazuh/wazuh, last accessed 2025/05/30",
  "Glasser, J., Lindauer, B.: Bridging the gap: a pragmatic approach to generating "
  "insider threat data. In: Proc. IEEE Security and Privacy Workshops (2013)",
]
for r in refs:
    A(para("referenceitem", run(r)))

# ==============================================================================
# assemble + write
# ==============================================================================
sectPr = ('<w:sectPr w:rsidSect="009F7FCE">'
          '<w:pgSz w:w="11906" w:h="16838" w:orient="portrait" w:code="9"/>'
          '<w:pgMar w:top="2948" w:right="2494" w:bottom="2948" w:left="2494" '
          'w:header="2381" w:footer="2324" w:gutter="0"/>'
          '<w:cols w:space="227"/><w:titlePg/>'
          '<w:docGrid w:linePitch="240"/></w:sectPr>')

with open(os.path.join(UNP, "word", "document.xml"), encoding="utf-8") as f:
    head = f.read().split("<w:body>")[0]

doc = (head + "<w:body>" + "".join(P) + sectPr + "</w:body></w:document>")
with open(os.path.join(UNP, "word", "document.xml"), "w", encoding="utf-8") as f:
    f.write(doc)

# --- rels: keep needed core rels, drop chart/mailto/lncs hyperlink, add images ---
rels_path = os.path.join(UNP, "word", "_rels", "document.xml.rels")
with open(rels_path, encoding="utf-8") as f:
    rels = f.read()
# drop chart relationship + the two external hyperlinks (unused now)
for rid in ("rId9", "rId8", "rId10"):
    rels = re.sub(r'<Relationship[^>]*Id="' + rid + r'"[^>]*/>', "", rels)
rels = rels.replace("</Relationships>", "".join(_img_rels) + "</Relationships>")
with open(rels_path, "w", encoding="utf-8") as f:
    f.write(rels)

# --- remove the orphan sample chart (broken external xlsx reference) ---
chart_dir = os.path.join(UNP, "word", "charts")
if os.path.isdir(chart_dir):
    shutil.rmtree(chart_dir)

# --- Content_Types: ensure png default present, drop chart override ---
ct = os.path.join(UNP, "[Content_Types].xml")
with open(ct, encoding="utf-8") as f:
    ctx = f.read()
ctx = re.sub(r'<Override[^>]*PartName="/word/charts/[^"]*"[^>]*/>', "", ctx)
# convert the macro-enabled (.docm) main part type to a plain .docx document type
ctx = ctx.replace(
    "application/vnd.ms-word.document.macroEnabled.main+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")
if 'Extension="png"' not in ctx:
    ctx = ctx.replace("</Types>",
        '<Default Extension="png" ContentType="image/png"/></Types>')
with open(ct, "w", encoding="utf-8") as f:
    f.write(ctx)

print("document.xml rebuilt:", len(P), "paragraphs,", len(_img_rels), "images")
