"""Verify a trusted Colab bundle, inspect normal alerts, and freeze an offline experiment plan."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.train_clue_ae import FEATURES,PROFILE,build_model,load_dataset,matrix,select,sha


def prepare(dataset,bundle,output):
    import joblib
    import numpy as np
    import torch
    bundle,output=Path(bundle).resolve(),Path(output)
    if output.exists(): raise ValueError('Use a new private review directory')
    manifest=json.loads((bundle/'clue_model_manifest.json').read_text())
    published=json.loads((bundle/'normal_holdout_report.json').read_text())
    if (manifest.get('frozen') is not True or manifest.get('profile')!=PROFILE or manifest.get('features')!=FEATURES
            or manifest.get('input_dim')!=len(FEATURES) or manifest.get('transform')!='log1p_then_standard_scaler_v1'):
        raise ValueError('Incompatible frozen profile')
    if published['manifest_sha256']!=sha(bundle/'clue_model_manifest.json'):
        raise ValueError('Report/manifest binding differs')
    for kind in ('model','scaler'):
        artifact=(bundle/manifest[kind+'_path']).resolve()
        if artifact.parent!=bundle or sha(artifact)!=manifest[kind+'_sha256']:
            raise ValueError('Artifact path/digest differs')
    data,digest=load_dataset(dataset)
    if digest!=manifest['dataset_sha256'] or digest!=published['dataset_sha256']:
        raise ValueError('Dataset digest differs')
    if manifest['feature_code_sha256']!=data['provenance']['feature_code_sha256']:
        raise ValueError('Frozen feature code differs')
    code=(ROOT/'scripts/train_clue_ae.py').read_bytes()
    if manifest['training_code_sha256'] not in {hashlib.sha256(code).hexdigest(),hashlib.sha256(code.replace(b'\r\n',b'\n')).hexdigest()}:
        raise ValueError('Use the pinned training implementation')
    if manifest['model_sha256']!=published['model_sha256']:
        raise ValueError('Report model differs')
    population,parts=select(data,manifest['cutoffs_utc'])
    if population!=manifest['fitting_population']:
        raise ValueError('Frozen population differs')
    threshold=manifest['threshold_raw_mse']
    if threshold!=published['threshold_raw_mse']:
        raise ValueError('Frozen threshold differs')
    model=build_model().cpu()
    model.load_state_dict(torch.load(bundle/manifest['model_path'],map_location='cpu',weights_only=True)['state_dict'])
    model.eval()
    scaler=joblib.load(bundle/manifest['scaler_path'])
    x=torch.tensor(scaler.transform(matrix(parts[4])).astype(np.float32))
    with torch.no_grad(): residual=((model(x)-x)**2).numpy()
    scores=residual.mean(axis=1)
    indices=np.flatnonzero(scores>threshold)
    if len(indices)!=published['normal_alerts'] or len(scores)!=published['heldout_active_identity_days']:
        raise ValueError('Local normal classification differs from Colab')
    alerts=[]
    for index in indices:
        row=parts[4][int(index)]
        fitting=[r for r in parts[1] if r['user']==row['user']]
        top=np.argsort(residual[index])[::-1][:3]
        alerts.append({'identity_alias':'cohort-'+str(population.index(row['user'])+1),'date':row['date'],
                       'raw_mse':float(scores[index]),'threshold_multiple':float(scores[index]/threshold),
                       'history_days':row.get('history_days'),
                       'reconstruction_residuals':[{'feature':FEATURES[j],
                           'raw_count':row['features'][FEATURES[j]],
                           'fitting_identity_median':float(np.median([r['features'][FEATURES[j]] for r in fitting])),
                           'mse_contribution':float(residual[index,j]/len(FEATURES))} for j in top]})
    diagnostics={'profile':PROFILE,'model_sha256':manifest['model_sha256'],'dataset_sha256':digest,
                 'manifest_sha256':sha(bundle/'clue_model_manifest.json'),'threshold_raw_mse':threshold,
                 'normal_alerts':len(indices),'normal_rows':len(scores),'alerts':alerts,
                 'minimum_threshold_distance':float(np.min(np.abs(scores-threshold))),
                 'limitations':'Residual components are numerical reconstruction diagnostics, not SHAP or proven causes. '
                 'Publisher-declared normal labels are retained. No model/threshold change or attack execution.'}
    # All scenario selection below uses only fitting rows and the train-fitted scaler.
    fit=parts[1]
    transformed=scaler.transform(matrix(fit))
    centres={u:np.median(transformed[[i for i,r in enumerate(fit) if r['user']==u]],axis=0) for u in population}
    pairs=[]
    for i,left in enumerate(population):
        for right in population[i+1:]: pairs.append((float(np.linalg.norm(centres[left]-centres[right])),left,right))
    pairs.sort()
    middle=pairs[int(len(pairs)*0.2):int(len(pairs)*0.8)]
    rng=random.Random(42); rng.shuffle(middle)
    selected,used=[],set()
    for distance,left,right in middle:
        if left not in used and right not in used:
            selected.append({'case_id':f'switch-{len(selected)+1:02d}', 'left':left,'right':right,
                             'fitting_profile_distance':distance})
            used.update((left,right))
            if len(selected)==3: break
    if len(selected)!=3: raise ValueError('Insufficient disjoint fitting-only pairs')
    from datetime import date,timedelta
    switch_day=(date.fromisoformat(manifest['cutoffs_utc'][3])+timedelta(days=1)).isoformat()
    plan={'schema_version':1,'profile':PROFILE,'seed':42,'model_sha256':manifest['model_sha256'],
          'manifest_sha256':sha(bundle/'clue_model_manifest.json'),'dataset_sha256':digest,
          'threshold_raw_mse':threshold,'switch_day_utc':switch_day,
          'end_day_utc':manifest['cutoffs_utc'][4],'cases':selected,
          'selection':'Three disjoint pairs from middle 20-80% fitting-profile distances; seeded shuffle. '
          'Median log1p/train-standardised fitting vectors only. No evaluation rows/residuals select pairs.',
          'execution':'Not executed. Separate scenarios, one reciprocal pair per run. Reassign analytical uid '
          'only after switch_day, then recompute day features and prior-action history from native prefix events. '
          'Preserve original IDs/timestamps; do not forward simulated records into live ingestion.',
          'ground_truth':'Offline simulated account-switch labels stay outside model features. '
          'Do not call them real intruders, native credential compromise or enterprise attack recall.',
          'reporting':'Report each case/account/active-day result and normal controls. The same normal control '
          'days recur across cases and must not be counted as independent evidence.',
          'expected_limitation':'Population AE has no identity-conditioned volume baseline. Most swapped '
          'features may remain identical; only history-dependent novelty can change. Zero detections '
          'must be reported, without tuning the frozen holdout.', 'executed':False}
    output.mkdir(parents=True,exist_ok=False)
    for filename,value in [('normal_alert_diagnostics.json',diagnostics),('account_switch_plan.json',plan)]:
        (output/filename).write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf8')
    return diagnostics,plan


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',required=True); parser.add_argument('--bundle',required=True); parser.add_argument('--out',required=True)
    args=parser.parse_args()
    try:
        diagnostics,plan=prepare(args.data,args.bundle,args.out)
        print(json.dumps({'normal_alerts_reproduced':diagnostics['normal_alerts'],'normal_rows':diagnostics['normal_rows'],
                          'planned_switch_cases':len(plan['cases']),'attacks_executed':False,'activated':False}))
    except Exception:
        parser.exit(1,'Candidate review stopped. Check trusted hashes, frozen population, dataset and a new output directory. No raw events displayed.\n')
