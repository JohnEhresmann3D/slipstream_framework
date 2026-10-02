from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class WorkflowStatus(str, Enum):
    READY = "READY"  # waiting to be started or resumed
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    ERROR = "ERROR"
    DONE = "DONE"


class PhaseStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"  # operator verdict MET; gate (if any) not yet decided
    APPROVED = "APPROVED"  # gate approved, or no gate; ready to advance
    NEEDS_HUMAN = "NEEDS_HUMAN"
    ERROR = "ERROR"


class GateStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PhaseRecord:
    name: str
    status: PhaseStatus = PhaseStatus.PENDING
    attempts: int = 0
    run_id: str | None = None
    artifact: str | None = None
    reason: str = ""
    cost_usd: float = 0.0  # across all attempts
    run_cost_usd: float = 0.0  # portion of the current run already counted
    feedback: list[str] = field(default_factory=list)


@dataclass
class GateRecord:
    gate_id: str
    phase: str
    description: str
    status: GateStatus = GateStatus.PENDING
    requested_at: str = field(default_factory=utc_now)
    decided_at: str | None = None
    decided_by: str | None = None
    note: str = ""


@dataclass
class WorkflowState:
    workflow_run_id: str
    workflow: str
    task: str
    personas: list[str]
    phases: list[PhaseRecord]
    status: WorkflowStatus = WorkflowStatus.READY
    phase_index: int = 0
    gates: list[GateRecord] = field(default_factory=list)
    total_cost_usd: float = 0.0
    reason: str = ""
    launch: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @property
    def current(self) -> PhaseRecord | None:
        if 0 <= self.phase_index < len(self.phases):
            return self.phases[self.phase_index]
        return None

    def record(self, name: str) -> PhaseRecord:
        for record in self.phases:
            if record.name == name:
                return record
        raise KeyError(name)

    def pending_gate(self) -> GateRecord | None:
        for gate in reversed(self.gates):
            if gate.status is GateStatus.PENDING:
                return gate
        return None

    def gate_approved(self, gate_id: str) -> bool:
        for gate in reversed(self.gates):
            if gate.gate_id == gate_id:
                return gate.status is GateStatus.APPROVED
        return False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        for record in data["phases"]:
            record["status"] = record["status"].value
        for gate in data["gates"]:
            gate["status"] = gate["status"].value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowState":
        copied = dict(data)
        copied["status"] = WorkflowStatus(copied["status"])
        copied["phases"] = [
            PhaseRecord(**{**p, "status": PhaseStatus(p["status"])}) for p in copied.get("phases", [])
        ]
        copied["gates"] = [
            GateRecord(**{**g, "status": GateStatus(g["status"])}) for g in copied.get("gates", [])
        ]
        return cls(**copied)


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class WorkflowStore:
    """Persists workflow state under `<workspace>/.slipstream/workflows/<id>/`."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def run_dir(self, workflow_run_id: str) -> Path:
        if not _SAFE_ID.match(workflow_run_id):
            raise ValueError(f"invalid workflow run id: {workflow_run_id!r}")
        return self.root / workflow_run_id

    def artifact_dir(self, workflow_run_id: str) -> Path:
        return self.run_dir(workflow_run_id) / "artifacts"

    def exists(self, workflow_run_id: str) -> bool:
        return (self.run_dir(workflow_run_id) / "state.json").is_file()

    def save(self, state: WorkflowState) -> None:
        state.updated_at = utc_now()
        run_dir = self.run_dir(state.workflow_run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "state.json"
        tmp = run_dir / "state.json.tmp"
        tmp.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(path)

    def load(self, workflow_run_id: str) -> WorkflowState:
        path = self.run_dir(workflow_run_id) / "state.json"
        if not path.is_file():
            raise FileNotFoundError(f"no workflow run {workflow_run_id!r} under {self.root}")
        return WorkflowState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        runs = [p for p in self.root.iterdir() if (p / "state.json").is_file()]
        return [p.name for p in sorted(runs, key=lambda p: (p / "state.json").stat().st_mtime)]
