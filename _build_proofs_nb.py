# -*- coding: utf-8 -*-
"""Build evaluation_proofs.ipynb — a self-contained Colab notebook that
re-runs the CERT, Cloud, and GitHub evaluations from scratch."""
import base64, json

CLOUD_B64 = base64.b64encode(open("data/processed/cloud_features.parquet", "rb").read()).decode()

# Combine the saved real GitHub events into one snapshot and embed (reproducible)
import glob
_gh_events = []
for _f in sorted(glob.glob("data/raw/github/events_p*.json")):
    _gh_events += json.load(open(_f, encoding="utf-8"))
GH_B64 = base64.b64encode(json.dumps(_gh_events).encode()).decode()

intro_md = """# Argus — Evaluation Proofs (self-contained)

Run **Runtime → Run all**. No setup, no Google Drive, no file uploads needed:

* **Section 1 — CERT autoencoder, inductive 5-fold CV.** Downloads the real CERT feature
  table from the public Hugging Face Space and retrains the one-class autoencoder per fold,
  scoring held-out users only. Expected: AUROC ~0.96.
* **Section 2 — Cloud autoencoder, inductive 5-fold CV.** Uses the flaws.cloud feature table
  embedded in this notebook. Expected: AUROC ~0.72 (limited by ~2 attacker entities).
* **Section 3 — GitHub semi-synthetic.** Pulls real live events from the GitHub public API,
  injects labelled synthetic attacks, scores with the rarity detector. Expected: AUROC ~0.99.

Every number is produced by code in *your* environment — this is the reproducibility proof.
"""

cert_md = "## Section 1 — CERT autoencoder · inductive 5-fold cross-validation"
cert_code = r'''import urllib.request, numpy as np, pandas as pd, torch, torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import roc_auc_score, average_precision_score

HF = "https://huggingface.co/spaces/Zhe-cyber/argus-ueba/resolve/main/data/processed/"
urllib.request.urlretrieve(HF + "daily_features_v4.parquet", "daily.parquet")
urllib.request.urlretrieve(HF + "user_scores_v4.csv", "scores.csv")

SEED = 42; np.random.seed(SEED)
ROLE = ['login_count_sum','files_accessed_sum','usb_events_sum','email_count_sum']
daily = pd.read_parquet("daily.parquet")
base = [c for c in daily.columns if c not in ('user','date_d','y_true')]
g = daily.groupby('user')
U = pd.concat([g[base].sum().add_suffix('_sum'), g[base].mean().add_suffix('_mean'),
               g[base].max().add_suffix('_max')], axis=1).reset_index()
for f in ('files_accessed','usb_events','after_hours_count'):
    U[f+'_burst_ratio'] = np.minimum(U[f+'_max']/np.maximum(U[f+'_mean'],1e-3), 50.0)
U['usb_file_interaction'] = U['has_usb_sum']*U['files_accessed_max']
lab = pd.read_csv("scores.csv")[['user','is_insider']]
U = U.merge(lab, on='user', how='left').fillna({'is_insider':0})
static = [c for c in U.columns if c.endswith(('_sum','_mean','_max','_burst_ratio')) or c=='usb_file_interaction']
y = U['is_insider'].values.astype(int); role = U[ROLE].values.astype('float32')
print(f"{len(U)} users, {int(y.sum())} insiders, {len(static)+4} features")

def mk(d):
    class AE(nn.Module):
        def __init__(s,d):
            super().__init__()
            s.e=nn.Sequential(nn.Linear(d,128),nn.BatchNorm1d(128),nn.LeakyReLU(.1),nn.Dropout(.3),
                nn.Linear(128,64),nn.BatchNorm1d(64),nn.LeakyReLU(.1),nn.Dropout(.2),
                nn.Linear(64,32),nn.BatchNorm1d(32),nn.LeakyReLU(.1),nn.Linear(32,16),nn.LeakyReLU(.1))
            s.d=nn.Sequential(nn.Linear(16,32),nn.LeakyReLU(.1),nn.Linear(32,64),nn.BatchNorm1d(64),
                nn.LeakyReLU(.1),nn.Dropout(.2),nn.Linear(64,128),nn.BatchNorm1d(128),nn.LeakyReLU(.1),nn.Linear(128,d))
        def forward(s,x): return s.d(s.e(x))
    return AE(d)

def peer(role, trn):
    rs=StandardScaler().fit(role[trn]); km=KMeans(5,random_state=SEED,n_init=10).fit(rs.transform(role[trn]))
    a=pd.DataFrame(role[trn],columns=ROLE); a['pg']=km.predict(rs.transform(role[trn])); pm=a.groupby('pg')[ROLE].mean()
    pg=km.predict(rs.transform(role)); out=np.zeros((len(role),len(ROLE)),'float32')
    for j,f in enumerate(ROLE): out[:,j]=role[:,j]/np.maximum(pd.Series(pg).map(pm[f]).values,1.0)
    return out

skf=StratifiedKFold(5,shuffle=True,random_state=SEED); oof=np.zeros(len(U)); fold=[]
for k,(tr,te) in enumerate(skf.split(U,y),1):
    trn=tr[y[tr]==0]; X=np.hstack([U[static].values.astype('float32'),peer(role,trn)]).astype('float32')
    sc=StandardScaler().fit(X[trn]); Xs=sc.transform(X).astype('float32')
    torch.manual_seed(SEED); m=mk(Xs.shape[1]); opt=torch.optim.Adam(m.parameters(),1e-3,weight_decay=1e-4); lf=nn.MSELoss()
    dl=DataLoader(TensorDataset(torch.tensor(Xs[trn])),batch_size=64,shuffle=True,drop_last=True); m.train()
    for _ in range(150):
        for (b,) in dl: opt.zero_grad(); l=lf(m(b),b); l.backward(); opt.step()
    m.eval()
    with torch.no_grad(): e=((torch.tensor(Xs[te])-m(torch.tensor(Xs[te])))**2).mean(1).numpy()
    oof[te]=e; fold.append(roc_auc_score(y[te],e)); print(f"  fold {k}: held-out AUROC={fold[-1]:.4f}")
print("\nCERT inductive 5-fold AUROC: %.4f +/- %.4f"%(np.mean(fold),np.std(fold)))
print("Pooled OOF AUROC: %.4f | AUPRC: %.4f  (transductive reference 0.976)"%(roc_auc_score(y,oof),average_precision_score(y,oof)))'''

cloud_md = "## Section 2 — Cloud autoencoder · inductive 5-fold cross-validation (flaws.cloud)"
cloud_code = ('import base64, io\n'
    '_CLOUD_B64 = "' + CLOUD_B64 + '"\n'
    + r'''import numpy as np, pandas as pd, torch, torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, average_precision_score

SEED=42; np.random.seed(SEED)
CLOUD_FEATURES=['event_count','unique_actions','unique_resources','unique_ips','after_hours_events',
 'sensitive_events','error_events','new_action_count','iam_sts_events','data_exfil_events',
 'admin_events','assume_role_events']
df = pd.read_parquet(io.BytesIO(base64.b64decode(_CLOUD_B64)))
X = df[CLOUD_FEATURES].fillna(0).values.astype('float32'); y = df['is_attacker'].values.astype(int)
print(f"{len(df)} user-days, {int(y.sum())} attacker-days, {df[df.is_attacker==1]['user'].nunique()} attacker entities")
print("NOTE: Level6 ~= 99% of attacker-days -> ~2-entity case study, not a robust benchmark")

def mk(d):
    class AE(nn.Module):
        def __init__(s,d):
            super().__init__()
            s.e=nn.Sequential(nn.Linear(d,32),nn.LeakyReLU(.1),nn.Linear(32,16),nn.LeakyReLU(.1),nn.Linear(16,8),nn.LeakyReLU(.1))
            s.d=nn.Sequential(nn.Linear(8,16),nn.LeakyReLU(.1),nn.Linear(16,32),nn.LeakyReLU(.1),nn.Linear(32,d))
        def forward(s,x): return s.d(s.e(x))
    return AE(d)

skf=StratifiedKFold(5,shuffle=True,random_state=SEED); oof=np.zeros(len(y)); fold=[]
for tr,te in skf.split(X,y):
    trn=tr[y[tr]==0]; sc=StandardScaler().fit(X[trn]); Xs=sc.transform(X).astype('float32')
    torch.manual_seed(SEED); m=mk(X.shape[1]); opt=torch.optim.Adam(m.parameters(),1e-3,weight_decay=1e-5); lf=nn.MSELoss()
    dl=DataLoader(TensorDataset(torch.tensor(Xs[trn])),batch_size=64,shuffle=True,drop_last=True); m.train()
    for _ in range(200):
        for (b,) in dl: opt.zero_grad(); l=lf(m(b),b); l.backward(); opt.step()
    m.eval()
    with torch.no_grad(): e=((torch.tensor(Xs[te])-m(torch.tensor(Xs[te])))**2).mean(1).numpy()
    oof[te]=e; fold.append(roc_auc_score(y[te],e))
print("\nCloud inductive 5-fold AUROC: %.4f +/- %.4f"%(np.mean(fold),np.std(fold)))
print("Pooled OOF AUROC: %.4f | AUPRC: %.4f  (reported same-dataset 0.724)"%(roc_auc_score(y,oof),average_precision_score(y,oof)))''')

gh_md = ("## Section 3 — GitHub semi-synthetic (real events + injected attacks)\n\n"
         "This cell downloads the **actual production** `normalizer.py` and `rarity_scorer.py` from "
         "the public HF Space and scores with that real code (not a re-implementation), on an "
         "embedded snapshot of real GitHub events plus injected labelled attacks. Expected AUROC ~0.99.")
gh_code = ('import urllib.request, os, base64, json, random, numpy as np\n'
    'from datetime import datetime, timedelta, timezone\n'
    'from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve\n'
    '\n'
    '# 1. Pull the REAL production modules so we score with the actual code\n'
    'os.makedirs("backend", exist_ok=True); open("backend/__init__.py","w").close()\n'
    'HFB="https://huggingface.co/spaces/Zhe-cyber/argus-ueba/resolve/main/backend/"\n'
    'for _m in ("models.py","normalizer.py","rarity_scorer.py"):\n'
    '    urllib.request.urlretrieve(HFB+_m, f"backend/{_m}")\n'
    'from backend.normalizer import parse_github_events\n'
    'from backend.rarity_scorer import compute_rarity_flags, rarity_score\n'
    '\n'
    '# 2. Embedded snapshot of real GitHub events (reproducible)\n'
    '_GH_B64 = "' + GH_B64 + '"\n'
    'real = json.loads(base64.b64decode(_GH_B64))\n'
    'print(f"{len(real)} real GitHub events (embedded snapshot)")\n'
    '\n'
    '# 3. Score each account with the REAL rarity scorer (incremental history)\n'
    'def user_risk(evs):\n'
    '    evs=sorted(evs,key=lambda e:e.get("timestamp","")); hist=[]; sc=[]\n'
    '    for e in evs: sc.append(rarity_score(compute_rarity_flags(e,hist))); hist.append(e)\n'
    '    return float(np.mean(sc)) if sc else 0.0\n'
    '\n'
    'benign={}\n'
    'for ev in real:\n'
    '    n=parse_github_events(ev)\n'
    '    if n.get("user"): benign.setdefault(n["user"],[]).append(n)\n'
    '\n'
    'rng=random.Random(42)\n'
    'SENS=["acme/prod-secrets","acme/aws-credentials","acme/ssh-keys","internal/admin-tokens",\n'
    '      "corp/password-vault","victim/private-key-store","ops/root-access","finance/db-passwords"]\n'
    'NORM=["octo/web-app","octo/api-server","team/docs","lib/utils","data/pipeline","ml/models"]\n'
    'def gh(login,typ,repo,t): return parse_github_events({"id":f"{login}{t.timestamp()}","type":typ,\n'
    '    "actor":{"login":login},"repo":{"name":repo},"payload":{"ref":"refs/heads/main","size":0},\n'
    '    "created_at":t.strftime("%Y-%m-%dT%H:%M:%SZ")})\n'
    'rows=[(0,user_risk(e)) for e in benign.values()]\n'
    'for b in range(8):  # benign high-volume CI bots (label 0)\n'
    '    cnt=rng.randint(40,120); st=datetime(2026,6,4,rng.choice([0,6,9,15,20]),0,0,tzinfo=timezone.utc)\n'
    '    rows.append((0,user_risk([gh(f"ci-bot-{b}",rng.choice(["PushEvent","PullRequestEvent","IssuesEvent","IssueCommentEvent","WatchEvent"]),rng.choice(NORM),st+timedelta(seconds=i*50)) for i in range(cnt)])))\n'
    'for a in range(10):  # overt attackers (label 1)\n'
    '    cnt=rng.randint(55,90); st=datetime(2026,6,4,rng.choice([1,2,3,4]),0,0,tzinfo=timezone.utc)\n'
    '    rows.append((1,user_risk([gh(f"overt-{a}",rng.choice(["DeleteEvent","PushEvent","DeleteEvent","PushEvent","CreateEvent"]),rng.choice(SENS),st+timedelta(seconds=i*45)) for i in range(cnt)])))\n'
    'for a in range(5):  # stealthy attackers (label 1)\n'
    '    cnt=rng.randint(3,10); st=datetime(2026,6,4,rng.choice([10,11,13,14]),0,0,tzinfo=timezone.utc)\n'
    '    rows.append((1,user_risk([gh(f"stealth-{a}",rng.choice(["PushEvent","PullRequestEvent"]),rng.choice(SENS),st+timedelta(minutes=i*25)) for i in range(cnt)])))\n'
    '\n'
    'y=np.array([r[0] for r in rows]); s=np.array([r[1] for r in rows])\n'
    'prec,rec,_=precision_recall_curve(y,s); f1=float(np.max(np.where((prec+rec)>0,2*prec*rec/(prec+rec),0)))\n'
    'print(f"\\n{len(y)} accounts, {int(y.sum())} injected attackers")\n'
    'print("GitHub semi-synthetic AUROC: %.4f | AUPRC: %.4f | best-F1: %.4f"%(roc_auc_score(y,s),average_precision_score(y,s),f1))')

def cell(t, src):
    c = {"cell_type": t, "metadata": {}, "source": src.splitlines(keepends=True)}
    if t == "code":
        c["outputs"] = []; c["execution_count"] = None
    return c

nb = {
    "cells": [
        cell("markdown", intro_md),
        cell("markdown", cert_md),  cell("code", cert_code),
        cell("markdown", cloud_md), cell("code", cloud_code),
        cell("markdown", gh_md),    cell("code", gh_code),
    ],
    "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"},
                 "language_info": {"name": "python"}, "colab": {"provenance": []}},
    "nbformat": 4, "nbformat_minor": 0,
}
json.dump(nb, open("evaluation_proofs.ipynb", "w", encoding="utf-8"), indent=1)
json.load(open("evaluation_proofs.ipynb", encoding="utf-8"))  # validate
import os
print("WROTE evaluation_proofs.ipynb", os.path.getsize("evaluation_proofs.ipynb"), "bytes,", len(nb["cells"]), "cells")
