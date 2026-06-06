# -*- coding: utf-8 -*-
"""Builds cloud_ae_full_pipeline.ipynb — a self-contained Colab notebook that
does the FULL cloud-AE pipeline (clean -> feature-engineer -> train -> evaluate),
faithfully porting build_cloud_dataset.py + cloud_feature_extractor.py +
train_cloud_ae.py + the inductive CV. No `backend` import needed."""
import ast, json

CELLS = []
def md(t):   CELLS.append(("markdown", t))
def code(t): CELLS.append(("code", t))

md(r"""# Cloud Autoencoder — Full Pipeline (flaws.cloud)

End-to-end, reproducible Colab notebook for the **cloud** unsupervised autoencoder, parallel to
the CERT training notebook. Stages:

1. **Data cleaning + feature engineering** — raw AWS CloudTrail (`flaws.cloud`) `.json.gz` →
   per-(user, day) 12-feature vectors with ground-truth `is_attacker` labels.
2. **Training** — one-class autoencoder trained on **normal user-days only**.
3. **Evaluation (same-dataset)** — AUROC / AUPRC separating Level5/Level6 attacker days from normal.
4. **Inductive 5-fold cross-validation** — held-out evaluation (removes transductive optimism).

**Setup:** download `flaws_cloudtrail_logs.tar` from
http://summitroute.com/downloads/flaws_cloudtrail_logs.tar (or the Kaggle mirror), extract the
`flaws_cloudtrail00.json.gz … 19.json.gz` files, and upload the folder to your Google Drive at
`MyDrive/fyp-ueba/data/raw/cloudtrail/flaws_cloudtrail_logs/`. Then **Runtime → Run all**.""")

code(r"""# --- Setup: mount Drive and point at the raw flaws.cloud logs ---
from google.colab import drive
drive.mount('/content/drive')

import os, glob
BASE = '/content/drive/MyDrive/fyp-ueba'
RAW_DIR = f'{BASE}/data/raw/cloudtrail/flaws_cloudtrail_logs'
OUT_DIR = f'{BASE}/data/processed'
MODEL_DIR = f'{BASE}/ml/models'
os.makedirs(OUT_DIR, exist_ok=True); os.makedirs(MODEL_DIR, exist_ok=True)

files = sorted(glob.glob(f'{RAW_DIR}/*.json.gz'))
print(f'Found {len(files)} CloudTrail .json.gz files in {RAW_DIR}')
assert files, 'No .json.gz files found — upload flaws_cloudtrail_logs/ to Drive (see cell above).'
SEED = 42""")

md(r"""## Stage 1 — Data cleaning & feature engineering

Faithful port of `build_cloud_dataset.py` + `cloud_feature_extractor.py`:
- parse each CloudTrail record to the unified schema, extract a clean user identity,
- drop non-user principals (bare account IDs, raw access-key/role IDs),
- group by (user, day) and compute the 12 cloud features,
- label `Level5`/`Level6` as attackers (the flaws.cloud CTF ground truth).""")

code(r"""# --- CloudTrail parsing + clean user identity (port of build_cloud_dataset.py) ---
import gzip, json, re
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np, pandas as pd

KNOWN_ATTACKERS = {'Level5', 'Level6', 'level5', 'level6'}

def parse_cloudtrail(ev):
    ui = ev.get('userIdentity', {}) or {}
    user = ui.get('userName') or ui.get('principalId') or ui.get('arn') or ''
    rp = ev.get('requestParameters') or {}
    resource = (rp.get('bucketName') or rp.get('resourceArn') or rp.get('instanceId')
                or rp.get('roleName') or rp.get('functionName') or (str(rp) if rp else ''))
    return {'timestamp': ev.get('eventTime', ''), 'user': str(user),
            'action': ev.get('eventName', ''), 'resource': str(resource),
            'ip_address': ev.get('sourceIPAddress', '')}

def clean_user(raw):
    ui = raw.get('userIdentity', {}) or {}
    if ui.get('userName'): return str(ui['userName'])
    iss = (ui.get('sessionContext') or {}).get('sessionIssuer') or {}
    if iss.get('userName'): return str(iss['userName'])
    pid = str(ui.get('principalId', ''))
    if ':' in pid:
        sn = pid.split(':', 1)[1]
        if sn and not sn.isdigit() and len(sn) < 40: return sn
    return str(ui.get('type', '')) or ''

def day_of(ts):
    if not ts: return ''
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%d')
    except Exception:
        return ts[:10]""")

code(r"""# --- The 12 cloud features (port of cloud_feature_extractor.py) ---
CLOUD_FEATURES = ['event_count','unique_actions','unique_resources','unique_ips',
    'after_hours_events','sensitive_events','error_events','new_action_count',
    'iam_sts_events','data_exfil_events','admin_events','assume_role_events']

_IAM = re.compile(r"\b(iam|sts|kms|ssm|secretsmanager|credential|getpolicyversion|listpolicies|listentitiesforpolicy|attachuserrole|detachrole|createrole|deleterole|createuser|deleteuser|createaccesskey|updateaccesskey|createloginprofile|listusers|listroles|microsoft\.authorization|microsoft\.aad|passwordprofile|passwordreset|addmember|removemember)\b", re.I)
_EXFIL = re.compile(r"\b(getobject|listobjects|listbuckets|getbucketacl|downloadobject|readfile|listfiles|listshares|downloadblob|getblob|listblobs|describeinstances|getsecretvalue|getparameter|getparameters|describedbinstances|listfunctions|getfunction|readcontents|read|download|get|list)\b", re.I)
_ADMIN = re.compile(r"\b(createuser|deleteuser|creategroup|deletegroup|createpolicy|deletepolicy|attachpolicy|detachpolicy|putrolepolicy|updateassumerolepolicy|createaccesskey|createloginprofile|updateloginprofile|changepassword|enablemfadevice|deactivatemfadevice|addusertopolicy|removeuserfromgroup|addmember|removemember|activatedirectory|createapplication|deleteapplication|runinstances|terminateinstances|startinstances|stopinstances|createbucket|deletebucket|createfunction|deletefunction)\b", re.I)
_ASSUME = re.compile(r"\b(assumerole|getsessiontoken|getfederationtoken|assumerolewithsaml|assumerolewithwebidentity|impersonation|addmember|oauth)\b", re.I)
_ERROR = re.compile(r"\b(error|denied|fail|unauthoriz|forbidden|accessdeni|not\s*found|invalid|except|throttl|limit)\b", re.I)
_SENS  = re.compile(r"\b(iam|secret|kms|admin|root|password|credential|token|key|ssm|backup|prod|production|confidential|sensitive|pii|financial|salary|internal|private|vpn|ssh)\b", re.I)

def is_off_hours(ts):
    if not ts: return False
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        else: dt = dt.astimezone(timezone.utc)
        return dt.weekday() >= 5 or not (7 <= dt.hour < 19)
    except Exception:
        return False

def aggregate_window(events, history=None):
    if not events: return {f: 0.0 for f in CLOUD_FEATURES}
    t = {f: 0.0 for f in CLOUD_FEATURES}
    sa, sr, si = set(), set(), set()
    prior = {str(e.get('action','')).lower().strip() for e in history} if history else set()
    nac = 0
    for ev in events:
        a = str(ev.get('action','')).lower().strip(); r = str(ev.get('resource','')).strip()
        ip = str(ev.get('ip_address','')).strip(); ts = str(ev.get('timestamp','')).strip()
        c = f'{a} {r}'.lower()
        sa.add(a)
        if r: sr.add(r)
        if ip and ip not in ('','127.0.0.1','::1'): si.add(ip)
        if history is not None and a and a not in prior: nac += 1; prior.add(a)
        t['event_count'] += 1
        if is_off_hours(ts): t['after_hours_events'] += 1
        if _SENS.search(r): t['sensitive_events'] += 1
        if _ERROR.search(a) or '(denied)' in a: t['error_events'] += 1
        if _IAM.search(c): t['iam_sts_events'] += 1
        if _EXFIL.search(c): t['data_exfil_events'] += 1
        if _ADMIN.search(c): t['admin_events'] += 1
        if _ASSUME.search(c): t['assume_role_events'] += 1
    t['unique_actions']=float(len(sa)); t['unique_resources']=float(len(sr))
    t['unique_ips']=float(len(si)); t['new_action_count']=float(nac)
    return t""")

code(r"""# --- Build the per-(user, day) feature table from all .json.gz files ---
user_day = defaultdict(lambda: defaultdict(list))
total = skipped = 0
for fp in files:
    with gzip.open(fp, 'rt', encoding='utf-8', errors='replace') as fh:
        try: data = json.load(fh)
        except json.JSONDecodeError: continue
    for raw in data.get('Records', data if isinstance(data, list) else []):
        try:
            ev = parse_cloudtrail(raw); ev['user'] = clean_user(raw)
        except Exception:
            continue
        u = ev['user'].strip()
        if (not u or u in ('?','HIDDEN_DUE_TO_SECURITY_REASONS') or u.isdigit()
                or u.startswith('AIDA') or u.startswith('AROA')):
            skipped += 1; continue
        d = day_of(ev['timestamp'])
        if not d: skipped += 1; continue
        user_day[u][d].append(ev); total += 1
print(f'{total:,} events kept, {skipped:,} skipped, {len(user_day)} users')

rows = []
for u, days in sorted(user_day.items()):
    prior = []
    for d in sorted(days):
        evs = days[d]
        feats = aggregate_window(evs, history=prior)
        rows.append({'user': u, 'date': d, 'is_attacker': int(u in KNOWN_ATTACKERS), **feats})
        prior.extend(evs)
df = pd.DataFrame(rows)
for c in CLOUD_FEATURES: df[c] = df[c].fillna(0.0).astype(float)
df.to_parquet(f'{OUT_DIR}/cloud_features.parquet', index=False)
print('Saved cloud_features.parquet:', df.shape,
      '| attacker user-days:', int(df.is_attacker.sum()),
      '| attacker entities:', df[df.is_attacker==1].user.nunique())
df.groupby('user')['is_attacker'].first().value_counts()""")

md(r"""## Stage 2 — Train the one-class cloud autoencoder

Port of `train_cloud_ae.py`: train on **normal user-days only** (80/20 split), architecture
`12 → 32 → 16 → 8 → 16 → 32 → 12`, Adam + cosine schedule, MSE reconstruction loss. The score
is the reconstruction error, normalised so the 95th percentile of normal maps to 0.5.""")

code(r"""import torch, torch.nn as nn, joblib
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import StandardScaler
torch.manual_seed(SEED); np.random.seed(SEED)

normal_df = df[df.is_attacker == 0].sort_values('date')
atk_df    = df[df.is_attacker == 1]
split = int(len(normal_df) * 0.8)
Xtr_raw = normal_df[CLOUD_FEATURES].values[:split].astype('float32')
Xvl_raw = normal_df[CLOUD_FEATURES].values[split:].astype('float32')
Xat_raw = atk_df[CLOUD_FEATURES].values.astype('float32')
scaler = StandardScaler().fit(Xtr_raw)
Xtr, Xvl, Xat = scaler.transform(Xtr_raw), scaler.transform(Xvl_raw), scaler.transform(Xat_raw)
print(f'train normals={len(Xtr)}  val normals={len(Xvl)}  attacker days={len(Xat)}')

class CloudAE(nn.Module):
    def __init__(s, d):
        super().__init__()
        s.e = nn.Sequential(nn.Linear(d,32), nn.LeakyReLU(.1), nn.Linear(32,16), nn.LeakyReLU(.1), nn.Linear(16,8), nn.LeakyReLU(.1))
        s.d = nn.Sequential(nn.Linear(8,16), nn.LeakyReLU(.1), nn.Linear(16,32), nn.LeakyReLU(.1), nn.Linear(32,d))
    def forward(s, x): return s.d(s.e(x))

EPOCHS = 200
model = CloudAE(len(CLOUD_FEATURES))
opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=EPOCHS)
lf = nn.MSELoss()
dl = DataLoader(TensorDataset(torch.tensor(Xtr)), batch_size=64, shuffle=True, drop_last=True)
best, best_state = 1e9, None
for ep in range(1, EPOCHS+1):
    model.train()
    for (b,) in dl:
        opt.zero_grad(); loss = lf(model(b), b); loss.backward(); opt.step()
    sch.step()
    model.eval()
    with torch.no_grad():
        vl = lf(model(torch.tensor(Xvl)), torch.tensor(Xvl)).item()
    if vl < best: best, best_state = vl, {k: v.clone() for k, v in model.state_dict().items()}
    if ep % 25 == 0 or ep == 1: print(f'  epoch {ep:>3} val={vl:.5f}')
model.load_state_dict(best_state); model.eval()

def mse(X):
    with torch.no_grad():
        r = model(torch.tensor(X)); return ((torch.tensor(X)-r)**2).mean(1).numpy()
nrm = mse(Xvl)
ae_min, ae_max = float(np.percentile(nrm,5)), float(np.percentile(nrm,95)*2.0)
torch.save({'state_dict':best_state,'input_dim':len(CLOUD_FEATURES),'features':CLOUD_FEATURES,
            'ae_min':ae_min,'ae_max':ae_max}, f'{MODEL_DIR}/cloud_ae_v1.pt')
joblib.dump(scaler, f'{MODEL_DIR}/cloud_scaler_v1.pkl')
print(f'Saved model. ae_min={ae_min:.5f} ae_max={ae_max:.5f}')
print(f'normal val mean err={nrm.mean():.5f} | attacker mean err={mse(Xat).mean():.5f}')""")

md(r"""## Stage 3 — Same-dataset evaluation (AUROC / AUPRC)

Score every user-day with the trained AE and measure how well the reconstruction error
separates attacker days (Level5/Level6) from normal days.""")

code(r"""from sklearn.metrics import roc_auc_score, average_precision_score, roc_curve
import matplotlib.pyplot as plt
Xall = scaler.transform(df[CLOUD_FEATURES].values.astype('float32'))
err = mse(Xall)
score = np.clip((err - ae_min) / max(ae_max - ae_min, 1e-9), 0, 1)
y = df['is_attacker'].values
auroc = roc_auc_score(y, score); auprc = average_precision_score(y, score)
print(f'Same-dataset AUROC = {auroc:.4f} | AUPRC = {auprc:.4f} (attacker base rate {y.mean():.3f})')
print('\nPer-entity mean normalised score:')
print(df.assign(score=score).groupby('user')['score'].mean().sort_values(ascending=False).head(12))
fpr,tpr,_ = roc_curve(y, score)
plt.figure(figsize=(5,4)); plt.plot(fpr,tpr,label=f'Cloud AE (AUROC={auroc:.3f})')
plt.plot([0,1],[0,1],'k--',alpha=.3); plt.xlabel('FPR'); plt.ylabel('TPR')
plt.title('Cloud AE — same-dataset ROC (flaws.cloud)'); plt.legend(); plt.show()""")

md(r"""## Stage 4 — Inductive 5-fold cross-validation (held-out)

Removes the transductive optimism of scoring normal user-days that were in training: each fold
retrains the AE on the training folds' **normal** days only and scores the **held-out** fold.

> **Limitation (honest):** flaws.cloud contains only ~2 distinct attacker entities (Level5,
> Level6), with Level6 ≈ 99% of attacker days — so the attacker class cannot be robustly
> cross-validated. Read the cloud result as a **2-entity real-AWS case study**, not a benchmark.""")

code(r"""from sklearn.model_selection import StratifiedKFold
Xraw = df[CLOUD_FEATURES].values.astype('float32'); y = df['is_attacker'].values.astype(int)
skf = StratifiedKFold(5, shuffle=True, random_state=SEED); oof = np.zeros(len(y)); fold = []
for tr, te in skf.split(Xraw, y):
    trn = tr[y[tr] == 0]
    sc = StandardScaler().fit(Xraw[trn]); Xs = sc.transform(Xraw).astype('float32')
    torch.manual_seed(SEED); m = CloudAE(Xraw.shape[1])
    o = torch.optim.Adam(m.parameters(), 1e-3, weight_decay=1e-5); lf2 = nn.MSELoss()
    d2 = DataLoader(TensorDataset(torch.tensor(Xs[trn])), batch_size=64, shuffle=True, drop_last=True)
    m.train()
    for _ in range(200):
        for (b,) in d2: o.zero_grad(); l = lf2(m(b), b); l.backward(); o.step()
    m.eval()
    with torch.no_grad(): e = ((torch.tensor(Xs[te]) - m(torch.tensor(Xs[te])))**2).mean(1).numpy()
    oof[te] = e; fold.append(roc_auc_score(y[te], e))
print('Inductive 5-fold AUROC: %.4f +/- %.4f' % (np.mean(fold), np.std(fold)))
print('Pooled out-of-fold AUROC: %.4f | AUPRC: %.4f' % (roc_auc_score(y, oof), average_precision_score(y, oof)))""")

# ---- assemble + validate ----
def cell(t, src):
    c = {"cell_type": t, "metadata": {}, "source": src.splitlines(keepends=True)}
    if t == "code":
        c["outputs"] = []; c["execution_count"] = None
        ast.parse(src)   # fail fast if any code cell has a syntax error
    return c

nb = {"cells": [cell(t, s) for t, s in CELLS],
      "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"},
                   "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}
with open("cloud_ae_full_pipeline.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)
json.load(open("cloud_ae_full_pipeline.ipynb", encoding="utf-8"))
print("BUILT cloud_ae_full_pipeline.ipynb —", len(CELLS), "cells, all code cells parse OK")
