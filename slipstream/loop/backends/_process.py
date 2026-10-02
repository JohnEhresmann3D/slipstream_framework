from __future__ import annotations

import shutil
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
