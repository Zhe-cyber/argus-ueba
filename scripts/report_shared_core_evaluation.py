"""Render frozen reduced-score artifacts; never reopens native data or changes a detector."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

FAMILIES = [('mass_access','5× file-read injection'),('off_hours','Night-time shift'),
            ('new_action','Unfamiliar-action injection'),('account_switch','Account-switch injection')]


def render(source, output):
    source, output = Path(source), Path(output)
    data = json.loads(source.read_bytes())
    if data.get('status') != 'reserved_normal_and_injected_scenarios' or data.get('activated') is not False:
        raise ValueError('Completed dormant reserved evaluation required')
    if output.exists():
        raise ValueError('New report directory required')
    output.mkdir(parents=True)
    rows=[]
    for family,label in FAMILIES:
        for detector,title in [('ae','AE'),('max_deviation','Max-deviation baseline')]:
            metric=data['metrics'][family][detector]
            row={'scenario':label,'detector':title,'normal_days':metric['normal_days'],
                 'injected_cases':metric['injected_cases'],'injected_prevalence':metric['injected_prevalence'],
                 'auroc':metric['auroc'],'average_precision':metric['average_precision']}
            for budget in ['0.01','0.05']:
                point=metric['budgets'][budget]
                for key in ['threshold','normal_alerts','normal_alert_fraction','case_alerts','case_recall']:
                    row[key+'_'+budget]=point[key]
                row['case_threshold_ties_'+budget]=sum(case['scores'][detector]==point['threshold'] for case in data['case_rows'] if case['family']==family)
            rows.append(row)
    with (output/'metrics.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    lines=['# Shared-core reserved evaluation — 30 October 2026','',
           '**Decision: do not promote this candidate to general live compromise alerting.**',
           'The five-feature population AE has weak ranking on account switches and mass access, and low recall at the frozen thresholds. The simple baseline ranks three scenario families better. No retraining or threshold/injection tuning was performed after the reserved results.','',
           'Window: 11–24 August 2017 UTC. One fixed candidate, 55 fitting-selected pseudonymous accounts; 472 eligible normal account-days and 12 input-quality exclusions. All 55 have some test activity; unobserved idle days are not negatives.','',
           'Semi-synthetic evidence: publisher-described normal storage activity plus preregistered one-day native-event injections. Not real attack accuracy or live multi-cloud performance.','',
           '## Ranking metrics','',
           '| Scenario | Cases | AE AUROC | Baseline AUROC | AE AP | Baseline AP | Positive prevalence |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for family,label in FAMILIES:
        a,b=data['metrics'][family]['ae'],data['metrics'][family]['max_deviation']
        lines.append(f"| {label} | {a['injected_cases']} | {a['auroc']:.3f} | {b['auroc']:.3f} | {a['average_precision']:.3f} | {b['average_precision']:.3f} | {a['injected_prevalence']:.1%} |")
    lines += ['', 'AP is average precision, not trapezoidal PR-AUC; it depends on the displayed class prevalence. Per-scenario figures use the same 472 normal days. No pooled accuracy headline is used.','',
              '## Frozen operating points','',
              '| Scenario | AE recall: 1% budget | Baseline: 1% | AE recall: 5% budget | Baseline: 5% |',
              '|---|---:|---:|---:|---:|']
    for family,label in FAMILIES:
        a,b=data['metrics'][family]['ae'],data['metrics'][family]['max_deviation']
        count=a['injected_cases']
        def point(metric,budget):
            p=metric['budgets'][budget]
            return f"{p['case_alerts']}/{count} ({p['case_recall']:.1%})"
        lines.append(f"| {label} | {point(a,'0.01')} | {point(b,'0.01')} | {point(a,'0.05')} | {point(b,'0.05')} |")
    lines += ['',
              'At the nominal 1% normal-calibration budget both methods alert on **0/472 normal test days**. That is an observed count, not proof of zero future false alarms; it accompanies very low case recall.',
              'At the nominal 5% calibration budget the AE alerts on **16/472 normal days (3.39%)**, baseline **13/472 (2.75%)**. These are achieved test rates, not thresholds chosen from the mixed test set.',
              'Higher AUROC/AP need not imply higher recall at a particular fixed cutoff. Report both ranking and operating-point results. CSV includes exact thresholds and case tie counts.','',
              '## Coverage and controls','',
              '- Twelve observed normal account-days are unscorable due to required input quality; excluded cases are not true negatives.',
              '- Switch design: 27 disjoint directed pairs, 27 targets, 27 donor-only accounts and one unpaired account. There are 144 scorable switches; 81 target-days lack an active/scorable donor and nine target-days have an unscorable original. Donor-only days and the unpaired account remain in normal-day accounting.',
              '- One switch has identical five-feature values and is retained as a positive case. Normal originals alone update later-day history.',
              '- Other exclusions: mass access 99 days without reads plus 12 unscorable originals; off-hours 62 already-night days plus 12 unscorable; unfamiliar action 122 already-known permission-kind days, 49 without a resource template and 12 unscorable.',
              '- Account-days and paired counterfactuals are dependent. No independent-binomial confidence claim or broad deployment generalisation is made.','',
              '## Validation and provenance','',
              '37 pre-release tests passed; the full reader/history/generator/scoring/metrics rehearsal on inspected 5–9 August passed with exact prefix/full-ZIP feature parity. Source-only Claude Code reviews were completed; code binding concerns were checked against actual guards and tamper tests.',
              'A pre-test numerical supplement aligned calibration with canonical CPU float32 single-row inference: same 167 normal rows, same higher quantiles and strict-greater rule. AE 1% cutoff changed by one float32 step (1.1920928955078125e-07); original weights, scaler, manifest and thresholds remain preserved. This was completed before test access, not fitted to attacks.','',
              'Frozen evaluator release SHA256: '+data['release_sha256']+'.',
              'Reduced evaluation artifact SHA256: '+hashlib.sha256(source.read_bytes()).hexdigest()+'.',
              'Completed native-access receipt is stored privately beside evaluation.json. The test window is now consumed and cannot be reused as an untouched test for later model tuning. A first 25-August boundary row was decoded for closure; do not call that date wholly uninspected.','',
              'Candidate: shared_behavior_core_v1, AE 5-16-8-3-8-16-5, 532 fitting / 183 validation / 167 normal-calibration days. Exact source/data/model bindings remain in the private training preregistration and evaluator release. No live activation or cloud-resource change.','',
              '## Next planned step','',
              'Complete provider-level applicability/sign-off with this negative benchmark finding retained. Current live inputs remain cold-start and broad AWS resource semantics are incomplete; this experiment does not justify enabling live High/Medium/Low from this candidate. Keep the working collection, source-scoped identities, approved cross-provider timeline and existing AWS study intact. Any changed detector needs an explicit new protocol and a genuinely fresh test, not retuning on these outcomes.','',
              'Source: [CLUE-LDS, Landauer et al.](https://zenodo.org/records/7119953), CC BY 4.0. This is cloud-storage activity, not a real linked AWS/GitHub/Cloudflare attack dataset.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from sklearn.metrics import roc_curve
    fig,axes=plt.subplots(2,2,figsize=(11,9),layout='constrained')
    for ax,(family,label) in zip(axes.flat,FAMILIES):
        positives=[row for row in data['case_rows'] if row['family']==family]
        for detector,title,color in [('ae','AE','#315cc4'),('max_deviation','Max-deviation baseline','#bf7915')]:
            scores=[row['scores'][detector] for row in data['normal_rows']]+[row['scores'][detector] for row in positives]
            y=[0]*len(data['normal_rows'])+[1]*len(positives)
            fpr,tpr,_=roc_curve(y,scores)
            auc=data['metrics'][family][detector]['auroc']
            ax.plot(fpr,tpr,color=color,lw=2,label=f'{title}: AUROC {auc:.3f}')
        ax.plot([0,1],[0,1],color='#94a3b8',ls='--',lw=1)
        ax.set(title=f'{label} (n={len(positives)})',xlabel='Normal-day alert fraction',ylabel='Injected-case recall',xlim=(0,1),ylim=(0,1))
        ax.grid(alpha=.15);ax.legend(loc='lower right',fontsize=8)
    fig.suptitle('Reserved CLUE evaluation · 11–24 August 2017\n472 eligible normal account-days · fixed semi-synthetic scenarios',fontsize=13)
    fig.savefig(output/'roc-comparison.png',dpi=180)
    plt.close(fig)
    (output/'provenance.json').write_text(json.dumps({'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'release_sha256':data['release_sha256'],'report_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'read_only_reduced_scores':True,'native_archive_reopened':False},indent=2))
    print('Frozen evaluation report, CSV and ROC figure saved to '+str(output))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evaluation',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args();render(args.evaluation,args.out)
