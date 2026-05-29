"""
upload_to_hf_space.py — Upload model + data files to the correct paths
inside the Argus HuggingFace Space repo.

Usage:
    python scripts/upload_to_hf_space.py --token hf_xxx

Or set HF_TOKEN env var and just run:
    python scripts/upload_to_hf_space.py
"""
import argparse
import os
from pathlib import Path

from huggingface_hub import HfApi

SPACE_REPO = "Zhe-cyber/argus-ueba"

# (local_path_relative_to_project_root, path_in_space_repo)
FILES = [
    ("ml/models/autoencoder_v4.pt",              "ml/models/autoencoder_v4.pt"),
    ("ml/models/scaler_v4.pkl",                  "ml/models/scaler_v4.pkl"),
    ("data/processed/user_scores_v4.csv",        "data/processed/user_scores_v4.csv"),
    ("data/processed/shap_values_v4.parquet",    "data/processed/shap_values_v4.parquet"),
    ("data/processed/daily_features_v4.parquet", "data/processed/daily_features_v4.parquet"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default=os.getenv("HF_TOKEN"), help="HuggingFace write token")
    args = parser.parse_args()

    if not args.token:
        raise SystemExit("ERROR: pass --token hf_xxx or set HF_TOKEN env var")

    api = HfApi(token=args.token)
    root = Path(__file__).resolve().parent.parent

    for local_rel, space_path in FILES:
        local = root / local_rel
        if not local.exists():
            print(f"  SKIP  {local_rel!r}  (file not found locally)")
            continue

        size_mb = local.stat().st_size / 1_048_576
        print(f"  Uploading  {local_rel}  ({size_mb:.1f} MB)  →  {space_path} ...")
        api.upload_file(
            path_or_fileobj=str(local),
            path_in_repo=space_path,
            repo_id=SPACE_REPO,
            repo_type="space",
            commit_message=f"upload {Path(space_path).name}",
        )
        print(f"    done ✓")

    print("\nAll uploads finished. The Space will restart automatically.")


if __name__ == "__main__":
    main()
