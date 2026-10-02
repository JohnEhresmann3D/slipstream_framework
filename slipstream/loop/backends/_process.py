from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def resolve_command(executable: str) -> list[str]:
    """Turn a configured executable into an argv prefix that Popen can launch.

    On Windows, CreateProcess does not apply PATHEXT, so a bare ``pi`` or
    ``claude`` fails when the installed entry point is ``pi.cmd``. Python
    scripts are run through the current interpreter so they work without a
    shebang-aware shell.
    """
    resolved = shutil.which(executable) or executable
    if Path(resolved).suffix.lower() == ".py":
        return [sys.executable, resolved]
    return [resolved]


def terminate_tree(proc: subprocess.Popen, *, wait_sec: float = 2.0) -> None:
    """Stop a process and everything it spawned.

    Shims such as ``pi.cmd`` start the real program as a child. Terminating
    only the shim leaves that child holding our pipes and its working
    directory, so blocked reads never return and snapshots cannot be deleted.
    """
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=wait_sec)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=wait_sec)
