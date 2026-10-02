from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .backends.base import AgentResult
from .progress import ProgressSnapshot
from .verification import GateResult


class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    DONE = "DONE"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    ERROR = "ERROR"


class RunStage(str, Enum):
    START = "START"
    WORKER_COMPLETE = "WORKER_COMPLETE"
    EVIDENCE_COMPLETE = "EVIDENCE_COMPLETE"
    VERIFY_COMPLETE = "VERIFY_COMPLETE"
    FINISHED = "FINISHED"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunState:
    run_id: str
    goal: str
    acceptance_criteria: list[str]
    workspace: str
    status: RunStatus = RunStatus.RUNNING
    stage: RunStage = RunStage.START
    iteration: int = 0
    total_cost_usd: float = 0.0
    budget_status: str = "NOT_CONFIGURED"
    session_id: str | None = None
    no_progress_count: int = 0
    consecutive_backend_errors: int = 0
    consecutive_verifier_errors: int = 0
    current_prompt: str = ""
    worker_result: dict[str, Any] | None = None
    evidence_file: str | None = None
    gate_result: dict[str, Any] | None = None
    progress_snapshot: dict[str, Any] | None = None
    final_reason: str | None = None
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    @classmethod
    def start(
        cls,
        goal: str,
        acceptance_criteria: list[str],
        workspace: Path,
        run_id: str | None = None,
    ) -> "RunState":
        return cls(
            run_id=run_id or uuid.uuid4().hex,
            goal=goal,
            acceptance_criteria=list(acceptance_criteria),
            workspace=str(Path(workspace)),
        )

    def record_worker(self, result: AgentResult) -> None:
        self.worker_result = {
            "text": result.text,
            "session_id": result.session_id,
            "is_error": result.is_error,
            "cost_usd": result.cost_usd,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "turns": result.turns,
            "tool_calls": result.tool_calls,
            "events": result.events,
            "raw": result.raw if isinstance(result.raw, (dict, list, str, int, float, bool, type(None))) else repr(result.raw),
            "stderr": result.stderr,
        }
        if result.session_id:
            self.session_id = result.session_id
        if result.cost_usd is not None:
            self.total_cost_usd += result.cost_usd
        self.stage = RunStage.WORKER_COMPLETE
        self.updated_at = _utc_now()

    def agent_result(self) -> AgentResult:
        if not self.worker_result:
            raise ValueError("No worker result is checkpointed")
        return AgentResult(**self.worker_result)

    def record_evidence(self, relative_file: str) -> None:
        self.evidence_file = relative_file
        self.stage = RunStage.EVIDENCE_COMPLETE
        self.updated_at = _utc_now()

    def record_gate(self, gate: GateResult) -> None:
        self.gate_result = gate.to_dict()
        self.stage = RunStage.VERIFY_COMPLETE
        self.updated_at = _utc_now()

    def gate(self) -> GateResult:
        if not self.gate_result:
            raise ValueError("No gate result is checkpointed")
        return GateResult.from_dict(self.gate_result)

    def set_progress(self, snapshot: ProgressSnapshot) -> None:
        self.progress_snapshot = snapshot.to_dict()
        self.updated_at = _utc_now()

    def previous_progress(self) -> ProgressSnapshot | None:
        return ProgressSnapshot.from_dict(self.progress_snapshot) if self.progress_snapshot else None

    def finish(self, status: RunStatus, reason: str) -> None:
        self.status = status
        self.stage = RunStage.FINISHED
        self.final_reason = reason
        self.updated_at = _utc_now()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["stage"] = self.stage.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunState":
        copied = dict(data)
        copied["status"] = RunStatus(copied["status"])
        copied["stage"] = RunStage(copied["stage"])
        return cls(**copied)


class RunStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def run_dir(self, run_id: str) -> Path:
        return self.root / run_id

    def initialize(self, state: RunState, manifest: dict[str, Any]) -> Path:
        run_dir = self.run_dir(state.run_id)
        (run_dir / "evidence").mkdir(parents=True, exist_ok=True)
        (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
        (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        self.checkpoint(state)
        return run_dir

    def checkpoint(self, state: RunState) -> None:
        run_dir = self.run_dir(state.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "state.json"
        tmp = run_dir / "state.json.tmp"
        tmp.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    def load(self, run_id: str) -> RunState:
        path = self.run_dir(run_id) / "state.json"
        return RunState.from_dict(json.loads(path.read_text(encoding="utf-8")))
