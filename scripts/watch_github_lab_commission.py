"""Bounded native-event reconciliation only; never generates workload actions."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import github_lab_app as app
from scripts import github_lab_workload as lab


def main():
    cfg = json.loads((app.STATE_DIR/'watch-config.json').read_bytes())
    if datetime.now(timezone.utc).timestamp() >= cfg['expires_at_unix']:
        result = {'status': 'watch_expired', 'scheduled_workload': False}
    elif any(hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest for name,digest in cfg['source_sha256'].items()):
        result = {'status': 'source_changed_stopped', 'scheduled_workload': False}
    else:
        try:
            result = lab.reconcile()
        except Exception as error:
            result = {'status': 'reconciliation_failed', 'error_type': type(error).__name__, 'scheduled_workload': False}
    result['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
    app.atomic(app.STATE_DIR/'last-reconciliation.json', result)
    return 1 if result['status'] in ('source_changed_stopped','reconciliation_failed') else 0


if __name__ == '__main__':
    raise SystemExit(main())
