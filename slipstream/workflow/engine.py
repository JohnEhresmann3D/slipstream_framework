from __future__ import annotations

import json
import os
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator

from ..config.models import Phase, Project, Workflow
from ..config.prompt import PhasePromptBuilder
from ..loop.backends.base import AgentBackend
from ..loop.decision_log import DecisionLog
from ..loop.evidence import CheckSpec, EvidenceCollector
from ..loop.guardrails import GuardrailConfig
from ..loop.operator import Operator, OperatorResult
from ..loop.state import RunStatus, RunStore
from ..loop.verification import Verifier
from ..loop.workspaces.base import DirectWorkspaceManager
from .state import (
    GateRecord,
    GateStatus,
    PhaseRecord,
    PhaseStatus,
    WorkflowState,
    WorkflowStatus,
    WorkflowStore,
    utc_now,
)

ARTIFACT_CHECK = "phase_output_exists"


class WorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class EngineLimits:
    """Defaults for phases that do not set their own circuit breaker."""

    max_iterations: int = 4
    max_stuck_iterations: int = 2
    per_call_timeout_sec: int = 900
    max_turns: int | None = None
    max_cost_usd: float | None = None  # across the whole workflow run


OperatorFactory = Callable[..., Operator]


class WorkflowEngine:
    """Drives a workflow's phases through the Slipstream operator.

    Each phase is one operator run (worker -> evidence -> verifier -> decision)
    with a fresh session. Phases hand off through Markdown artifacts, not chat
    history. Human gates pause the run until `approve` or `reject` is called;
    the engine never waits in-process, so every pause point survives restarts.
    """

    def __init__(
        self,
        project: Project,
        workspace: Path,
        worker: AgentBackend | None = None,
        verifier: Verifier | None = None,
        checks: Iterable[CheckSpec] = (),
        limits: EngineLimits | None = None,
        required_worker_capabilities: Iterable[str] = (),
        operator_factory: OperatorFactory = Operator,
    ):
        self.project = project
        self.workspace = Path(workspace).resolve()
        self.worker = worker
        self.verifier = verifier
        self.checks = tuple(checks)
        self.limits = limits or EngineLimits()
        self.required_worker_capabilities = set(required_worker_capabilities)
        self.operator_factory = operator_factory
        self.state_root = self.workspace / ".slipstream"
        self.store = WorkflowStore(self.state_root / "workflows")

    # ------------------------------------------------------------------ API

    def start(
        self,
        task: str,
        workflow_id: str | None = None,
        personas: Iterable[str] | None = None,
        workflow_run_id: str | None = None,
        launch: dict | None = None,
    ) -> WorkflowState:
        workflow = self._workflow(workflow_id or self.project.default_workflow)
        assigned = list(personas or workflow.default_personas or self.project.default_personas)
        for persona in assigned:
            if persona not in self.project.personas:
                raise WorkflowError(f"unknown persona {persona!r}")
        for phase in workflow.phases:
            if not self.project.resolve_agents(phase, assigned):
                raise WorkflowError(f"phase {phase.name!r} has no agents; assign personas")

        run_id = workflow_run_id or f"{workflow.id}-{uuid.uuid4().hex[:8]}"
        if self.store.exists(run_id):
            raise WorkflowError(f"workflow run {run_id!r} already exists; use resume")
        state = WorkflowState(
            workflow_run_id=run_id,
            workflow=workflow.id,
            task=task.strip(),
            personas=assigned,
            phases=[PhaseRecord(p.name) for p in workflow.phases],
            launch=dict(launch or {}),
        )
        self.store.save(state)
        with self._locked(run_id):
            self._log(state, "workflow_started", workflow=workflow.id, personas=assigned)
            return self._drive(state)

    def resume(self, workflow_run_id: str, launch: dict | None = None) -> WorkflowState:
        """Continue a run. `launch`, if given, replaces the saved launch settings
        before any agent call, so later resumes keep the same checks and budget."""
        with self._locked(workflow_run_id):
            return self._resume(workflow_run_id, launch)

    def _resume(self, workflow_run_id: str, launch: dict | None) -> WorkflowState:
        state = self.store.load(workflow_run_id)
        if launch is not None and launch != state.launch:
            state.launch = dict(launch)
            self.store.save(state)
            self._log(state, "launch_updated", launch=launch)
        if state.status is WorkflowStatus.DONE:
            return state
        if state.status is WorkflowStatus.AWAITING_APPROVAL:
            gate = state.pending_gate()
            raise WorkflowError(
                f"gate {gate.gate_id if gate else '?'} is awaiting approval; approve or reject it first"
            )
        record = state.current
        if record and record.status in (PhaseStatus.NEEDS_HUMAN, PhaseStatus.ERROR):
            # A human has looked at the stopped phase; start a fresh attempt.
            record.status = PhaseStatus.PENDING
            record.run_id = None
        self._log(state, "workflow_resumed", phase=record.name if record else None)
        return self._drive(state)

    def approve(self, workflow_run_id: str, gate_id: str | None = None, note: str = "", by: str | None = None) -> WorkflowState:
        with self._locked(workflow_run_id):
            return self._approve(workflow_run_id, gate_id, note, by)

    def _approve(self, workflow_run_id: str, gate_id: str | None, note: str, by: str | None) -> WorkflowState:
        state, gate = self._pending(workflow_run_id, gate_id)
        gate.status = GateStatus.APPROVED
        gate.decided_at = utc_now()
        gate.decided_by = by
        gate.note = note
        state.record(gate.phase).status = PhaseStatus.APPROVED
        state.status = WorkflowStatus.READY
        state.reason = f"gate {gate.gate_id} approved"
        self.store.save(state)
        self._log(state, "gate_approved", gate_id=gate.gate_id, by=by, note=note)
        return state

    def reject(self, workflow_run_id: str, note: str, gate_id: str | None = None, by: str | None = None) -> WorkflowState:
        if not note.strip():
            raise WorkflowError("rejecting a gate requires a note explaining what to change")
        with self._locked(workflow_run_id):
            return self._reject(workflow_run_id, note, gate_id, by)

    def _reject(self, workflow_run_id: str, note: str, gate_id: str | None, by: str | None) -> WorkflowState:
        state, gate = self._pending(workflow_run_id, gate_id)
        gate.status = GateStatus.REJECTED
        gate.decided_at = utc_now()
        gate.decided_by = by
        gate.note = note
        record = state.record(gate.phase)
        record.status = PhaseStatus.PENDING
        record.run_id = None
        record.feedback.append(note.strip())
        state.status = WorkflowStatus.READY
        state.reason = f"gate {gate.gate_id} rejected; phase {gate.phase} will re-run with feedback"
        self.store.save(state)
        self._log(state, "gate_rejected", gate_id=gate.gate_id, by=by, note=note)
        return state

    def status(self, workflow_run_id: str) -> WorkflowState:
        return self.store.load(workflow_run_id)

    def list_runs(self) -> list[WorkflowState]:
        return [self.store.load(run_id) for run_id in self.store.list_ids()]

    # ------------------------------------------------------------ internals

    @contextmanager
    def _locked(self, workflow_run_id: str) -> Iterator[None]:
        """Hold an exclusive per-run lock so two processes never drive one run."""
        if not self.store.exists(workflow_run_id):
            raise FileNotFoundError(f"no workflow run {workflow_run_id!r} under {self.store.root}")
        path = self.store.run_dir(workflow_run_id) / "lock"
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise WorkflowError(
                f"workflow run {workflow_run_id!r} is in use by another process ({path}). "
                "If no slipstream process is running it, delete that file and retry."
            ) from None
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"pid": os.getpid(), "since": utc_now()}))
        try:
            yield
        finally:
            path.unlink(missing_ok=True)

    def _workflow(self, workflow_id: str | None) -> Workflow:
        if not workflow_id:
            raise WorkflowError("no workflow given and no default workflow configured")
        try:
            return self.project.workflows[workflow_id]
        except KeyError:
            raise WorkflowError(
                f"unknown workflow {workflow_id!r}; available: {sorted(self.project.workflows)}"
            ) from None

    def _pending(self, workflow_run_id: str, gate_id: str | None) -> tuple[WorkflowState, GateRecord]:
        state = self.store.load(workflow_run_id)
        gate = state.pending_gate()
        if state.status is not WorkflowStatus.AWAITING_APPROVAL or gate is None:
            raise WorkflowError(f"workflow run {workflow_run_id!r} has no gate awaiting approval")
        if gate_id and gate.gate_id != gate_id:
            raise WorkflowError(f"pending gate is {gate.gate_id!r}, not {gate_id!r}")
        return state, gate

    def _log(self, state: WorkflowState, event: str, **fields) -> None:
        DecisionLog(self.store.run_dir(state.workflow_run_id) / "events.jsonl").append(event, **fields)

    def _artifact_path(self, state: WorkflowState, phase: Phase) -> Path:
        index = [r.name for r in state.phases].index(phase.name) + 1
        name = f"{index:02d}_{phase.name}_{phase.output}.md"
        return self.store.artifact_dir(state.workflow_run_id) / name

    def _rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.workspace).as_posix()

    def _stop(self, state: WorkflowState, status: WorkflowStatus, reason: str) -> WorkflowState:
        state.status = status
        state.reason = reason
        self.store.save(state)
        self._log(state, "workflow_stopped", status=status.value, reason=reason)
        return state

    def _drive(self, state: WorkflowState) -> WorkflowState:
        workflow = self._workflow(state.workflow)
        state.status = WorkflowStatus.RUNNING
        self.store.save(state)

        while state.phase_index < len(workflow.phases):
            phase = workflow.phases[state.phase_index]
            record = state.phases[state.phase_index]

            if record.status in (PhaseStatus.PENDING, PhaseStatus.RUNNING):
                self._run_phase(state, workflow, phase, record)
                if record.status is PhaseStatus.NEEDS_HUMAN:
                    return self._stop(state, WorkflowStatus.NEEDS_HUMAN, f"{phase.name}: {record.reason}")
                if record.status is PhaseStatus.ERROR:
                    return self._stop(state, WorkflowStatus.ERROR, f"{phase.name}: {record.reason}")

            if record.status is PhaseStatus.DONE:
                if phase.hitl_gate:
                    gate = GateRecord(
                        gate_id=phase.gate_id or f"{phase.name}-gate",
                        phase=phase.name,
                        description=phase.gate_description or f"Approve {phase.name} output",
                    )
                    state.gates.append(gate)
                    self._log(state, "gate_requested", gate_id=gate.gate_id, artifact=record.artifact)
                    return self._stop(
                        state,
                        WorkflowStatus.AWAITING_APPROVAL,
                        f"gate {gate.gate_id}: {gate.description}. Review {record.artifact}",
                    )
                record.status = PhaseStatus.APPROVED

            if record.status is PhaseStatus.APPROVED:
                target = (
                    workflow.phases[state.phase_index + 1].name
                    if state.phase_index + 1 < len(workflow.phases)
                    else "complete"
                )
                blocked = self._transition_blockers(state, workflow, phase, target)
                if blocked:
                    return self._stop(
                        state,
                        WorkflowStatus.NEEDS_HUMAN,
                        f"transition {phase.name}_to_{target} blocked: {', '.join(blocked)}",
                    )
                state.phase_index += 1
                self.store.save(state)
                self._log(state, "phase_advanced", source=phase.name, target=target)

        return self._stop(state, WorkflowStatus.DONE, "all phases complete")

    def _transition_blockers(self, state: WorkflowState, workflow: Workflow, phase: Phase, target: str) -> list[str]:
        record = state.record(phase.name)
        transition = workflow.transition(phase.name, target)
        # These hold for every transition, declared or not.
        requires = {"phase_done", "artifact_exists"}
        if phase.hitl_gate:
            requires.add("hitl_gate_approved")
        if transition:
            requires.update(transition.requires)
        blockers: list[str] = []
        if "phase_done" in requires and record.status is not PhaseStatus.APPROVED:
            blockers.append("phase_done")
        if "artifact_exists" in requires and not (
            record.artifact and (self.workspace / record.artifact).is_file()
        ):
            blockers.append("artifact_exists")
        if "hitl_gate_approved" in requires and not (
            phase.gate_id and state.gate_approved(phase.gate_id)
        ):
            blockers.append("hitl_gate_approved")
        return blockers

    def _phase_goal(self, state: WorkflowState, phase: Phase, artifact_rel: str) -> str:
        return (
            f"{phase.description}.\n\n"
            f"TASK:\n{state.task}\n\n"
            f"Write this phase's output ({phase.output}) as Markdown to `{artifact_rel}`. "
            "That file is how the next phase and the human reviewer will see your work."
        )

    def _phase_criteria(self, phase: Phase, artifact_rel: str, record: PhaseRecord) -> list[str]:
        criteria = [f"`{artifact_rel}` exists and contains the {phase.output} for this phase"]
        criteria += [f"Reviewer feedback is addressed: {note}" for note in record.feedback]
        criteria += phase.checklist
        criteria += phase.standards
        if phase.moral_gate:
            criteria.append("The phase output answers each item of the constitution's Engineering Moral Gate")
        if phase.run_checks and self.checks:
            criteria.append("All required project checks pass")
        return criteria

    def _phase_context(self, state: WorkflowState, record: PhaseRecord) -> list[str]:
        sections: list[str] = []
        earlier = [
            r for r in state.phases[: state.phase_index]
            if r.artifact and (self.workspace / r.artifact).is_file()
        ]
        if earlier:
            sections.append(
                "## Earlier phase outputs (read these before working)\n"
                + "\n".join(f"- {r.name}: `{r.artifact}`" for r in earlier)
            )
        previous = sorted(
            self.store.artifact_dir(state.workflow_run_id).glob(f"*_{record.name}_*.attempt*.md")
        )
        if previous:
            sections.append(
                "## Your previous attempts at this phase (for reference; write a new output)\n"
                + "\n".join(f"- `{self._rel(p)}`" for p in previous)
            )
        if record.feedback:
            sections.append(
                "## Reviewer feedback on earlier attempts (address all of it)\n"
                + "\n".join(f"- {note}" for note in record.feedback)
            )
        return sections

    def _phase_checks(self, phase: Phase, artifact_rel: str) -> list[CheckSpec]:
        exists = CheckSpec(
            ARTIFACT_CHECK,
            (
                sys.executable,
                "-c",
                "import pathlib, sys; p = pathlib.Path(sys.argv[1]); "
                "sys.exit(0 if p.is_file() and p.stat().st_size > 0 else 1)",
                artifact_rel,
            ),
            timeout_sec=30,
        )
        return [exists, *(self.checks if phase.run_checks else ())]

    def _remaining_budget(self, state: WorkflowState) -> float | None:
        if self.limits.max_cost_usd is None:
            return None
        return self.limits.max_cost_usd - state.total_cost_usd

    def _run_phase(self, state: WorkflowState, workflow: Workflow, phase: Phase, record: PhaseRecord) -> None:
        if self.worker is None or self.verifier is None:
            raise WorkflowError("running a phase needs a worker backend and a verifier")
        agents = self.project.resolve_agents(phase, state.personas)
        lead, consultants = agents[0], agents[1:]
        artifact = self._artifact_path(state, phase)
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact_rel = self._rel(artifact)

        remaining = self._remaining_budget(state)
        if remaining is not None and remaining <= 0:
            record.status = PhaseStatus.NEEDS_HUMAN
            record.reason = "workflow_budget_exhausted"
            self.store.save(state)
            return

        resumable = (
            record.status is PhaseStatus.RUNNING
            and record.run_id
            and (RunStore(self.state_root / "runs").run_dir(record.run_id) / "state.json").is_file()
        )
        if not resumable and artifact.exists():
            # A fresh attempt must produce a fresh artifact; otherwise the
            # existence check and verifier would accept the rejected one.
            artifact.replace(artifact.with_name(f"{artifact.stem}.attempt{record.attempts or 1}.md"))

        operator = self.operator_factory(
            root=self.workspace,
            worker=self.worker,
            verifier=self.verifier,
            evidence_collector=EvidenceCollector(self._phase_checks(phase, artifact_rel), [artifact_rel]),
            guardrails=GuardrailConfig(
                max_iterations=phase.max_turns or self.limits.max_iterations,
                max_stuck_iterations=phase.stall_threshold or self.limits.max_stuck_iterations,
                max_cost_usd=remaining,
                per_call_timeout_sec=self.limits.per_call_timeout_sec,
                max_turns=self.limits.max_turns,
            ),
            workspace_manager=DirectWorkspaceManager(),
            prompt_builder=PhasePromptBuilder(
                self.project, lead, phase, consultants, self._phase_context(state, record)
            ),
            runs_root=self.state_root / "runs",
            required_worker_capabilities=self.required_worker_capabilities,
        )

        if resumable:
            self._log(state, "phase_resumed", phase=phase.name, run_id=record.run_id)
            result = operator.resume(record.run_id)
        else:
            record.attempts += 1
            record.run_id = f"{state.workflow_run_id}-{phase.name}-{record.attempts}"
            record.artifact = artifact_rel
            record.run_cost_usd = 0.0
            record.status = PhaseStatus.RUNNING
            self.store.save(state)
            self._log(state, "phase_started", phase=phase.name, lead=lead, consultants=consultants, run_id=record.run_id)
            result = operator.run(
                self._phase_goal(state, phase, artifact_rel),
                self._phase_criteria(phase, artifact_rel, record),
                run_id=record.run_id,
            )
        self._record_result(state, record, result)

    def _record_result(self, state: WorkflowState, record: PhaseRecord, result: OperatorResult) -> None:
        delta = max(result.total_cost_usd - record.run_cost_usd, 0.0)
        record.run_cost_usd = result.total_cost_usd
        record.cost_usd += delta
        state.total_cost_usd += delta
        record.reason = result.reason
        if result.status is RunStatus.DONE:
            record.status = PhaseStatus.DONE
        elif result.status is RunStatus.ERROR:
            record.status = PhaseStatus.ERROR
        else:
            record.status = PhaseStatus.NEEDS_HUMAN
        self.store.save(state)
        self._log(
            state,
            "phase_finished",
            phase=record.name,
            status=record.status.value,
            reason=result.reason,
            iterations=result.iterations,
            cost_usd=result.total_cost_usd,
        )
