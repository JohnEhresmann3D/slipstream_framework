from __future__ import annotations

from pathlib import Path

import pytest

from slipstream.loop.backends.base import AgentResult
from slipstream.loop.evidence import EvidenceCollector
from slipstream.loop.guardrails import GuardrailConfig
from slipstream.loop.operator import Operator
from slipstream.loop.state import RunStage, RunStatus, RunStore
from slipstream.loop.verification import GateResult, Verdict
from tests.fakes.fake_backend import FakeBackend, ScriptedStep
from tests.fakes.fake_verifier import FakeVerifier


class CrashCollector(EvidenceCollector):
    def collect(self, workspace, criteria=None):
        raise RuntimeError("simulated crash after worker checkpoint")


class CrashVerifier:
    def evaluate(self, *args, **kwargs):
        raise KeyboardInterrupt("simulated process death after evidence checkpoint")


def mutate(workspace: Path, call: int) -> None:
    (workspace / "done.txt").write_text("done\n", encoding="utf-8")


def test_resume_after_worker_checkpoint_does_not_rerun_worker(git_repo):
    worker = FakeBackend([ScriptedStep(AgentResult(text="implemented"), mutate)])
    run_id = "recover-worker"
    op = Operator(git_repo, worker, FakeVerifier(), CrashCollector(), GuardrailConfig(max_iterations=3))
    with pytest.raises(RuntimeError, match="simulated crash"):
        op.run("task", ["done"], run_id=run_id)

    store = RunStore(git_repo / ".slipstream" / "runs")
    state = store.load(run_id)
    assert state.stage is RunStage.WORKER_COMPLETE
    assert len(worker.calls) == 1

    resumed = Operator(git_repo, worker, FakeVerifier([GateResult(Verdict.MET, "done")]), EvidenceCollector())
    result = resumed.resume(run_id)
    assert result.status is RunStatus.DONE
    assert len(worker.calls) == 1


def test_resume_after_evidence_checkpoint_does_not_rerun_worker_or_evidence(git_repo):
    worker = FakeBackend([ScriptedStep(AgentResult(text="implemented"), mutate)])
    run_id = "recover-evidence"
    collector = EvidenceCollector()
    op = Operator(git_repo, worker, CrashVerifier(), collector, GuardrailConfig(max_iterations=3))
    with pytest.raises(KeyboardInterrupt):
        op.run("task", ["done"], run_id=run_id)

    store = RunStore(git_repo / ".slipstream" / "runs")
    state = store.load(run_id)
    assert state.stage is RunStage.EVIDENCE_COMPLETE
    assert len(worker.calls) == 1

    class ExplodingCollector(EvidenceCollector):
        def collect(self, workspace, criteria=None):
            raise AssertionError("evidence should be loaded, not recollected")

    resumed = Operator(
        git_repo,
        worker,
        FakeVerifier([GateResult(Verdict.MET, "done")]),
        ExplodingCollector(),
    )
    result = resumed.resume(run_id)
    assert result.status is RunStatus.DONE
    assert len(worker.calls) == 1
