from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class WorkspaceHandle:
    path: Path
    source_root: Path
    isolated: bool
    baseline_revision: str | None = None


class WorkspaceManager(Protocol):
    def prepare(self, run_id: str, source_root: Path) -> WorkspaceHandle: ...

    def cleanup(self, handle: WorkspaceHandle, outcome: str) -> None: ...


class DirectWorkspaceManager:
    def prepare(self, run_id: str, source_root: Path) -> WorkspaceHandle:
        return WorkspaceHandle(path=Path(source_root).resolve(), source_root=Path(source_root).resolve(), isolated=False)

    def cleanup(self, handle: WorkspaceHandle, outcome: str) -> None:
        return None
