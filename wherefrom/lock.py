"""A lock that only one process can hold at a time, so starting the watcher
again (setup run twice, sign-in plus a manual start) doesn't run two of them.

The operating system drops the lock when the process ends, however it ends,
so a crash never leaves it stuck.
"""

import os
import sys


def hold(path):
    """Take the lock in `path`. Returns an open file to keep (the lock lasts as
    long as it stays open), or None if another process holds it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")      # noqa: SIM115 - must stay open while held
    try:
        if sys.platform == "win32":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()).encode())     # for people looking; nothing reads it
    handle.flush()
    return handle
