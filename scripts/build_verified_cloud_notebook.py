"""Generate the Colab notebook with an explicit immutable reviewed Git revision."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def build(revision):
    if not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Pin a full reviewed Git commit')
    cells = []
    def add(kind, source):
        cell = {'cell_type': kind, 'metadata': {}, 'source': source.splitlines(keepends=True),
                'id': hashlib.sha256((kind + source).encode()).hexdigest()[:12]}
        if kind == 'code': cell.update(execution_count=None, outputs=[])
        cells.append(cell)
    add('markdown', '''# Argus: audited cloud AE training

This notebook trains the separate 12-feature cloud AE. Your 71-feature CERT
benchmark is unchanged. It accepts only the feature export from audited normal
AWS lab runs, not raw provider logs or the legacy flaws.cloud label heuristic.

**Current one-day baseline is insufficient.** Collect five closed UTC training
days (at least 30 identity-days), a later validation day and a later calibration
day (six identities each). These are operational minimums, not evidence of
enterprise accuracy. Reserve still later activity for independent evaluation.
Training is opt-in below and never deploys or activates the model.
''')
    add('code', f'''import pathlib, subprocess, sys, os
REVISION = "{revision}"
REPO = pathlib.Path('/content/argus-training-source')
if not REPO.exists():
    subprocess.run(['git', 'clone', 'https://github.com/Zhe-cyber/argus-ueba.git', str(REPO)], check=True)
subprocess.run(['git', '-C', str(REPO), 'fetch', 'origin', REVISION], check=True)
subprocess.run(['git', '-C', str(REPO), 'checkout', '--detach', REVISION], check=True)
os.chdir(REPO)
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == REVISION
subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'scripts/requirements-cloud-training.txt'], check=True)
subprocess.run([sys.executable, '-m', 'pip', 'install', '--index-url', 'https://download.pytorch.org/whl/cpu', 'torch==2.12.0'], check=True)
''')
    add('markdown', '''## Upload only the reviewed feature export

Run scripts/export_cloud_baseline.py locally first. Upload that JSON only, never
AWS credentials, .env, events.db, raw CloudTrail logs or experiment manifests.
Copy its reported SHA256 into EXPECTED_DATA_SHA256. Hashed identity values are
pseudonyms, not a guarantee of anonymisation; features can still be sensitive.
''')
    add('code', '''from google.colab import files
import hashlib, json
EXPECTED_DATA_SHA256 = "REPLACE_WITH_LOCAL_EXPORT_SHA256"
assert len(EXPECTED_DATA_SHA256) == 64, 'Set the reviewed local export hash first'
uploaded = files.upload()
assert len(uploaded) == 1, 'Upload exactly one feature JSON'
payload = next(iter(uploaded.values()))
assert hashlib.sha256(payload).hexdigest() == EXPECTED_DATA_SHA256, 'Export digest differs'
DATA = pathlib.Path('/content/argus-reviewed-features.json')
DATA.write_bytes(payload)
del uploaded, payload
''')
    add('markdown', '''## Validate data readiness before training

Set real UTC cutoffs; do not shift timestamps to create history. Calendar days
cannot overlap across fitting, model-selection validation and normal calibration.
The scaler is fitted on training only. Calibration sees no attack labels/data.
''')
    add('code', '''TRAIN_END = "YYYY-MM-DD"
VALIDATION_END = "YYYY-MM-DD"
CALIBRATION_END = "YYYY-MM-DD"
OUT = pathlib.Path('/content/argus-cloud-candidate')
command = [sys.executable, 'scripts/train_verified_cloud.py', '--data', str(DATA), '--out', str(OUT),
           '--train-end', TRAIN_END, '--validation-end', VALIDATION_END, '--calibration-end', CALIBRATION_END,
           '--epochs', '100', '--seed', '42']
subprocess.run(command + ['--check-only'], check=True)
''')
    add('code', '''RUN_TRAINING = False  # Set True only after the readiness check passes.
assert RUN_TRAINING, 'Training is disabled until you explicitly enable it'
subprocess.run(command, check=True)
manifest = json.loads((OUT / 'frozen_model_manifest.json').read_text())
print({k: manifest[k] for k in ('frozen', 'evaluation_status', 'provisional', 'partitions', 'environment')})
''')
    add('markdown', '''## Download a candidate bundle

This bundle is not activated. Review provenance, verify fixed-input CPU inference
locally and run later held-out evaluation before using accuracy claims. Scores
are anomalies, not compromise probabilities. Daily calibration does not validate
partial-day live scoring, and AWS-only training does not validate other sources.
Keep the model/scaler and manifest together. Do not overwrite the CERT artifacts.
''')
    add('code', '''import shutil
archive = shutil.make_archive('/content/argus-cloud-candidate', 'zip', OUT)
files.download(archive)
''')
    return {'cells': cells, 'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                                       'language_info': {'name': 'python'}}, 'nbformat': 4, 'nbformat_minor': 5}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    (ROOT / 'cloud_ae_verified_training.ipynb').write_text(json.dumps(build(args.revision), indent=1) + '\n', encoding='utf-8')
