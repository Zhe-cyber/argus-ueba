"""Package one completed W33 evaluation into report.md, metrics.csv, ROC/PR figures and a hashed manifest.

Read-only on the evaluation output. It never runs the evaluator, opens the archive or touches a release.
Before writing anything it recomputes the whole summary from the private scored rows with the evaluator's
own `summarise` and requires an exact match with `evaluation.json`; per-family generation counts must
also reconcile with the retained cases. Unavailable arms stay 'unavailable' (never 0 or blank), and
exclusions are reported as exclusions, never as negatives. Outputs are aggregates only: no account keys.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import evaluate_clue_v2 as ev, train_clue_v2 as trainer

NA = 'unavailable'
VIEWS = (('common', 'metrics_common'), ('all_supported', 'metrics_all_supported'))
COLUMNS = (['view', 'family', 'detector', 'normal_days', 'injected_cases', 'injected_prevalence', 'auroc',
            'average_precision', 'paired_cases', 'paired_median_change', 'paired_positive_fraction']
           + [f'{field}_{budget}' for budget in ev.BUDGETS
              for field in ('threshold', 'normal_alerts', 'normal_alert_fraction', 'case_alerts', 'case_recall')])


def load(evaluation_dir, release_sha):
    """(document, rows) after release binding and full reconciliation; raises on any mismatch."""
    evaluation_dir = Path(evaluation_dir)
    document = json.loads((evaluation_dir / 'evaluation.json').read_bytes())
    rows = json.loads((evaluation_dir / 'scored-rows-private.json').read_bytes())
    if (document.get('status') != 'reserved_evaluation_completed' or document.get('activated') is not False
            or document.get('release_sha256') != release_sha):
        raise ValueError('Not a completed, unactivated evaluation bound to this release')
    summary = document['summary']
    result = {'normal': rows['normal'], 'cases': rows['cases'], 'generation': summary['generation'],
              'unscored_normal': summary['unscored_normal'], 'exclusions': summary['exclusions'],
              'switch_design': summary['switch_design']}
    recomputed = json.loads(json.dumps(ev.summarise(result, document['thresholds'])))
    if recomputed != summary:
        raise ValueError('Summary does not reconcile with the scored rows')
    for family in ev.FAMILIES:
        if summary['generation'][family]['retained_scored_by_any'] != sum(c['family'] == family for c in rows['cases']):
            raise ValueError(f'Generation counts do not reconcile for {family}')
    return document, rows


def fmt(value):
    if value is None:
        return NA
    return f'{value:.4f}' if isinstance(value, float) else str(value)


def metric_rows(summary):
    for view, key in VIEWS:
        for family in ev.FAMILIES:
            for detector in ev.DETECTORS:
                entry = summary[key][family][detector]
                paired = entry['paired_change'] or {}
                line = {'view': view, 'family': family, 'detector': detector, 'normal_days': entry['normal_days'],
                        'injected_cases': entry['injected_cases'], 'injected_prevalence': entry['injected_prevalence'],
                        'auroc': entry['auroc'], 'average_precision': entry['average_precision'],
                        'paired_cases': paired.get('cases'), 'paired_median_change': paired.get('median'),
                        'paired_positive_fraction': paired.get('positive_fraction')}
                for budget in ev.BUDGETS:
                    cell = entry['budgets'][budget] or {}
                    for field in ('threshold', 'normal_alerts', 'normal_alert_fraction', 'case_alerts', 'case_recall'):
                        line[f'{field}_{budget}'] = cell.get(field)
                yield line


def metrics_csv(summary):
    out = io.StringIO()
    writer = csv.DictWriter(out, COLUMNS, lineterminator='\n')
    writer.writeheader()
    for line in metric_rows(summary):
        writer.writerow({k: NA if v is None else repr(v) if isinstance(v, float) else v for k, v in line.items()})
    return out.getvalue().encode()


def table(header, body):
    return '\n'.join(['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
                     + ['| ' + ' | '.join(fmt(v) for v in line) + ' |' for line in body])


def report(document, figures):
    s = document['summary']
    parts = [
        '# W33 reserved evaluation: CLUE v2 detectors',
        '',
        f"- Status: `{document['status']}`; activated: `{document['activated']}`; profile `{document['profile']}`",
        f"- Window: {document['window'][0]} to {document['window'][1]}; release SHA256 `{document['release_sha256']}`",
        f"- Evidence: {document['evidence']}",
        '- Metrics recomputed from the scored rows and reconciled exactly with `evaluation.json`.',
        '',
        '## Coverage of normal account-days',
        '',
        table(['Normal days observed', 'Common days (all detectors scored)'],
              [[s['normal_days_observed'], s['normal_common_days']]]),
        '',
        table(['Detector', 'Normal days scored'], [[d, s['normal_scored_by_detector'][d]] for d in ev.DETECTORS]),
        '',
        f"Unscored normal days: {json.dumps(s['unscored_normal'], sort_keys=True)}. "
        f"Account-switch design: {s['switch_design']['pairs']} pairs, "
        f"{s['switch_design']['unpaired_accounts']} unpaired accounts.",
        '',
        '## Injected cases: generation and exclusions',
        '',
        'Exclusions happen before generation and are not negatives.',
        '',
        table(['Family', 'Generated', 'Retained (scored by any)', 'Unscorable by all', 'Common cases', 'Exclusions'],
              [[f, s['generation'][f]['generated'], s['generation'][f]['retained_scored_by_any'],
                s['generation'][f]['unscorable_by_all'], s['cases_common'].get(f, 0),
                ', '.join(f'{k}={v}' for k, v in s['exclusions'][f].items()) or 'none'] for f in ev.FAMILIES]),
        '',
        table(['Family', 'v2 features unchanged / changed / unavailable', 'W23 features unchanged / changed / unavailable'],
              [[f] + ['{} / {} / {}'.format(*(s['feature_unchanged'][f][view].get(k, 0)
                                               for k in ('unchanged', 'changed', 'unavailable')))
                      for view in ('v2', 'w23')] for f in ev.FAMILIES]),
    ]
    for view, key in VIEWS:
        title = ('Common evaluation (primary: days and cases scored by every detector)' if view == 'common'
                 else 'All supported rows (each detector on the rows it can score; not directly comparable)')
        parts += ['', f'## {title}', '']
        for family in ev.FAMILIES:
            body = []
            for detector in ev.DETECTORS:
                e = s[key][family][detector]
                body.append([detector, e['normal_days'], e['injected_cases'], e['injected_prevalence'], e['auroc'],
                             e['average_precision']]
                            + [(e['budgets'][b] or {}).get(field) for b in ev.BUDGETS
                               for field in ('normal_alert_fraction', 'case_recall')])
            parts += [f'### {family}', '',
                      table(['Detector', 'Normal', 'Cases', 'Prevalence', 'AUROC', 'AP']
                            + [f'{name} @{b}' for b in ev.BUDGETS for name in ('normal alert frac.', 'recall')], body),
                      '']
            if view == 'common' and family in figures:
                parts += [f'![ROC and PR, {family}]({figures[family]})', '']
    parts += ['## Descriptive dominance (common evaluation; never a winner or activation rule)', '',
              table(['Comparison'] + [f'@{b}' for b in ev.BUDGETS],
                    [[pair] + [s['dominance_common'][pair][b] for b in ev.BUDGETS] for pair in s['dominance_common']]),
              '', '## Thresholds (strict >)', '',
              table(['Detector'] + [f'@{b}' for b in ev.BUDGETS],
                    [[d] + [(document['thresholds'][d] or {}).get(b) for b in ev.BUDGETS] for d in ev.DETECTORS]),
              '', 'AP depends on the reported injection prevalence; the prevalence column is its chance baseline.',
              '', '## Limitations', ''] + [f'- {item}' for item in document['limitations']]
    return ('\n'.join(parts) + '\n').encode()


def figure(rows, family, path):
    """ROC and PR curves on the common evaluation; returns detectors drawn. Detectors lacking both classes are skipped."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from sklearn.metrics import precision_recall_curve, roc_curve
    normal = [r for r in rows['normal'] if ev._common(r)]
    cases = [r for r in rows['cases'] if r['family'] == family and ev._common(r)]
    if not normal or not cases:
        return []
    fig, (roc, pr) = plt.subplots(1, 2, figsize=(10, 4.2))
    y = [0] * len(normal) + [1] * len(cases)
    for detector in ev.DETECTORS:
        values = [r['scores'][detector] for r in normal + cases]
        fpr, tpr, _ = roc_curve(y, values)
        precision, recall, _ = precision_recall_curve(y, values)
        roc.plot(fpr, tpr, label=detector)
        pr.step(recall, precision, where='post', label=detector)  # AP is the step-wise area
    roc.plot([0, 1], [0, 1], linestyle=':', color='grey')
    pr.axhline(len(cases) / len(y), linestyle=':', color='grey', label='prevalence')
    roc.set(title=f'ROC: {family}', xlabel='False positive rate', ylabel='True positive rate')
    pr.set(title=f'Precision-recall: {family}', xlabel='Recall', ylabel='Precision')
    roc.legend(loc='lower right')
    pr.legend(loc='upper right')
    fig.tight_layout()
    fig.savefig(path, dpi=120, metadata={'Software': None})
    plt.close(fig)
    return list(ev.DETECTORS)


def package(evaluation_dir, release_sha, output):
    output = trainer.private_new(output)
    document, rows = load(evaluation_dir, release_sha)
    output.mkdir(parents=True)
    figures = {f: f'roc-pr-{f}.png' for f in ev.FAMILIES if figure(rows, f, output / f'roc-pr-{f}.png')}
    for name, body in (('report.md', report(document, figures)), ('metrics.csv', metrics_csv(document['summary']))):
        with (output / name).open('xb') as handle:
            handle.write(body)
    sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    manifest = {'kind': 'w33_result_package_v1', 'release_sha256': release_sha, 'reconciled': True,
                'inputs': {name: sha(Path(evaluation_dir) / name) for name in ('evaluation.json', 'scored-rows-private.json')},
                'outputs': {p.name: sha(p) for p in sorted(output.iterdir())}, 'contains_account_keys': False}
    ev.canonical_write(output / 'manifest.json', manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation', required=True)
    parser.add_argument('--release-sha', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.evaluation, args.release_sha, args.out)['outputs']))


if __name__ == '__main__':
    main()
