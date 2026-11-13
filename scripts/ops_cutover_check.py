"""Cutover drain check for install_ops_tasks.ps1 (one SQS consumer only).

Reads JSON on stdin: {"task": null | {"state": "Ready|Running|Disabled|...", "enabled": true|false},
                      "processes": [{"pid": 1, "command_line": "..."}]}
(the PowerShell script fills it from Get-ScheduledTask Argus-Pilot-Collect and Win32_Process). Prints one line per
blocker and exits 0 only when drained: the old task is absent or disabled (so not Running), and no process
runs the pilot's `local_pilot.py ... tick` or `collect_live`.
"""
import json
import re
import sys

PILOT_PROCESS = re.compile(r'local_pilot\.py\b.*\btick\b|collect_live', re.IGNORECASE)


def blockers(task, processes):
    """Reasons the cutover must wait; [] when drained."""
    out = []
    # State is one value, so 'Disabled' also excludes Running/Queued; a run that started before the task was disabled
    # keeps going under state Disabled, which the process check below catches.
    if task is not None and (task.get('enabled') is not False or task.get('state') != 'Disabled'):
        out.append(f"Argus-Pilot-Collect is not disabled and idle (state {task.get('state')})")
    out += [f"pilot process still alive (pid {p.get('pid')})" for p in processes
            if PILOT_PROCESS.search(p.get('command_line') or '')]
    return out


def main():
    data = json.loads(sys.stdin.buffer.read().decode('utf-8-sig', errors='replace'))  # PowerShell pipes add a BOM
    processes = data.get('processes') or []
    if isinstance(processes, dict):  # PowerShell 5.1 can unwrap a one-element array
        processes = [processes]
    found = blockers(data.get('task'), processes)
    print('\n'.join(found) if found else 'drained: old collector disabled and no pilot collection process alive')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
