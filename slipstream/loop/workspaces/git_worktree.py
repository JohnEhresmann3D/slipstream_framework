from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .base import WorkspaceHandle


@dataclass(frozen=True)
class GitWorktreePolicy:
    preserve_on_success: bool = True
    preserve_on_needs_human: bool = True
    preserve_on_error: bool = True


class GitWorktreeWorkspaceManager:
    """Creates an isolated detached worktree under `.slipstream/worktrees/`."""

    def __init__(self, policy: GitWorktreePolicy | None = None):
        self.policy = policy or GitWorktreePolicy()

    @staticmethod
    def _git(source_root: Path, *args: str) -> str:
        proc = subprocess.run(["git", *args], cwd=source_root, text=True, capture_output=True, timeout=60)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
        return proc.stdout.strip()

    def prepare(self, run_id: str, source_root: Path) -> WorkspaceHandle:
        source_root = Path(source_root).resolve()
        baseline = self._git(source_root, "rev-parse", "HEAD")
        path = source_root / ".slipstream" / "worktrees" / run_id
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            self._git(source_root, "worktree", "add", "--detach", str(path), baseline)
        return WorkspaceHandle(path=path, source_root=source_root, isolated=True, baseline_revision=baseline)

    def cleanup(self, handle: WorkspaceHandle, outcome: str) -> None:
        if not handle.isolated:
            return
        preserve = {
            "DONE": self.policy.preserve_on_success,
            "NEEDS_HUMAN": self.policy.preserve_on_needs_human,
            "ERROR": self.policy.preserve_on_error,
        }.get(outcome, True)
        if preserve:
            return
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(handle.path)],
            cwd=handle.source_root,
            text=True,
            capture_output=True,
            timeout=60,
        )
