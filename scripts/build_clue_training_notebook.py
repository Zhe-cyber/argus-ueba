"""Generate an opt-in CLUE Colab notebook pinned to an immutable implementation."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def build(revision):
    if not re.fullmatch('[a-f0-9]{40}', revision): raise ValueError('Use a full implementation commit')
    cells = []
    def add(kind, text):
        cell = {'cell_type':kind,'id':hashlib.sha256((kind+text).encode()).hexdigest()[:12],
                'metadata':{},'source':text.splitlines(keepends=True)}
        if kind == 'code': cell.update(execution_count=None,outputs=[])
        cells.append(cell)
    add('markdown', '''# Argus: separate CLUE behavioural benchmark

This notebook trains clue_behavior_v1 (10 features), not the 71-feature CERT or
12-feature AWS model. It does not deploy anything. Dataset: Landauer, Skopik,
Hoeld and Wurzenberger (AIT), CLUE-LDS (2022), DOI 10.5281/zenodo.7119953,
CC BY 4.0. Only locally exported feature JSON is needed; never upload credentials,
.env, raw logs or archive prefixes. Partial-prefix coverage/integrity limitations
remain. The population AE is not an individually conditioned user model.
''')
    add('code', f'''import pathlib,subprocess,sys,os,json,hashlib
REVISION = '{revision}'
REPO = pathlib.Path('/content/argus-clue-training')
if not REPO.exists():
    subprocess.run(['git','clone','https://github.com/Zhe-cyber/argus-ueba.git',str(REPO)],check=True)
subprocess.run(['git','-C',str(REPO),'fetch','origin',REVISION],check=True)
subprocess.run(['git','-C',str(REPO),'checkout','--detach',REVISION],check=True)
os.chdir(REPO)
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==REVISION
subprocess.run([sys.executable,'-m','pip','install','-r','scripts/requirements-clue-training.txt'],check=True)
subprocess.run([sys.executable,'-m','pip','install','--index-url','https://download.pytorch.org/whl/cpu','torch==2.12.0'],check=True)
''')
    add('markdown', '''## Upload the private feature export

Use data/processed/clue-v1/colab-features.json from the original local checkout.
The default hash below identifies the prepared artifact; change it only when
you have deliberately produced/reviewed a new export and its readiness report.
The notebook checks the feature-code digest and fitting-only population.
''')
    add('code', '''from google.colab import files
EXPECTED_DATA_SHA256 = 'c151ccd687f09175ee06f827168525c31a28cd000df0a67a8cda9a1ed187c4f3'
upload=files.upload()
assert len(upload)==1,'Upload exactly one feature JSON'
payload=next(iter(upload.values()))
assert hashlib.sha256(payload).hexdigest()==EXPECTED_DATA_SHA256,'Unexpected export hash'
DATA=pathlib.Path('/content/clue-features.json')
DATA.write_bytes(payload)
del upload,payload
CUTOFFS=['2017-07-12','2017-07-26','2017-07-31','2017-08-04','2017-08-09']
from scripts.train_clue_ae import load_dataset,select
document,digest=load_dataset(DATA)
population,parts=select(document,CUTOFFS)
print({'profile':document['profile'],'fitting_population':len(population),
       'fit':len(parts[1]),'validation':len(parts[2]),'normal_calibration':len(parts[3])})
del document,population,parts
''')
    add('markdown', '''## Train and freeze the candidate

Counts receive log1p followed by a scaler fitted on training only. Validation
chooses weights. A predeclared 99th-percentile normal-calibration MSE sets the
alert threshold; no held-out feature values select weights or thresholds.
100 seeded CPU epochs are the default. Re-running requires a new output folder.
''')
    add('code', '''RUN_TRAINING=False
assert RUN_TRAINING,'Enable only after checking the dataset and cutoffs'
BUNDLE=pathlib.Path('/content/clue-candidate')
subprocess.run([sys.executable,'scripts/train_clue_ae.py','train','--data',str(DATA),
                '--out',str(BUNDLE),'--cutoffs',*CUTOFFS,'--epochs','100','--seed','42'],check=True)
manifest=json.loads((BUNDLE/'clue_model_manifest.json').read_text())
print({k:manifest[k] for k in ('profile','partition_rows','evaluation_status','activated','environment')})
''')
    add('markdown', '''## Evaluate the frozen model once on later normal activity

This measures alerts on publisher-declared normal active user-days. It does not
measure attack recall. Missing user activity is not a true negative. Do not tune
the threshold after viewing this report and still describe the same split as
untouched. The descriptive binomial interval does not account for dependence
between days/users. Scores are not compromise probabilities or AWS validation.
''')
    add('code', '''RUN_NORMAL_EVALUATION=False
assert RUN_NORMAL_EVALUATION,'Evaluation is a separate explicit action after freezing'
REPORT=BUNDLE/'normal_holdout_report.json'
subprocess.run([sys.executable,'scripts/train_clue_ae.py','evaluate','--data',str(DATA),
                '--bundle',str(BUNDLE),'--out',str(REPORT)],check=True)
print(json.loads(REPORT.read_text()))
''')
    add('markdown', '''## Download the candidate bundle

Keep weights, scaler, manifest and any evaluation report together. Preserve the
exact software versions recorded in the manifest. Only load model/scaler bundles
you trust: file hashes are provenance checks, not a signature from an authority.
These artifacts must never replace cloud_ae_v1.pt or the CERT model. A later
offline account-switch experiment is needed before attack-detection claims.
''')
    add('code', '''import shutil
archive=shutil.make_archive('/content/argus-clue-candidate','zip',BUNDLE)
files.download(archive)
''')
    return {'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
                                     'language_info':{'name':'python'}},'nbformat':4,'nbformat_minor':5}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision',required=True)
    args=parser.parse_args()
    (Path(__file__).resolve().parents[1]/'clue_ae_training.ipynb').write_text(json.dumps(build(args.revision),indent=1)+'\n',encoding='utf8')
