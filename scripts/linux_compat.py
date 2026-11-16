"""Non-Windows replacements for the two Windows-only pieces the operational path needs.

lock(path)        local_pilot.lock uses msvcrt; on Linux the same fail-fast semantics via fcntl.flock.
read_secret(name) plain secret files in /etc/argus/secrets/<name> instead of Windows DPAPI. The file must be owned
                  by the service user and have mode 0600 exactly, or it is refused (the value is never logged).
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import stat

SECRET_DIR = Path('/etc/argus/secrets')


@contextmanager
def lock(path):
    if os.name == 'nt':
        from scripts.local_pilot import lock as windows_lock
        with windows_lock(path):
            yield
        return
    import fcntl
    with Path(path).open('a+b') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # raises BlockingIOError when held
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def check_secret_file(info, uid):
    """Raise unless the stat result is a regular file owned by `uid` with mode 0600."""
    if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o600:
        raise PermissionError('Secret file must be a regular file owned by the service user with mode 0600')


def read_secret(name, base=None):
    if not name or name.startswith('.') or any(c in name for c in '/\\'):
        raise ValueError('Invalid secret name')
    path = Path(base or SECRET_DIR) / name
    with path.open('rb') as handle:  # check the opened file, not the path: no swap between check and read
        check_secret_file(os.fstat(handle.fileno()), os.geteuid())
        return handle.read().decode('utf-8').strip()
