"""Finite log-read watcher only. Never sends machine-workload requests."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import cloudflare_lab_setup as setup
from scripts import provision_cloudflare_machine as lab
from scripts.github_lab_app import atomic


def main():
    cfg=json.loads((setup.STATE/'watch-config.json').read_bytes())
    if datetime.now(timezone.utc).timestamp()>=cfg['expires_at_unix']:
        result={'status':'watch_expired','scheduled_workload':False}
    elif any(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest for name,digest in cfg['source_sha256'].items()):
        result={'status':'source_changed_stopped','scheduled_workload':False}
    elif (setup.STATE/'commissioning-native-log.json').exists():
        result={'status':'native_log_captured','scheduled_workload':False,'ingested':False}
    else:
        try:result=lab.inspect_log(setup.api())
        except Exception as error:result={'status':'log_check_failed','error_type':type(error).__name__,'scheduled_workload':False}
    result['checked_at_utc']=datetime.now(timezone.utc).isoformat()
    atomic(setup.STATE/'last-log-check.json',result)
    return 1 if result['status'] in ('source_changed_stopped','log_check_failed') else 0


if __name__=='__main__':raise SystemExit(main())
