"""Reserved-day wrapper reusing the bounded history execution/ledger engine."""
from datetime import timezone
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import reserved_study as study, run_persona_history as history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-id', required=True)
    parser.add_argument('--stack', default='argus-ueba-actors')
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--profile', default='argus-simulator')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    try:
        now = history.utc_now()
        plan = study.plan_for_date(args.account_id, args.stack, now.astimezone(study.MALAYSIA).date().isoformat(), now)
        if args.execute:
            result = history.execute(plan, args.state_dir, args.profile, reserved=True)
        else:
            result = {'executed': False, 'purpose': plan['purpose'], 'planned_actions': len(plan['actions']),
                      'case_slots': [r['case_slot'] for r in plan['actions'] if 'case_slot' in r]}
        print(json.dumps(result))
        return 0
    except Exception:
        print('Reserved runner refused; check frozen release, current date, ledger and collection health.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
