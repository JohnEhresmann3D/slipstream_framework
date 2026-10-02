from __future__ import annotations

import sys
from pathlib import Path

from slipstream.loop.backends.base import AgentResult
from slipstream.loop.evidence import CheckSpec, EvidenceCollector
from slipstream.loop.guardrails import GuardrailConfig
from slipstream.loop.operator import Operator
from slipstream.loop.state import RunStatus
from slipstream.loop.verification import GateResult, Verdict
from tests.fakes.fake_backend import FakeBackend, ScriptedStep
from tests.fakes.fake_verifier import FakeVerifier


def write_feature(workspace: Path, call: int) -> None:
    (workspace / "feature.txt").write_text(f"iteration {call}\n", encoding="utf-8")


def test_happy_path(git_repo):
    worker = FakeBackend([ScriptedStep(AgentResult(text="implemented", cost_usd=0.1), write_feature)], reserve=0.2)
    verifier = FakeVerifier([GateResult(Verdict.MET, "criteria met")])
    collector = EvidenceCollector(
        checks=[CheckSpec("feature", (sys.executable, "-c", "from pathlib import Path; assert Path('feature.txt').exists()"))]
    )
    op = Operator(git_repo, worker, verifier, collector, GuardrailConfig(max_cost_usd=1.0))
    result = op.run("create feature", ["feature.txt exists"])
    assert result.status is RunStatus.DONE
    assert result.iterations == 1
    assert result.total_cost_usd == 0.1
    assert len(worker.calls) == 1
    assert len(verifier.calls) == 1


def test_false_worker_claim_cannot_earn_met(git_repo):
    worker = FakeBackend([ScriptedStep(AgentResult(text="all tests pass"))])
    verifier = FakeVerifier([GateResult(Verdict.MET, "worker says done")])
    collector = EvidenceCollector(
        checks=[CheckSpec("tests", (sys.executable, "-c", "raise SystemExit(1)"))]
    )
    op = Operator(
        git_repo,
        worker,
        verifier,
        collector,
        GuardrailConfig(max_iterations=1, max_stuck_iterations=2),
    )
    result = op.run("fix tests", ["tests pass"])
    assert result.status is not RunStatus.DONE
    assert result.last_gate is not None
    assert result.last_gate.verdict is Verdict.PROGRESSING
    assert "required checks failed" in result.last_gate.reason.lower()


def test_no_progress_uses_evidence_not_changing_prose(git_repo):
    worker = FakeBackend(
        [
            ScriptedStep(AgentResult(text="attempt one")),
            ScriptedStep(AgentResult(text="completely different explanation")),
            ScriptedStep(AgentResult(text="yet another narrative")),
        ]
    )
    verifier = FakeVerifier([GateResult(Verdict.PROGRESSING, "keep going", ["actual change needed"])])
    collector = EvidenceCollector()
    op = Operator(
        git_repo,
        worker,
        verifier,
        collector,
        GuardrailConfig(max_iterations=5, max_stuck_iterations=2),
    )
    result = op.run("change repository", ["repository changes"])
    assert result.status is RunStatus.NEEDS_HUMAN
    assert result.reason == "evidence_based_no_progress_limit"
    assert len(worker.calls) == 3


def test_real_progress_with_similar_prose_continues(git_repo):
    worker = FakeBackend(
        [
            ScriptedStep(AgentResult(text="working"), write_feature),
            ScriptedStep(AgentResult(text="working"), write_feature),
        ]
    )
    verifier = FakeVerifier(
        [
            GateResult(Verdict.PROGRESSING, "one more change", ["finish"]),
            GateResult(Verdict.MET, "done"),
        ]
    )
    op = Operator(git_repo, worker, verifier, EvidenceCollector(), GuardrailConfig(max_stuck_iterations=1))
    result = op.run("iterate", ["finish"])
    assert result.status is RunStatus.DONE
    assert len(worker.calls) == 2


def test_bounded_budget_stops_before_second_worker_call(git_repo):
    worker = FakeBackend(
        [
            ScriptedStep(AgentResult(text="first", cost_usd=0.5)),
            ScriptedStep(AgentResult(text="second", cost_usd=0.5)),
        ],
        reserve=0.6,
    )
    verifier = FakeVerifier([GateResult(Verdict.PROGRESSING, "continue", ["more"])])
    op = Operator(
        git_repo,
        worker,
        verifier,
        EvidenceCollector(),
        GuardrailConfig(max_cost_usd=1.0, max_iterations=4, max_stuck_iterations=4),
    )
    result = op.run("task", ["more"])
    assert result.status is RunStatus.NEEDS_HUMAN
    assert result.reason == "insufficient_remaining_budget_for_bounded_call"
    assert result.total_cost_usd == 0.5
    assert len(worker.calls) == 1


def test_backend_without_cost_reporting_keeps_unknown_budget_status(git_repo):
    worker = FakeBackend(
        [ScriptedStep(AgentResult(text="done", cost_usd=None), write_feature)],
        reserve=None,
        cost_reporting=False,
    )
    verifier = FakeVerifier([GateResult(Verdict.MET, "done")])
    op = Operator(
        git_repo,
        worker,
        verifier,
        EvidenceCollector(),
        GuardrailConfig(max_cost_usd=1.0),
    )
    result = op.run("task", ["done"])
    assert result.status is RunStatus.DONE
    assert result.total_cost_usd == 0.0
    assert result.budget_status == "UNKNOWN"


def test_verifier_reservation_is_checked_before_grader_call(git_repo):
    from slipstream.loop.verification import BackendVerifier

    worker = FakeBackend(
        [ScriptedStep(AgentResult(text="worker complete", cost_usd=0.5), write_feature)],
        reserve=0.5,
    )
    verifier_backend = FakeBackend(
        [ScriptedStep(AgentResult(text='{"verdict":"MET","reason":"done","unmet_criteria":[]}', cost_usd=0.4))],
        reserve=0.6,
    )
    op = Operator(
        git_repo,
        worker,
        BackendVerifier(verifier_backend),
        EvidenceCollector(),
        GuardrailConfig(max_cost_usd=1.0),
    )
    result = op.run("task", ["done"])
    assert result.status is RunStatus.NEEDS_HUMAN
    assert result.reason == "verifier_insufficient_remaining_budget_for_bounded_call"
    assert result.total_cost_usd == 0.5
    assert len(verifier_backend.calls) == 0


def test_required_capability_is_validated_before_worker(git_repo):
    worker = FakeBackend([ScriptedStep(AgentResult(text="should not run"))])
    # Override by using a backend that does not advertise shell.
    class NoShell(FakeBackend):
        @property
        def capabilities(self):
            caps = super().capabilities
            from slipstream.loop.backends.base import BackendCapabilities
            return BackendCapabilities(**{**caps.__dict__, "shell": False})

    worker = NoShell([ScriptedStep(AgentResult(text="should not run"))])
    op = Operator(
        git_repo,
        worker,
        FakeVerifier(),
        EvidenceCollector(),
        required_worker_capabilities={"shell"},
    )
    result = op.run("task", ["done"])
    assert result.status is RunStatus.NEEDS_HUMAN
    assert result.reason == "missing_worker_capability:shell"
    assert len(worker.calls) == 0


def test_worker_backend_error_limit_surfaces_as_error(git_repo):
    from slipstream.loop.backends.base import BackendUnavailable

    class FailingBackend(FakeBackend):
        def run(self, request):
            self.calls.append(request)
            raise BackendUnavailable("worker offline")

    worker = FailingBackend()
    op = Operator(
        git_repo,
        worker,
        FakeVerifier(),
        EvidenceCollector(),
        GuardrailConfig(max_iterations=5, max_consecutive_backend_errors=2),
    )
    result = op.run("task", ["done"])
    assert result.status is RunStatus.ERROR
    assert result.reason.startswith("worker_backend_error_limit:")
    assert len(worker.calls) == 2


def test_reported_worker_cost_breach_stops_as_error(git_repo):
    worker = FakeBackend(
        [ScriptedStep(AgentResult(text="expensive", cost_usd=1.2), write_feature)],
        reserve=0.5,
    )
    op = Operator(
        git_repo,
        worker,
        FakeVerifier([GateResult(Verdict.MET, "done")]),
        EvidenceCollector(),
        GuardrailConfig(max_cost_usd=1.0),
    )
    result = op.run("task", ["done"])
    assert result.status is RunStatus.ERROR
    assert result.reason == "monetary_budget_breached_by_worker_call"
    assert result.total_cost_usd == 1.2
