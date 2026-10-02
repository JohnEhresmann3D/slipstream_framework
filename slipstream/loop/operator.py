from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .backends.base import AgentBackend, AgentRequest, AgentResult, BackendError
from .decision_log import DecisionLog
from .evidence import EvidenceBundle, EvidenceCollector
from .guardrails import BudgetStatus, GuardrailConfig, Guardrails
from .progress import ProgressDetector, ProgressSnapshot
from .prompt_builder import PromptBuilder
from .state import RunStage, RunState, RunStatus, RunStore
from .verification import GateResult, Verdict, Verifier
from .workspaces.base import DirectWorkspaceManager, WorkspaceHandle, WorkspaceManager


@dataclass(frozen=True)
class OperatorResult:
    run_id: str
    status: RunStatus
    reason: str
    iterations: int
    total_cost_usd: float
    budget_status: str
    workspace: Path
    last_gate: GateResult | None


class Operator:
    """Provider-neutral Slipstream orchestration core.

    Architectural invariant: this module imports only backend protocols/data
    contracts. It never imports Claude Code, Pi, OpenAI, or any provider-specific
    adapter.
    """

    def __init__(
        self,
        root: Path,
        worker: AgentBackend,
        verifier: Verifier,
        evidence_collector: EvidenceCollector,
        guardrails: GuardrailConfig | None = None,
        workspace_manager: WorkspaceManager | None = None,
        prompt_builder: PromptBuilder | None = None,
        runs_root: Path | None = None,
        required_worker_capabilities: set[str] | None = None,
    ):
        self.root = Path(root).resolve()
        self.worker = worker
        self.verifier = verifier
        self.evidence_collector = evidence_collector
        self.guardrails = Guardrails(guardrails or GuardrailConfig())
        self.workspace_manager = workspace_manager or DirectWorkspaceManager()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.run_store = RunStore(runs_root or (self.root / ".slipstream" / "runs"))
        self.progress_detector = ProgressDetector()
        self.required_worker_capabilities = set(required_worker_capabilities or ())

    @staticmethod
    def _backend_manifest(backend: AgentBackend) -> dict[str, Any]:
        return {
            "name": backend.name,
            "capabilities": asdict(backend.capabilities),
            "policy": asdict(backend.policy),
            "adapter_class": f"{backend.__class__.__module__}.{backend.__class__.__name__}",
        }

    def _verifier_backend(self) -> AgentBackend | None:
        candidate = getattr(self.verifier, "backend", None)
        # Structural check avoids depending on a concrete verifier implementation.
        if candidate is not None and hasattr(candidate, "run") and hasattr(candidate, "capabilities") and hasattr(candidate, "policy"):
            return candidate
        return None

    def _manifest(self, state: RunState, handle: WorkspaceHandle) -> dict[str, Any]:
        verifier_backend = self._verifier_backend()
        return {
            "run_id": state.run_id,
            "created_at": state.created_at,
            "goal": state.goal,
            "acceptance_criteria": state.acceptance_criteria,
            "worker": self._backend_manifest(self.worker),
            "verifier": self._backend_manifest(verifier_backend) if verifier_backend else {
                "type": f"{self.verifier.__class__.__module__}.{self.verifier.__class__.__name__}"
            },
            "guardrails": asdict(self.guardrails.config),
            "workspace": {
                "source_root": str(handle.source_root),
                "active_path": str(handle.path),
                "isolated": handle.isolated,
                "baseline_revision": handle.baseline_revision,
            },
            "slipstream_version": "vendor-neutral-update-dev",
            "required_worker_capabilities": sorted(self.required_worker_capabilities),
            "prompt_inputs": {
                "constitution_present": bool(getattr(self.prompt_builder, "constitution", "")),
                "persona_present": bool(getattr(self.prompt_builder, "persona", "")),
                "skills": list(getattr(self.prompt_builder, "skills", [])),
            },
        }

    def _result(self, state: RunState) -> OperatorResult:
        gate = GateResult.from_dict(state.gate_result) if state.gate_result else None
        return OperatorResult(
            run_id=state.run_id,
            status=state.status,
            reason=state.final_reason or "",
            iterations=state.iteration,
            total_cost_usd=state.total_cost_usd,
            budget_status=state.budget_status,
            workspace=Path(state.workspace),
            last_gate=gate,
        )

    def _finish(self, state: RunState, handle: WorkspaceHandle, log: DecisionLog, status: RunStatus, reason: str) -> OperatorResult:
        state.finish(status, reason)
        self.run_store.checkpoint(state)
        log.append("finish", status=status.value, reason=reason, total_cost_usd=state.total_cost_usd)
        self.workspace_manager.cleanup(handle, status.value)
        return self._result(state)

    def _budget_breach_check(self, state: RunState) -> None:
        cap = self.guardrails.config.max_cost_usd
        if cap is not None and state.total_cost_usd > cap:
            state.budget_status = BudgetStatus.BREACHED.value

    def _worker_call(self, state: RunState, handle: WorkspaceHandle, log: DecisionLog) -> AgentResult | None:
        for capability in sorted(self.required_worker_capabilities):
            if not hasattr(self.worker.capabilities, capability):
                state.final_reason = f"unknown_required_capability:{capability}"
                return None
            if not bool(getattr(self.worker.capabilities, capability)):
                state.final_reason = f"missing_worker_capability:{capability}"
                return None

        preflight = self.guardrails.preflight(
            iteration=state.iteration,
            total_cost_usd=state.total_cost_usd,
            worker=self.worker,
        )
        state.budget_status = preflight.budget_status.value
        if not preflight.allowed:
            state.final_reason = preflight.reason
            return None

        request = AgentRequest(
            prompt=state.current_prompt,
            workspace=handle.path,
            session_id=state.session_id,
            max_turns=self.guardrails.config.max_turns,
            timeout_sec=self.guardrails.config.per_call_timeout_sec,
            metadata={
                "run_id": state.run_id,
                "iteration": state.iteration + 1,
                "budget_remaining_usd": preflight.remaining_cost_usd,
            },
        )
        log.append(
            "worker_start",
            iteration=state.iteration + 1,
            backend=self.worker.name,
            session_id=state.session_id,
            budget_status=state.budget_status,
        )
        try:
            result = self.worker.run(request)
        except BackendError as exc:
            state.iteration += 1
            state.consecutive_backend_errors += 1
            state.stage = RunStage.START
            state.updated_at = state.updated_at
            self.run_store.checkpoint(state)
            log.append("worker_backend_error", iteration=state.iteration, error=repr(exc))
            if self.guardrails.should_stop_for_backend_errors(state.consecutive_backend_errors):
                state.final_reason = f"worker_backend_error_limit: {exc}"
                return None
            return AgentResult(text="", is_error=True, stderr=str(exc), raw={"retryable_backend_error": True})

        state.iteration += 1
        state.consecutive_backend_errors = 0
        state.record_worker(result)
        self._budget_breach_check(state)
        self.run_store.checkpoint(state)
        output_path = self.run_store.run_dir(state.run_id) / "outputs" / f"iteration_{state.iteration:03d}.md"
        output_path.write_text(result.text or "", encoding="utf-8")
        log.append(
            "worker_complete",
            iteration=state.iteration,
            is_error=result.is_error,
            session_id=result.session_id,
            cost_usd=result.cost_usd,
            total_cost_usd=state.total_cost_usd,
        )
        return result

    def _collect_evidence(self, state: RunState, handle: WorkspaceHandle, log: DecisionLog) -> EvidenceBundle:
        evidence = self.evidence_collector.collect(handle.path, state.acceptance_criteria)
        filename = f"iteration_{state.iteration:03d}.json"
        path = self.run_store.run_dir(state.run_id) / "evidence" / filename
        self.evidence_collector.dump(evidence, path)
        state.record_evidence(str(Path("evidence") / filename))
        self.run_store.checkpoint(state)
        log.append(
            "evidence_complete",
            iteration=state.iteration,
            changed_files=evidence.changed_files,
            passed_checks=evidence.passed_checks,
            failed_checks=evidence.failed_checks,
            required_failure=evidence.has_required_failure,
        )
        return evidence

    def _load_evidence(self, state: RunState) -> EvidenceBundle:
        if not state.evidence_file:
            raise RuntimeError("State says evidence exists but no evidence file is recorded")
        return self.evidence_collector.load(self.run_store.run_dir(state.run_id) / state.evidence_file)

    def _verify(
        self,
        state: RunState,
        handle: WorkspaceHandle,
        evidence: EvidenceBundle,
        worker_result: AgentResult,
        log: DecisionLog,
    ) -> GateResult | None:
        verifier_backend = self._verifier_backend()
        if verifier_backend is not None:
            cost_check = self.guardrails.cost_preflight(total_cost_usd=state.total_cost_usd, backend=verifier_backend)
            # Preserve UNKNOWN if either worker or verifier is unbounded.
            if cost_check.budget_status is BudgetStatus.UNKNOWN:
                state.budget_status = BudgetStatus.UNKNOWN.value
            elif state.budget_status != BudgetStatus.UNKNOWN.value:
                state.budget_status = cost_check.budget_status.value
            if not cost_check.allowed:
                state.final_reason = "verifier_" + str(cost_check.reason)
                self.run_store.checkpoint(state)
                log.append("verifier_budget_stop", reason=cost_check.reason)
                return None

        log.append("verify_start", iteration=state.iteration)
        try:
            gate = self.verifier.evaluate(
                state.goal,
                state.acceptance_criteria,
                evidence,
                worker_result,
                state,
                handle.path,
            )
        except Exception as exc:
            state.consecutive_verifier_errors += 1
            self.run_store.checkpoint(state)
            log.append("verifier_error", iteration=state.iteration, error=repr(exc))
            if state.consecutive_verifier_errors >= 2:
                state.final_reason = f"repeated_verifier_infrastructure_failure: {exc}"
                return None
            gate = GateResult(Verdict.STUCK, f"Verifier infrastructure error: {exc}", list(state.acceptance_criteria))
        else:
            if gate.reason.startswith("Verifier infrastructure error:"):
                state.consecutive_verifier_errors += 1
            else:
                state.consecutive_verifier_errors = 0

        if gate.cost_usd is not None:
            state.total_cost_usd += gate.cost_usd
            self._budget_breach_check(state)

        # Operator-level deterministic veto makes false-claim protection hold
        # even for custom verifier implementations.
        if evidence.has_required_failure and gate.verdict is Verdict.MET:
            failed = [c.name for c in evidence.checks if c.required and c.passed is False]
            gate = GateResult(
                Verdict.PROGRESSING,
                "Operator vetoed MET because deterministic required checks failed: " + ", ".join(failed),
                gate.unmet_criteria or failed,
                raw=gate.raw,
                cost_usd=gate.cost_usd,
            )

        state.record_gate(gate)
        self.run_store.checkpoint(state)
        log.append(
            "verify_complete",
            iteration=state.iteration,
            verdict=gate.verdict.value,
            reason=gate.reason,
            unmet_criteria=gate.unmet_criteria,
            cost_usd=gate.cost_usd,
            total_cost_usd=state.total_cost_usd,
        )
        return gate

    def _decide(
        self,
        state: RunState,
        handle: WorkspaceHandle,
        evidence: EvidenceBundle,
        worker_result: AgentResult,
        gate: GateResult,
        log: DecisionLog,
    ) -> OperatorResult | None:
        previous = state.previous_progress()
        current = ProgressSnapshot.from_evidence(
            evidence,
            unmet_criteria=tuple(gate.unmet_criteria),
            worker_text=worker_result.text,
        )
        delta = self.progress_detector.compare(previous, current)
        state.no_progress_count = 0 if delta.has_progress else state.no_progress_count + 1
        state.set_progress(current)
        self.run_store.checkpoint(state)
        log.append(
            "progress_evaluated",
            iteration=state.iteration,
            has_progress=delta.has_progress,
            reasons=list(delta.reasons),
            prose_changed=delta.prose_changed,
            no_progress_count=state.no_progress_count,
        )

        if gate.verdict is Verdict.MET:
            return self._finish(state, handle, log, RunStatus.DONE, gate.reason or "acceptance_criteria_met")

        if gate.verdict is Verdict.STUCK:
            if gate.reason.startswith("Verifier infrastructure error:") and state.consecutive_verifier_errors >= 2:
                return self._finish(state, handle, log, RunStatus.ERROR, "repeated_verifier_infrastructure_failure")
            return self._finish(state, handle, log, RunStatus.NEEDS_HUMAN, gate.reason or "verifier_reported_stuck")

        if self.guardrails.should_stop_for_no_progress(state.no_progress_count):
            return self._finish(state, handle, log, RunStatus.NEEDS_HUMAN, "evidence_based_no_progress_limit")

        state.current_prompt = self.prompt_builder.followup(
            state.goal, state.acceptance_criteria, gate, evidence
        )
        state.stage = RunStage.START
        self.run_store.checkpoint(state)
        log.append("continue", iteration=state.iteration)
        return None

    def _run_state(self, state: RunState, handle: WorkspaceHandle) -> OperatorResult:
        run_dir = self.run_store.run_dir(state.run_id)
        log = DecisionLog(run_dir / "decisions.jsonl")

        while state.status is RunStatus.RUNNING:
            if state.stage is RunStage.START:
                result = self._worker_call(state, handle, log)
                if result is None:
                    reason = state.final_reason or "worker_preflight_failed"
                    status = RunStatus.ERROR if reason.startswith("worker_backend_error_limit:") else RunStatus.NEEDS_HUMAN
                    return self._finish(state, handle, log, status, reason)
                if state.budget_status == BudgetStatus.BREACHED.value:
                    return self._finish(
                        state, handle, log, RunStatus.ERROR,
                        "monetary_budget_breached_by_worker_call",
                    )
                if result.is_error:
                    retryable = isinstance(result.raw, dict) and result.raw.get("retryable_backend_error")
                    if retryable and not self.guardrails.should_stop_for_backend_errors(state.consecutive_backend_errors):
                        continue
                    return self._finish(state, handle, log, RunStatus.ERROR, result.stderr or "worker_returned_error")

            if state.stage is RunStage.WORKER_COMPLETE:
                worker_result = state.agent_result()
                if worker_result.is_error:
                    return self._finish(state, handle, log, RunStatus.ERROR, worker_result.stderr or "worker_returned_error")
                self._collect_evidence(state, handle, log)

            if state.stage is RunStage.EVIDENCE_COMPLETE:
                evidence = self._load_evidence(state)
                worker_result = state.agent_result()
                gate = self._verify(state, handle, evidence, worker_result, log)
                if state.budget_status == BudgetStatus.BREACHED.value:
                    return self._finish(
                        state, handle, log, RunStatus.ERROR,
                        "monetary_budget_breached_by_verifier_call",
                    )
                if gate is None:
                    if state.final_reason and state.final_reason.startswith("repeated_verifier"):
                        return self._finish(state, handle, log, RunStatus.ERROR, state.final_reason)
                    return self._finish(state, handle, log, RunStatus.NEEDS_HUMAN, state.final_reason or "verifier_unavailable")

            if state.stage is RunStage.VERIFY_COMPLETE:
                evidence = self._load_evidence(state)
                worker_result = state.agent_result()
                gate = state.gate()
                outcome = self._decide(state, handle, evidence, worker_result, gate, log)
                if outcome is not None:
                    return outcome

        return self._result(state)

    def run(self, goal: str, acceptance_criteria: list[str], run_id: str | None = None) -> OperatorResult:
        # Prepare isolation before state so the active workspace is the one
        # persisted into checkpoints and evidence.
        provisional_run_id = run_id or __import__("uuid").uuid4().hex
        handle = self.workspace_manager.prepare(provisional_run_id, self.root)
        state = RunState.start(goal, acceptance_criteria, handle.path, run_id=provisional_run_id)
        state.current_prompt = self.prompt_builder.initial(goal, acceptance_criteria)
        self.run_store.initialize(state, self._manifest(state, handle))
        DecisionLog(self.run_store.run_dir(state.run_id) / "decisions.jsonl").append("run_started")
        return self._run_state(state, handle)

    def resume(self, run_id: str) -> OperatorResult:
        state = self.run_store.load(run_id)
        if state.status is not RunStatus.RUNNING:
            return self._result(state)
        path = Path(state.workspace)
        handle = WorkspaceHandle(
            path=path,
            source_root=self.root,
            isolated=path.resolve() != self.root.resolve(),
            baseline_revision=None,
        )
        DecisionLog(self.run_store.run_dir(state.run_id) / "decisions.jsonl").append(
            "run_resumed", stage=state.stage.value, iteration=state.iteration
        )
        return self._run_state(state, handle)
