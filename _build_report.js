// Build the FYP progress report (.docx)
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageNumber, PageBreak, Header, Footer, ImageRun,
  TableOfContents, VerticalAlign,
} = require("docx");

const CW = 9360; // content width (US Letter, 1" margins)
const NAVY = "002060", WHITE = "FFFFFF", LIGHT = "F2F2F2", ACCENT = "0072B2";

// ---- helpers ----------------------------------------------------------------
const P = (text, opts = {}) => new Paragraph({
  alignment: opts.align || AlignmentType.JUSTIFIED,
  spacing: { after: opts.after ?? 110, line: 258, ...(opts.before ? { before: opts.before } : {}) },
  children: Array.isArray(text) ? text : [new TextRun({ text, size: 22, ...opts.run })],
  ...(opts.p || {}),
});
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 200, after: 100 },
  children: [new TextRun({ text: t, bold: true, size: 30, color: NAVY })] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 150, after: 80 },
  children: [new TextRun({ text: t, bold: true, size: 25, color: "1F3864" })] });
const bullet = (text, level = 0) => new Paragraph({
  numbering: { reference: "bul", level }, spacing: { after: 56, line: 252 },
  children: Array.isArray(text) ? text : [new TextRun({ text, size: 22 })],
});
const num = (text) => new Paragraph({ numbering: { reference: "ord", level: 0 }, spacing: { after: 56, line: 252 },
  children: Array.isArray(text) ? text : [new TextRun({ text, size: 22 })] });
const caption = (t) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 40, after: 120 },
  children: [new TextRun({ text: t, italics: true, size: 19, color: "555555" })] });
const img = (file, w, h) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 20 },
  children: [new ImageRun({ type: "png", data: fs.readFileSync(file),
    transformation: { width: w, height: h },
    altText: { title: file, description: file, name: file } })] });

const B = (t) => new TextRun({ text: t, bold: true, size: 22 });
const T = (t) => new TextRun({ text: t, size: 22 });

// ---- table builder ----------------------------------------------------------
const bd = { style: BorderStyle.SINGLE, size: 1, color: "BBBBBB" };
const borders = { top: bd, bottom: bd, left: bd, right: bd, insideHorizontal: bd, insideVertical: bd };
function cell(text, w, { head = false, fill, bold = false, align } = {}) {
  return new TableCell({
    width: { size: w, type: WidthType.DXA },
    borders, verticalAlign: VerticalAlign.CENTER,
    shading: { fill: head ? NAVY : (fill || "auto"), type: ShadingType.CLEAR, color: "auto" },
    margins: { top: 60, bottom: 60, left: 110, right: 110 },
    children: [new Paragraph({ alignment: align || AlignmentType.LEFT, spacing: { after: 0, line: 252 },
      children: [new TextRun({ text, bold: head || bold, size: 20, color: head ? WHITE : "000000" })] })],
  });
}
function table(widths, rows) {
  return new Table({
    width: { size: CW, type: WidthType.DXA }, columnWidths: widths,
    rows: rows.map((r, ri) => new TableRow({
      tableHeader: ri === 0,
      children: r.map((c, ci) => cell(c, widths[ci], {
        head: ri === 0, fill: ri > 0 && ri % 2 === 0 ? LIGHT : undefined,
      })),
    })),
  });
}

// ============================================================================
const SS = (t) => new TextRun({ text: t, superScript: true, size: 17 });
const titlePage = [
  // Title
  new Paragraph({ spacing: { before: 240, after: 140 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Cloud-Native User and Entity Behaviour Analytics (UEBA) Platform for Insider Threat Detection", bold: true, size: 30, color: NAVY })] }),
  // Authors with affiliation superscripts
  new Paragraph({ spacing: { after: 70 }, alignment: AlignmentType.CENTER,
    children: [
      new TextRun({ text: "Z.C. Yap", size: 23 }), SS("1"),
      new TextRun({ text: ", F. Sahran", size: 23 }), SS("1,2"), SS("*"),
    ] }),
  // Affiliations
  new Paragraph({ spacing: { after: 20 }, alignment: AlignmentType.CENTER,
    children: [SS("1"), new TextRun({ text: " Faculty of Computer Science and Information Technology, Universiti Malaya", size: 18, italics: true })] }),
  new Paragraph({ spacing: { after: 20 }, alignment: AlignmentType.CENTER,
    children: [SS("2"), new TextRun({ text: " Centre of Research for Cyber Security and Network, Universiti Malaya, 50603 Kuala Lumpur, Malaysia", size: 18, italics: true })] }),
  new Paragraph({ spacing: { after: 30 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "*Corresponding author: firdaussahran@um.edu.my", size: 18 })] }),
  new Paragraph({ spacing: { after: 180 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Yap Zhe Cheng   ·   Matric No. 23004982   ·   Session 2025/26", size: 18, color: "888888" })] }),
  // Abstract
  new Paragraph({ spacing: { after: 90 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Abstract", bold: true, size: 24, color: NAVY })] }),
  P("Insider threats remain among the most damaging and least detectable cybersecurity risks, costing organisations an average of USD 17.4 million annually (Ponemon Institute, 2025) and contributing to roughly 60% of breaches through the human element (Verizon, 2025). Because insiders act with legitimate credentials, signature-based defences are structurally blind to them, and existing open-source UEBA tools — Wazuh, OpenUBA, and HELK — remain rule-based, single-source, and opaque. This project delivers a cloud-native UEBA platform that closes four gaps simultaneously: multi-cloud log heterogeneity, adaptive behavioural baselining, label-free anomaly detection, and per-alert explainability. A source-agnostic normalisation layer ingests four real cloud log formats — AWS CloudTrail, Azure AD, Cloudflare Access, and GitHub Events — into a unified eight-field schema. Two Autoencoders are trained without labels: a 71-dimensional model on the CERT r4.2 dataset and a 12-dimensional cloud-native model on 1.94 million real AWS CloudTrail events. On CERT r4.2 the Autoencoder achieves AUROC 0.976 and F1 0.787, reaching about 90% of the supervised ceiling without labelled data; the cloud model reaches AUROC 0.724 on real privilege-escalation attacks. SHAP attribution and an LLM assistant surface plain-English explanations on a React dashboard deployed via Docker and a HuggingFace Space."),
  P([B("Keywords: "), new TextRun({ text: "Insider threat detection; User and Entity Behaviour Analytics; unsupervised machine learning; Autoencoder; SHAP explainability; multi-cloud log normalisation.", italics: true, size: 22 })]),
];

// ---- 1. Introduction ----
const intro = [
  H1("1.  Introduction"),
  H2("1.1  Background and Motivation"),
  P("The rapid adoption of cloud computing has transformed how organisations store and process sensitive data. Platforms such as Amazon Web Services (AWS) and Microsoft Azure offer unprecedented scalability while simultaneously expanding the attack surface for insider threats — incidents perpetrated by users who already hold legitimate access credentials. Unlike external attackers who must defeat perimeter defences, insiders operate within trusted boundaries, rendering signature-based intrusion detection fundamentally inadequate. User and Entity Behaviour Analytics (UEBA) addresses this gap by establishing baselines of normal behaviour and flagging statistically significant deviations. However, existing open-source UEBA tools rely on static rule sets that cannot adapt to novel patterns, produce excessive false positives because they lack per-user and peer-group context, and operate as black boxes that cannot explain why a user was flagged."),
  H2("1.2  Problem Statement"),
  P("Organisations operating cloud environments lack an open-source UEBA solution that simultaneously addresses: (i) multi-cloud log heterogeneity through a source-agnostic normalisation layer; (ii) adaptive behavioural baselining at the individual-user and peer-group level; (iii) unsupervised anomaly detection capable of operating without labelled attack data; and (iv) per-alert explainability that enables analysts to validate, prioritise, and act on flagged events. The absence of these combined capabilities constitutes the research gap this project addresses."),
  H2("1.3  Research Questions"),
  P("The following research questions guide this investigation (unchanged from the project proposal):"),
  bullet([B("RQ1:  "), T("What are the critical limitations of existing rule-based and open-source UEBA systems?")]),
  bullet([B("RQ2:  "), T("How can a log-normalisation schema and behavioural-profiling pipeline support multi-cloud insider threat detection?")]),
  bullet([B("RQ3:  "), T("How can an Autoencoder-based unsupervised model, augmented with SHAP explainability, detect insider threats without requiring labelled training data?")]),
  bullet([B("RQ4:  "), T("To what extent does the proposed system improve detection performance over rule-based baselines?")]),
  H2("1.4  Research Objectives"),
  P("The project pursues four objectives (unchanged from the proposal):"),
  num("To study the limitations of traditional rule-based insider threat detection through a review of existing open-source UEBA systems."),
  num("To design a cloud log-normalisation layer and behavioural-profiling pipeline (rolling baselines, peer groups)."),
  num("To develop a functional UEBA prototype with Autoencoder anomaly detection and SHAP per-alert explanations for identifying insider threats."),
  num("To evaluate the system's performance on the CERT Insider Threat Dataset."),
  H2("1.5  Scope of Study"),
  P([B("In scope (extended since the proposal). "), T("Log sources have grown from the originally proposed AWS CloudTrail and Azure AD to four real formats — adding Cloudflare Access and GitHub Events — all reduced to one internal schema. Datasets: CERT Insider Threat Dataset r4.2 (1,000 users, 70 insiders) for the endpoint model, and the flaws.cloud AWS CloudTrail dataset (1.94 million events) for a second cloud-native model. Models: Isolation Forest and Autoencoder for unsupervised detection, with a rule-based and rarity-based scorer for live triage. Explainability: SHAP KernelExplainer plus an LLM analyst assistant. Dashboard: a React/Next.js analyst interface. Deployment: Docker locally and a live HuggingFace Space.")]),
  P([B("Out of scope. "), T("Real-time Kafka streaming, automated model-drift detection, and network packet-level intrusion detection remain deferred to future work; this project targets application-layer behavioural logs.")]),
];

// ---- 2. Literature Review ----
const lit = [
  H1("2.  Literature Review and Research Gap"),
  H2("2.1  User and Entity Behaviour Analytics"),
  P("Modern UEBA platforms ingest operational data from multiple log sources, build statistical behavioural profiles per entity, and raise alerts when observed activity deviates from the established baseline. Sharma et al. (2024) identify behavioural profiling, peer-group contextualisation, and anomaly scoring as the three foundational components of any UEBA architecture. Inayat et al. (2024), through a systematic review of 89 papers, demonstrate that most current implementations fail to address the black-box interpretability problem, which they identify as the primary barrier to analyst adoption."),
  H2("2.2  Unsupervised Anomaly Detection for Insider Threats"),
  P("Labelled insider-attack datasets are rare, legally restricted, and domain-specific, which makes supervised learning impractical in production. Unsupervised approaches circumvent this by modelling normality from unlabelled data and flagging behaviour that deviates from a learned baseline. Isolation Forest has become a standard baseline owing to its linear time complexity and resistance to the curse of dimensionality (Datta et al., 2021). Autoencoder-based detection captures non-linear joint feature distributions by compressing normal patterns into a low-dimensional latent space; anomalous inputs then produce elevated mean-squared reconstruction error that serves as the anomaly score. Kotb et al. (2025) report that reconstruction-based deep models achieve strong detection performance on the CERT benchmark, including against AI-generated insider behaviour."),
  H2("2.3  Explainable AI in Cybersecurity"),
  P("SHAP (SHapley Additive exPlanations) assigns each feature a contribution value reflecting its marginal impact on a model's output, and its model-agnostic KernelExplainer supports neural networks. Datta et al. (2021) show that SHAP integration in intrusion detection significantly reduces mean analyst investigation time per alert by enabling rapid triage. Beyond academic motivation, the EU AI Act (European Parliament, 2024) mandates explainability for high-risk AI systems in security-critical domains, providing a regulatory imperative for transparent alerting."),
  H2("2.4  Existing Open-Source Tools and Research Gap"),
  P("Several mature open-source tools address parts of the insider-detection workflow, but none combines all four required capabilities. Wazuh (Wazuh, 2025) is a widely deployed SIEM/XDR that correlates logs against signature and rule sets but performs no behavioural machine learning. Elastic Security on the ELK stack (Elastic, 2025) offers the closest functionality, providing unsupervised anomaly-detection jobs; however, that machine-learning tier sits behind a paid commercial licence and its alerts remain unexplained. OpenUBA (OpenUBA, 2024) is an open big-data UEBA framework but is early-stage and ships no production detection models, while HELK (Rodriguez, 2024) provides a hunting-oriented ELK distribution without per-user behavioural baselining. For alert handling rather than detection, TheHive and Cortex (TheHive Project, 2024) deliver open-source incident-response case management and analyst routing. The capability matrix below summarises the gap: no surveyed open-source detector simultaneously provides multi-cloud normalisation, unsupervised behavioural detection, and per-alert explainability under a fully free licence."),
  table([2480, 1280, 1500, 1280, 2820], [
    ["Capability", "Wazuh", "Elastic Security", "OpenUBA", "This project"],
    ["Multi-cloud log normalisation", "Partial", "Yes", "No", "Yes (4 sources)"],
    ["Adaptive behavioural baseline", "No", "Partial", "Partial", "Yes (rolling + peer)"],
    ["Unsupervised ML detection", "No", "Paid tier", "Partial", "Yes (AE + IF)"],
    ["Per-alert explainability", "No", "No", "No", "Yes (SHAP + LLM)"],
    ["Fully open-source / free", "Yes", "Partial", "Yes", "Yes"],
  ]),
  caption("Table 1.  Capability comparison of open-source UEBA / SIEM tools versus the proposed platform."),
];

// ---- 3. System Design & Architecture ----
const design = [
  H1("3.  System Design and Architecture"),
  P("The platform implements a decoupled, layered pipeline in which each stage communicates through well-defined interfaces, so any layer can be replaced without affecting the others. Figure 1 shows the full architecture and the technology used at each layer."),
  img("results/report_png/architecture.png", 520, 388),
  caption("Figure 1.  System architecture and tool stack, from multi-cloud ingestion to the analyst dashboard."),
  H2("3.1  Multi-Cloud Log Normalisation"),
  P("The normalisation layer is the primary architectural contribution. Each provider uses a structurally distinct JSON schema: AWS CloudTrail exposes eventTime, userIdentity.userName, eventName, and sourceIPAddress; Azure AD uses createdDateTime, userPrincipalName, appDisplayName, and ipAddress; Cloudflare Access uses created_at, user_email, and ip_address with a reliable country field; GitHub Events uses actor.login, type, and repo. A router dispatches each record to a source-specific parser that maps it to a unified eight-field schema — {timestamp, user, action, source_ip, bytes_transferred, resource, location_country, source_system}. This decouples the machine-learning pipeline from any provider: adding a new source requires only one additional parser function (NFR4)."),
  H2("3.2  Feature Engineering and Behavioural Baselines"),
  P("Normalised events are aggregated into per-user vectors along two tracks. For CERT endpoint data, 71 daily behavioural features span logon, file, device, email, and HTTP activity, with cross-source interaction features (for example, usb_and_file co-occurrence — the signature of USB exfiltration). A 30-day rolling window computes per-user means and standard deviations using shift(1) to prevent data leakage, and K-Means assigns each user to one of five behavioural peer groups, fitted on normal users only to prevent insider contamination. For cloud data, 12 features per user-day capture API behaviour: event volume, unique actions, unique resources, unique IPs, after-hours and sensitive events, IAM/STS calls, data-exfiltration calls, admin actions, and assume-role events."),
  H2("3.3  Detection Engines"),
  P("Four detectors run over the engineered features, of which the Autoencoder is adopted as the final detector and the remaining three serve as comparison baselines. A rule scorer and a source-agnostic rarity scorer (six flags: first-time action, new IP, off-hours, high volume, sensitive resource, and new-country geo-rarity) provide immediate live triage with no training, while an Isolation Forest (500 estimators, contamination 7%) provides an unsupervised statistical baseline. The Autoencoder itself is an encoder-bottleneck-decoder network trained only on normal users, so that anomalous behaviour yields elevated reconstruction error; two are maintained — a 71-dimensional CERT model and a 12-dimensional cloud-native model — and cloud-source events are routed to the cloud model automatically. A weighted IF+AE average was also evaluated, but because it underperforms the standalone Autoencoder (Section 5.1), the Autoencoder reconstruction error is used directly as the final risk score rather than a fused ensemble."),
  H2("3.4  Explainability and Analyst Assistance"),
  P("SHAP KernelExplainer is applied directly to the Autoencoder reconstruction-error function. Each flagged user receives a ranked list of feature attributions and a plain-English reason string, for example: “Flagged because: USB events (38% contribution, above baseline); files accessed (29%, above baseline); after-hours logins (18%, above baseline).” An LLM analyst assistant (using free-tier Gemini, DeepSeek, or Groq providers) converts these attributions into natural-language triage guidance. Both are surfaced on the dashboard alongside the numeric risk score, directly satisfying the EU AI Act transparency requirement (European Parliament, 2024)."),
  H2("3.5  Tools and Technology Stack"),
  P("The platform is built entirely on open-source libraries. The detection engines use PyTorch (Ansel et al., 2024) for the two Autoencoders and scikit-learn (scikit-learn developers, 2025) for the Isolation Forest, with SHAP (Lundberg, 2024) supplying model-agnostic per-alert explanations. The service layer uses FastAPI (Ramirez, 2024) for the asynchronous REST API and React with Next.js for the analyst dashboard, while the models are trained and analysed with Pandas and NumPy. Table 2 maps each tool to its architectural layer."),
  table([2100, 3000, 4260], [
    ["Layer", "Technology", "Purpose"],
    ["Data / EDA", "Python, Pandas, NumPy", "Feature engineering, baselines, exploration"],
    ["Machine learning", "PyTorch, scikit-learn, SHAP", "Autoencoders, Isolation Forest, explainability"],
    ["Backend", "FastAPI, SQLAlchemy", "REST API, real-time /ingest, score persistence"],
    ["Storage", "SQLite / PostgreSQL", "event_store and live_scores tables"],
    ["Analyst assist", "Gemini / DeepSeek / Groq", "Natural-language alert triage"],
    ["Frontend", "React, Next.js, Recharts, Tailwind", "Analyst dashboard and SHAP visualisation"],
    ["Deployment", "Docker, HuggingFace Space", "Containerised local + live hosted demo"],
    ["Datasets", "CERT r4.2, flaws.cloud", "Endpoint and cloud evaluation"],
  ]),
  caption("Table 2.  Technology stack by architectural layer."),
];

// ---- 4. Implementation ----
const impl = [
  H1("4.  Implementation Progress"),
  P("All core functional requirements (FR1-FR8) have been implemented and are operational. The following capabilities are complete:"),
  bullet([B("Four-source ingestion. "), T("Source-specific parsers for AWS CloudTrail, Azure AD, Cloudflare Access, and GitHub Events feed a single normaliser, validated end-to-end through the FastAPI POST /ingest endpoint with Pydantic schema enforcement.")]),
  bullet([B("Dual Autoencoders. "), T("The CERT 71-dimensional model and a newly trained 12-dimensional cloud-native model (best validation loss 0.041 over 200 epochs) are loaded as singletons and selected automatically by event source.")]),
  bullet([B("Real-time scoring and persistence. "), T("Each ingested event updates a live_scores table holding the Autoencoder live score, rule score, and rarity score, exposed through a GET /users/{id}/live-score endpoint and rendered as a live badge on the dashboard.")]),
  bullet([B("Explainability and assistance. "), T("SHAP attributions and an LLM-generated reason string accompany every high-risk alert; a demo page visualises the six rarity signals per event.")]),
  bullet([B("Deployment. "), T("The full stack runs through a single docker-compose command and is mirrored on a live HuggingFace Space for demonstration.")]),
  P("A cloud-native feature extractor, dataset builder, and training script were added to convert 1.94 million raw flaws.cloud CloudTrail records (30 identities, 4,569 user-days) into a labelled feature set in which Level5 and Level6 — the documented CTF privilege-escalation actors — serve as ground-truth attackers."),
];

// ---- 5. Evaluation ----
const evalSec = [
  H1("5.  Evaluation and Results"),
  P("Models were evaluated offline against ground-truth labels. The CERT split contains 1,000 users of whom 70 (7%) are malicious insiders — a severe class imbalance, so the area under the precision-recall curve (AUPRC) is reported alongside AUROC. Thresholds are chosen to maximise F1 on the precision-recall curve."),
  H2("5.1  Endpoint Detection (CERT r4.2)"),
  table([2640, 1180, 1180, 1180, 1180, 1180, 1160], [
    ["Model", "AUROC", "AUPRC", "F1", "Precision", "Recall", "Threshold"],
    ["Autoencoder (final)", "0.976", "0.851", "0.787", "0.877", "0.714", "0.066"],
    ["Weighted Avg (IF+AE)", "0.951", "0.740", "0.726", "0.954", "0.586", "0.308"],
    ["Isolation Forest", "0.860", "0.206", "0.379", "0.235", "0.971", "0.310"],
    ["Rule-based", "0.859", "0.207", "0.367", "0.259", "0.629", "0.353"],
  ]),
  caption("Table 3.  Detector performance on CERT r4.2 (1,000 users, 70 insiders). The Autoencoder is the adopted final detector; the others are comparison baselines."),
  P("The Autoencoder is the strongest detector, achieving AUROC 0.976 and AUPRC 0.851 — a decisive margin over the Isolation Forest (AUPRC 0.206) and rule-based (AUPRC 0.207) baselines, directly answering RQ4. Critically, fusing the Isolation Forest into a weighted IF+AE average (AUROC 0.951, AUPRC 0.740) lowers performance relative to the standalone Autoencoder, because the noisier Isolation Forest dilutes the Autoencoder's high-precision signal; this is why no fused ensemble is adopted and the Autoencoder reconstruction error is used directly as the final score. The Isolation Forest and rule baselines achieve high recall but very low precision, confirming the false-positive problem that motivates this work, whereas the Autoencoder balances precision (0.877) and recall (0.714). Its AUROC of 0.976 corresponds to roughly 90% of the supervised performance ceiling while requiring no labelled training data, answering RQ3."),
  img("results/report_png/roc.png", 370, 301),
  caption("Figure 2.  ROC curves for the Autoencoder and three baselines on CERT r4.2."),
  P("At the F1-optimal Autoencoder threshold the system correctly identifies the majority of insiders while keeping false positives low across 930 normal users, as shown in the confusion matrix below."),
  img("results/report_png/confusion.png", 300, 263),
  caption("Figure 3.  Autoencoder confusion matrix at the F1-optimal threshold."),
  H2("5.2  Live-Pipeline Validation (Closing the Evaluation Loop)"),
  P("The metrics in Table 3 score a static results file produced by the offline training notebook. They do not, by themselves, prove that the deployed /ingest pipeline — which performs its own feature aggregation, scaling, and peer-ratio computation at request time — reproduces that detection performance. To close this evaluation loop, a replay harness drives the live model file, scaler, and feature pipeline over all 1,000 cohort users, reconstructed from 330,452 user-days of behavioural features, and recomputes the Autoencoder score exactly as the production endpoint would, with peer-group baselines active. Table 4 compares the replayed live pipeline against the offline benchmark on the identical user set."),
  table([4360, 2500, 2500], [
    ["Pipeline", "AUROC", "AUPRC"],
    ["Offline (static results file)", "0.976", "0.851"],
    ["Live pipeline (replayed /ingest path)", "0.917", "0.315"],
  ]),
  caption("Table 4.  Offline benchmark versus the replayed live detection pipeline on the same 1,000 CERT users."),
  P("The live pipeline preserves the offline ranking strongly (AUROC 0.917), confirming that the deployed system genuinely separates insiders from normal users rather than replaying a precomputed file. However, the absolute scores diverge (Pearson r = 0.36, mean absolute difference 0.38), which lowers the precision-recall area to 0.315. This calibration gap — invisible to any offline-only evaluation — arises from feature-engineering differences between the live extractor and the training notebook, a scikit-learn version drift between the environments that fit and load the scaler, and the online reconstruction of the unique-host feature. The practical implication is that ranking-based alerting (top-N risk) transfers faithfully to production, whereas any fixed score threshold must be recalibrated against live traffic — demonstrating why deployment-time validation, not offline benchmarking alone, is necessary before an insider-detection model can be trusted in operation."),
  H2("5.3  Explainability"),
  P("SHAP analysis over the flagged population confirms that detection is driven by interpretable behavioural features rather than spurious correlations. Figure 4 ranks the features by mean absolute SHAP contribution; device and file-access behaviour dominate, matching the known signature of the USB-exfiltration scenario."),
  img("results/report_png/shap.png", 430, 286),
  caption("Figure 4.  Top feature importances by mean |SHAP value| across flagged users."),
  H2("5.4  Cloud-Native Detection (flaws.cloud)"),
  P("To validate generalisation beyond endpoint data, the 12-dimensional cloud Autoencoder was trained on normal AWS CloudTrail behaviour and tested against the Level5/Level6 privilege-escalation actors. It achieves AUROC 0.724 — a substantial improvement over the 0.5 random baseline — with attackers scoring on average more than twice the calibrated normal threshold. The principal false positive is an automated security-scanning identity (SecurityMonkey), whose high-volume behaviour is explainable. This demonstrates that the same architecture transfers from synthetic endpoint logs to real cloud API attacks, answering RQ2."),
  P([B("Summary against success criteria. "), T("The recommended Autoencoder exceeds both proposal targets: AUROC 0.976 against a target of ≥0.90 (NFR2), and F1 0.787 against a target of ≥0.70. Every high-risk alert is accompanied by at least three SHAP-attributed features (NFR3), and the live /ingest path returns scores well within the two-second response budget (NFR1).")]),
];

// ---- 6. Discussion ----
const discussion = [
  H1("6.  Discussion and Limitations"),
  P("The results confirm the central hypothesis: an unsupervised, reconstruction-based model can detect insider threats at near-supervised accuracy while remaining deployable where labelled data is legally unavailable. An important secondary finding is that score fusion did not help: the high-precision Autoencoder outperforms a weighted IF+AE average, because blending in the low-precision Isolation Forest reintroduces the very false positives the Autoencoder suppresses. The standalone Autoencoder is therefore adopted as the final detector, with the Isolation Forest and rule scorers retained only as interpretive baselines. Adding SHAP and LLM explanations addresses the interpretability barrier identified by Inayat et al. (2024) and the regulatory requirement of the EU AI Act (European Parliament, 2024)."),
  P("A further methodological finding strengthens confidence in the deployment. Replaying the live /ingest pipeline over the full cohort (Section 5.2) confirmed that the production path preserves the offline ranking at AUROC 0.917, while exposing a score-calibration gap (Pearson r = 0.36) that offline evaluation alone would have concealed. This validates ranking-based alerting for production use while motivating live-traffic threshold recalibration."),
  P("Several limitations remain. The CERT dataset is synthetic, so absolute performance may not transfer directly to production telemetry; the cloud Autoencoder's lower AUROC (0.724) reflects the harder, noisier reality of real CloudTrail logs and a small attacker population. The cloud model also currently treats each user-day independently, ignoring temporal sequence. Finally, SHAP KernelExplainer is computationally expensive, which constrains real-time explanation throughput."),
];

// ---- 7. Conclusion ----
const conclusion = [
  H1("7.  Conclusion and Future Work"),
  P("This report has presented a cloud-native, multi-source, explainable UEBA platform that meets all four research objectives. The system normalises four real cloud log formats into one schema, detects insider behaviour with two label-free Autoencoders, and explains every alert through SHAP and an LLM assistant on a deployed analyst dashboard. On CERT r4.2 it achieves AUROC 0.976 and F1 0.787, decisively outperforming rule-based and isolation baselines and reaching about 90% of the supervised ceiling without labels; on real flaws.cloud data it reaches AUROC 0.724 against documented privilege-escalation attacks."),
  P("Future work will introduce a Transformer-Autoencoder to model temporal event sequences, map alerts to the MITRE ATT&CK framework for SOC integration, add real-time streaming ingestion, and implement automated model-drift detection so baselines adapt as user behaviour evolves."),
  P([B("Analyst alert distribution. "), T("A follow-the-sun routing layer is also planned. Rather than assigning alerts by analyst skill rating — which is difficult to quantify objectively and falls outside the unsupervised-detection scope of this project — a lightweight rule would distribute each alert to an on-shift analyst by timezone and severity tier, so that an alert raised at 03:00 in one region is handled by an awake analyst elsewhere. This would build on established open-source case-management tooling such as TheHive and Cortex (TheHive Project, 2024) rather than reinventing incident-response workflow.")]),
];

// ---- References (all within 5 years) ----
const ref = (t) => new Paragraph({ spacing: { after: 100, line: 264 },
  indent: { left: 460, hanging: 460 }, children: [new TextRun({ text: t, size: 21 })] });
const references = [
  H1("References"),
  ref("Ansel, J., Yang, E., He, H., Gimelshein, N., Jain, A., Voznesensky, M., et al. (2024). PyTorch 2: Faster machine learning through dynamic Python bytecode transformation and graph compilation. Proceedings of the 29th ACM International Conference on Architectural Support for Programming Languages and Operating Systems (ASPLOS 2024). https://doi.org/10.1145/3620665.3640366"),
  ref("Datta, J., Dasgupta, S., Dasgupta, R., & Reddy, K. R. (2021). Real-time threat detection in UEBA using unsupervised learning algorithms. Proceedings of IEEE IEMENTech 2021. https://doi.org/10.1109/IEMENTech53263.2021.9614874"),
  ref("Elastic. (2025). Elastic Security: SIEM and security analytics documentation. https://www.elastic.co/security"),
  ref("European Parliament. (2024). Regulation (EU) 2024/1689 of the European Parliament and of the Council — Artificial Intelligence Act. Official Journal of the European Union."),
  ref("Inayat, U., Farzan, M., Mahmood, S., Zia, M. F., Hussain, S., & Pallonetto, F. (2024). Insider threat mitigation: Systematic literature review. Ain Shams Engineering Journal, 15(12), 103068. https://doi.org/10.1016/j.asej.2024.103068"),
  ref("Kotb, H. M., Gaber, T., AlJanah, S., Zawbaa, H. M., & Alkhathami, M. (2025). A novel deep synthesis-based insider intrusion detection (DS-IID) model for malicious insiders and AI-generated threats. Scientific Reports, 15(1), 207. https://doi.org/10.1038/s41598-024-84303-x"),
  ref("Lundberg, S. (2024). SHAP: SHapley Additive exPlanations (Version 0.46) [Software]. https://github.com/shap/shap"),
  ref("OpenUBA. (2024). OpenUBA: A free and open big-data security analytics platform [Software]. https://github.com/GACWR/OpenUBA"),
  ref("Ponemon Institute. (2025). Cost of insider risks global report 2025. Proofpoint."),
  ref("Ramirez, S. (2024). FastAPI documentation. https://fastapi.tiangolo.com"),
  ref("Rodriguez, R. (2024). HELK: The Hunting ELK [Software]. https://github.com/Cyb3rWard0g/HELK"),
  ref("scikit-learn developers. (2025). scikit-learn: Machine learning in Python (Version 1.5) [Software]. https://scikit-learn.org"),
  ref("Sharma, G., Thakur, A., & Tiwari, C. (2024). Developing a comprehensive framework for user and entity behavior analytics (UEBA): Integrating advanced machine learning and contextual insights. Journal of Communication Engineering & Systems."),
  ref("TheHive Project. (2024). TheHive: Open-source security incident response platform [Software]. https://github.com/TheHive-Project/TheHive"),
  ref("Verizon. (2025). 2025 data breach investigations report. Verizon Enterprise Solutions."),
  ref("Wazuh. (2025). The open source security platform. GitHub repository. https://github.com/wazuh/wazuh"),
];

// ---- TOC page ----
const toc = [
  new Paragraph({ spacing: { after: 160 }, children: [new TextRun({ text: "Table of Contents", bold: true, size: 30, color: NAVY })] }),
  new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-1" }),
  new Paragraph({ children: [new PageBreak()] }),
];

// ============================================================================
const doc = new Document({
  creator: "Yap Zhe Cheng",
  title: "Cloud-Native UEBA Platform for Insider Threat Detection",
  styles: {
    default: { document: { run: { font: "Calibri", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, color: NAVY, font: "Calibri" },
        paragraph: { spacing: { before: 260, after: 140 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 25, bold: true, color: "1F3864", font: "Calibri" },
        paragraph: { spacing: { before: 200, after: 110 }, outlineLevel: 1 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 540, hanging: 280 } } } }] },
      { reference: "ord", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
    ],
  },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "Page ", size: 18, color: "888888" }),
                 new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "888888" })] })] }) },
    children: [
      ...titlePage,
      ...intro,
      ...lit,
      ...design,
      ...impl,
      ...evalSec,
      ...discussion,
      ...conclusion,
      ...references,
    ],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("Yap Zhe Cheng Progress Report.docx", buf);
  console.log("WROTE Yap Zhe Cheng Progress Report.docx", buf.length, "bytes");
});
