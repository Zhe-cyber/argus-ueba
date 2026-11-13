"""install_ops_tasks.ps1 cutover drain decision (mocked task and process lists)."""
import codecs
import json
from pathlib import Path
import subprocess
import sys

from scripts.ops_cutover_check import blockers

DISABLED = {'state': 'Disabled', 'enabled': False}
PILOT_TICK = {'pid': 41, 'command_line': r'"C:\py\pythonw.exe" "C:\pilot\scripts\local_pilot.py" tick --config x.json'}
COLLECT = {'pid': 42, 'command_line': r'python.exe C:\pilot\scripts\collect_live.py --once'}
UNRELATED = [{'pid': 7, 'command_line': r'pythonw.exe C:\ops\scripts\ops_collect.py tick --config ops.json'},
             {'pid': 8, 'command_line': r'pythonw.exe C:\pilot\scripts\local_pilot.py serve'},
             {'pid': 9, 'command_line': 'powershell -File scripts\\install_ops_tasks.ps1 -Apply'}]


def test_drained_when_task_disabled_or_absent_and_no_pilot_process():
    assert blockers(DISABLED, UNRELATED) == []
    assert blockers(None, UNRELATED) == []


def test_enabled_or_running_task_blocks():
    for task in ({'state': 'Ready', 'enabled': True}, {'state': 'Running', 'enabled': True},
                 {'state': 'Running', 'enabled': False}, {'state': 'Queued', 'enabled': True}):
        assert len(blockers(task, [])) == 1, task


def test_live_pilot_processes_block_even_when_task_disabled():
    found = blockers(DISABLED, UNRELATED + [PILOT_TICK, COLLECT])
    assert found == ['pilot process still alive (pid 41)', 'pilot process still alive (pid 42)']


def test_cli_exit_code_as_called_by_powershell():
    script = Path(__file__).resolve().parents[1] / 'ops_cutover_check.py'
    def run(payload):  # PowerShell pipes UTF-8 with a BOM
        done = subprocess.run([sys.executable, str(script)], input=codecs.BOM_UTF8 + json.dumps(payload).encode(),
                              capture_output=True)
        done.stdout = done.stdout.decode()
        return done
    ok = run({'task': DISABLED, 'processes': UNRELATED})
    assert ok.returncode == 0 and ok.stdout.startswith('drained')
    busy = run({'task': {'state': 'Running', 'enabled': True}, 'processes': [PILOT_TICK]})
    assert busy.returncode == 1 and 'pid 41' in busy.stdout
