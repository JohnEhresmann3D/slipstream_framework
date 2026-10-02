from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from slipstream.config import load_project
from slipstream.loop.backends.base import AgentRequest, AgentResult, BackendCapabilities, BackendPolicy
from slipstream.loop.evidence import CheckSpec
from slipstream.loop.verification import GateResult, Verdict
from slipstream.workflow import (
    EngineLimits,
    PhaseStatus,
    WorkflowEngine,
    WorkflowError,
    WorkflowStatus,
)
from tests.fakes.fake_verifier import FakeVerifier

REPO = Path(__file__).resolve().parents[1]
ARTIFACT = re.compile(r"as Markdown to `([^`]+)`")


class ArtifactWorker:
    """Fake worker that writes the phase artifact named in its prompt."""

    def __init__(self, *, write: bool = True, cost: float | None = None, explode_on_call: int | None = None):
        self.write = write
        self.cost = cost
        self.explode_on_call = explode_on_call
        self.calls: list[AgentRequest] = []

    name = "artifact-fake"
    capabilities = BackendCapabilities(sessions=True, filesystem=True, shell=True, cost_reporting=True)

    @property
    def policy(self) -> BackendPolicy:
        return BackendPolicy(None)

    def run(self, request: AgentRequest) -> AgentResult:
        self.calls.append(request)
        if self.explode_on_call == len(self.calls):
            raise KeyboardInterrupt("simulated crash")
        match = ARTIFACT.search(request.prompt)
        if self.write and match:
            path = Path(request.workspace) / match.group(1)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# output\ncall {len(self.calls)}\n", encoding="utf-8")
        return AgentResult(text="wrote artifact", session_id="s", cost_usd=self.cost)

    def abort(self) -> None:
        return None

    def close(self) -> None:
        return None


@pytest.fixture(scope="module")
def project():
    return load_project(REPO)


def _engine(project, workspace, worker=None, verifier=None, **kwargs) -> WorkflowEngine:
    return WorkflowEngine(
        project,
        workspace,
        worker=worker or ArtifactWorker(),
        verifier=verifier or FakeVerifier(),
        **kwargs,
    )


def _prompt_for(worker: ArtifactWorker, phase: str) -> str:
    return next(c.prompt for c in worker.calls if f"## Phase: {phase}\n" in c.prompt)


def test_repo_configuration_is_valid(project):
    assert not project.errors, [str(i) for i in project.errors]
    assert {"standard", "quick_fix", "research_only"} <= set(project.workflows)
    assert "producer" in project.personas


def test_quick_fix_runs_phases_then_waits_at_gate(project, git_repo):
    worker = ArtifactWorker()
    engine = _engine(project, git_repo, worker)

    state = engine.start("Fix the jump bug", workflow_id="quick_fix", workflow_run_id="qf1")

    assert state.status is WorkflowStatus.AWAITING_APPROVAL
    assert [r.status for r in state.phases] == [PhaseStatus.APPROVED, PhaseStatus.APPROVED, PhaseStatus.DONE]
    assert state.pending_gate().gate_id == "quick-fix-review"
    assert len(worker.calls) == 3
    for record in state.phases:
        assert (git_repo / record.artifact).is_file()
    # Later phases are pointed at earlier artifacts instead of chat history.
    assert state.phases[0].artifact in _prompt_for(worker, "implement")

    with pytest.raises(WorkflowError, match="awaiting approval"):
        engine.resume("qf1")

    engine.approve("qf1", "quick-fix-review", note="looks right")
    done = engine.resume("qf1")
    assert done.status is WorkflowStatus.DONE
    assert len(worker.calls) == 3


def test_prompt_puts_constitution_before_task_and_enforces_phase_skills(project, git_repo):
    worker = ArtifactWorker()
    _engine(project, git_repo, worker).start("Fix it", workflow_id="quick_fix", workflow_run_id="qf2")
    prompt = _prompt_for(worker, "implement")

    assert prompt.index("Primary constitution") < prompt.index("TASK:\nFix it")
    assert "## Persona: Gameplay Engineer" in prompt
    enforced = prompt[prompt.index("## Enforced skills"):prompt.index("## Other skills")]
    assert "### security_review" in enforced and "### test_strategy" in enforced
    assert "Engineering Moral Gate" in prompt


def test_reject_reruns_phase_with_feedback(project, git_repo):
    worker = ArtifactWorker()
    engine = _engine(project, git_repo, worker)
    engine.start("Fix it", workflow_id="quick_fix", workflow_run_id="qf3")

    with pytest.raises(WorkflowError, match="requires a note"):
        engine.reject("qf3", note=" ")
    engine.reject("qf3", note="Add a regression test for double jump")
    state = engine.resume("qf3")

    assert state.status is WorkflowStatus.AWAITING_APPROVAL
    verify = state.record("verify")
    assert verify.attempts == 2
    assert "Add a regression test for double jump" in worker.calls[-1].prompt
    assert [g.status.value for g in state.gates] == ["REJECTED", "PENDING"]


def test_missing_artifact_is_vetoed_even_if_verifier_says_met(project, git_repo):
    worker = ArtifactWorker(write=False)
    engine = _engine(project, git_repo, worker, verifier=FakeVerifier([GateResult(Verdict.MET, "looks done")]))

    state = engine.start("Fix it", workflow_id="quick_fix", workflow_run_id="qf4")

    assert state.status is WorkflowStatus.NEEDS_HUMAN
    assert state.phase_index == 0
    assert state.phases[0].status is PhaseStatus.NEEDS_HUMAN

    # A human fixes the cause; resume starts a fresh attempt of the same phase.
    engine.worker = ArtifactWorker()
    state = engine.resume("qf4")
    assert state.status is WorkflowStatus.AWAITING_APPROVAL
    assert state.phases[0].attempts == 2


def test_project_checks_only_run_in_flagged_phases(project, git_repo):
    worker = ArtifactWorker()
    failing = CheckSpec("tests", (sys.executable, "-c", "raise SystemExit(1)"))
    engine = _engine(project, git_repo, worker, checks=[failing], limits=EngineLimits(max_stuck_iterations=1))

    state = engine.start("Fix it", workflow_id="quick_fix", workflow_run_id="qf5")

    # assess has no run_checks, so it passes; implement runs the failing check.
    assert state.phases[0].status is PhaseStatus.APPROVED
    assert state.phases[1].status is PhaseStatus.NEEDS_HUMAN
    assert state.status is WorkflowStatus.NEEDS_HUMAN


def test_crash_mid_phase_resumes_same_operator_run(project, git_repo):
    engine = _engine(project, git_repo, ArtifactWorker(explode_on_call=2))
    with pytest.raises(KeyboardInterrupt):
        engine.start("Fix it", workflow_id="quick_fix", workflow_run_id="qf6")

    crashed = engine.status("qf6")
    assert crashed.status is WorkflowStatus.RUNNING
    assert crashed.phases[1].status is PhaseStatus.RUNNING
    run_id = crashed.phases[1].run_id

    recovered = _engine(project, git_repo, ArtifactWorker()).resume("qf6")
    assert recovered.status is WorkflowStatus.AWAITING_APPROVAL
    assert recovered.phases[1].run_id == run_id
    assert recovered.phases[1].attempts == 1


def test_workflow_budget_stops_before_next_phase(project, git_repo):
    worker = ArtifactWorker(cost=0.6)
    engine = _engine(project, git_repo, worker, limits=EngineLimits(max_cost_usd=0.5))

    state = engine.start("Fix it", workflow_id="quick_fix", workflow_run_id="qf7")

    assert state.status in (WorkflowStatus.NEEDS_HUMAN, WorkflowStatus.ERROR)
    assert len(worker.calls) == 1
    assert state.total_cost_usd == pytest.approx(0.6)


def test_standard_workflow_lead_persona_consults_others(project, git_repo):
    worker = ArtifactWorker()
    engine = _engine(project, git_repo, worker)
    state = engine.start(
        "Add a dash powerup",
        workflow_id="standard",
        personas=["producer", "gameplay_engineer", "qa_engineer"],
        workflow_run_id="std1",
    )
    assert state.pending_gate().gate_id == "intake-confirmation"
    engine.approve("std1")
    state = engine.resume("std1")
    assert state.pending_gate().gate_id == "plan-approval"

    research = _prompt_for(worker, "research")
    assert "## Persona: Producer" in research
    assert "## Consulted perspectives" in research and "QA Engineer" in research
    assert "research_tracks" in research


def test_events_are_logged(project, git_repo):
    _engine(project, git_repo).start("Fix it", workflow_id="quick_fix", workflow_run_id="qf8")
    log = git_repo / ".slipstream" / "workflows" / "qf8" / "events.jsonl"
    events = [json.loads(line)["event"] for line in log.read_text(encoding="utf-8").splitlines()]
    assert events[0] == "workflow_started"
    assert "gate_requested" in events


def test_unknown_workflow_and_persona_are_rejected(project, git_repo):
    engine = _engine(project, git_repo)
    with pytest.raises(WorkflowError, match="unknown workflow"):
        engine.start("x", workflow_id="nope")
    with pytest.raises(WorkflowError, match="unknown persona"):
        engine.start("x", workflow_id="quick_fix", personas=["wizard"])


def test_rejected_artifact_cannot_pass_unchanged(project, git_repo):
    worker = ArtifactWorker()
    engine = _engine(project, git_repo, worker, limits=EngineLimits(max_stuck_iterations=1))
    engine.start("Fix it", workflow_id="quick_fix", workflow_run_id="qf9")
    engine.reject("qf9", note="Cover the moving-platform case")

    # The worker now does nothing; the old artifact must not satisfy the phase.
    engine.worker = ArtifactWorker(write=False)
    state = engine.resume("qf9")

    assert state.status is WorkflowStatus.NEEDS_HUMAN
    verify = state.record("verify")
    artifact_dir = git_repo / ".slipstream" / "workflows" / "qf9" / "artifacts"
    assert not (git_repo / verify.artifact).exists()
    assert list(artifact_dir.glob("*_verify_*.attempt1.md"))
    prompt = engine.worker.calls[0].prompt
    assert "Reviewer feedback is addressed: Cover the moving-platform case" in prompt
    assert ".attempt1.md" in prompt


def test_second_driver_is_locked_out(project, git_repo):
    engine = _engine(project, git_repo)
    engine.start("Fix it", workflow_id="quick_fix", workflow_run_id="qf10")
    lock = git_repo / ".slipstream" / "workflows" / "qf10" / "lock"
    lock.write_text("{}", encoding="utf-8")  # another process holds the run

    with pytest.raises(WorkflowError, match="in use by another process"):
        engine.approve("qf10")
    lock.unlink()
    engine.approve("qf10")
    assert not lock.exists()


def test_resume_persists_launch_overrides(project, git_repo):
    engine = _engine(project, git_repo, ArtifactWorker(write=False), limits=EngineLimits(max_stuck_iterations=1))
    engine.start("Fix it", workflow_id="quick_fix", workflow_run_id="qf11", launch={"max_cost_usd": 10})
    engine.worker = ArtifactWorker()
    engine.resume("qf11", launch={"max_cost_usd": 2})
    assert engine.status("qf11").launch == {"max_cost_usd": 2}
