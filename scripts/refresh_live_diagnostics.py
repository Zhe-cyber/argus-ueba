"""Finite, local, read-only diagnostic generation; no provider calls or activation."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from workspace_next import diagnostic_receipts as consumer

END = datetime.fromisoformat('2026-11-17T00:00:00+08:00')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temporary.write_bytes(consumer.canonical(value) + b'\n')
    os.replace(temporary, path)


def validate(config):
    consumer.require(config.get('schema') == 'argus_diagnostic_refresh_job_v1'
                     and config.get('end_my') == END.isoformat(), 'invalid_refresh_config')
    consumer.validate_provenance(config['expected_provenance'])
    expected = config['source_sha256']
    consumer.require(isinstance(expected, dict)
                     and {'scripts/refresh_live_diagnostics.py', 'workspace_next/diagnostic_receipts.py'} <= set(expected)
                     and all(expected.get(n) == h for n, h in config['expected_provenance']['source_sha256'].items()),
                     'invalid_refresh_config')
    consumer.verify_current_sources({'source_sha256': expected})
    output = Path(config['output_root']).resolve()
    state = Path(config['state_dir']).resolve()
    pointer = Path(config['pointer']).resolve()
    consumer.require(output == ROOT / 'data/processed/clue-ae-v2/daily-live-receipts'
                     and state == ROOT / 'data/live/diagnostic-refresh-v1'
                     and pointer == ROOT / 'data/live/workspace-case-preview-20261030-v1/diagnostic-receipts-config.json',
                     'invalid_refresh_config')
    consumer.require(state.is_dir() and output.is_dir() and pointer.parent.is_dir(), 'invalid_refresh_config')
    for key in ('pilot_config', 'prereg', 'training', 'database'):
        consumer.require(Path(config[key]).exists(), 'invalid_refresh_config')
    return config


def generate(config, output, now):
    # Existing Claude-owned generator. Never edits its code or a single-use experiment.
    from scripts import live_receipts_clue_v2 as producer
    return producer.run(config['database'], config['pilot_config'], config['prereg'], config['training'], output, now)


def refresh(config_path, *, check=False, now=None):
    config = validate(consumer.strict_json(Path(config_path).read_bytes()))
    now = now or datetime.now(timezone.utc)
    consumer.require(now.tzinfo is not None and now.utcoffset() is not None, 'invalid_cutoff')
    if now >= END:
        return {'status': 'refresh_period_expired', 'model_activated': False}
    if check:
        return {'status': 'configuration_verified', 'model_activated': False, 'provider_calls': 0}
    state = Path(config['state_dir'])
    lock = state / 'refresh.lock'
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return {'status': 'refresh_locked_requires_review', 'model_activated': False}
    published = False
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump({'pid': os.getpid(), 'started_utc': now.isoformat()}, handle)
        previous = state / 'last_success.json'
        if previous.is_file():
            record = consumer.strict_json(previous.read_bytes())
            if (consumer.stamp(record['cutoff_utc']).astimezone(consumer.MYT).date()
                    == now.astimezone(consumer.MYT).date()):
                return {'status': 'already_refreshed_today', 'model_activated': False}
        output = Path(config['output_root']) / ('run-' + now.strftime('%Y%m%dT%H%M%S') + '-' + uuid4().hex[:8])
        generate(config, output, now)
        validate(config)  # Refuse a concurrent source edit before publishing its output.
        pin = sha(output / 'manifest.json')
        index = consumer.load_bundle(output, manifest_sha256=pin,
                                     expected_provenance=config['expected_provenance'], now=now)
        manifest = consumer.strict_json((output / 'manifest.json').read_bytes())
        pointer = {'directory': str(output), 'manifest_sha256': pin,
                   'expected_provenance': config['expected_provenance']}
        atomic_json(Path(config['pointer']), pointer)
        published = True
        receipt = {'status': 'refreshed', 'cutoff_utc': index.cutoff_utc, 'manifest_sha256': pin,
                   'receipts': len(index.rows), 'scored_receipts': manifest['scored_receipts'],
                   'model_activated': False, 'score_display_changed': False, 'provider_calls': 0}
        atomic_json(previous, receipt)
        atomic_json(state / 'last_attempt.json', receipt)
        return receipt
    except Exception as error:
        atomic_json(state / 'last_attempt.json', {'status': 'refresh_failed', 'at_utc': now.isoformat(),
                    'reason_code': error.code if isinstance(error, consumer.ReceiptError) else type(error).__name__,
                    'pointer_changed': published, 'model_activated': False})
        raise
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(refresh(args.config, check=args.check)))
        return 0
    except Exception:
        print('Diagnostic refresh refused; inspect its local attempt report. Previous artifact is retained.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
