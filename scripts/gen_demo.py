import pandas as pd
import numpy as np
from pathlib import Path

rng = np.random.default_rng(42)
n = 200
users = [f"user_{i:04d}" for i in range(n)]

ae_scores = rng.exponential(0.15, n)
ae_scores = np.clip(ae_scores, 0, 1)
ae_scores[rng.choice(n, 10, replace=False)] = rng.uniform(0.7, 1.0, 10)
ae_scores = ae_scores / ae_scores.max()

scores_df = pd.DataFrame({
    "user": users,
    "ae_score": ae_scores.round(6),
    "if_score": rng.uniform(0, 1, n).round(6),
    "rule_score": rng.integers(0, 4, n).astype(float),
    "is_insider": (ae_scores > 0.85).astype(int),
    "scenario": rng.integers(0, 4, n),
})

features = [
    "after_hours_logons", "usb_events", "email_exfil", "file_copy_count",
    "http_anomaly", "login_failures", "data_volume_mb", "unique_hosts",
]
shap_data = {"user": users}
for f in features:
    shap_data[f] = rng.normal(0, 0.05, n).round(8)

insider_mask = scores_df["is_insider"] == 1
for f in ["after_hours_logons", "usb_events", "email_exfil", "file_copy_count"]:
    arr = np.array(shap_data[f])
    arr[insider_mask] += rng.uniform(0.1, 0.3, int(insider_mask.sum()))
    shap_data[f] = arr.round(8)

shap_df = pd.DataFrame(shap_data)

demo_dir = Path(__file__).resolve().parent.parent / "demo"
demo_dir.mkdir(exist_ok=True)
scores_df.to_csv(demo_dir / "demo_scores.csv", index=False)
shap_df.to_parquet(demo_dir / "demo_shap.parquet", index=False)
print(f"Written {len(scores_df)} users to demo/")
print(f"Insiders: {int(scores_df['is_insider'].sum())}")
