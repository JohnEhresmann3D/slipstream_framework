from pathlib import Path

from slipstream.loop.backends.base import AgentResult
from slipstream.loop.evidence import CheckResult, EvidenceBundle
from slipstream.loop.verification import BackendVerifier, Verdict
from tests.fakes.fake_backend import FakeBackend, ScriptedStep


def test_backend_verifier_deterministic_failure_vetoes_met(tmp_path):
    backend = FakeBackend([
        ScriptedStep(AgentResult(text='{"verdict":"MET","reason":"looks good","unmet_criteria":[]}'))
    ])
    verifier = BackendVerifier(backend)
    evidence = EvidenceBundle(
        workspace_revision=None,
        diff_summary="",
        changed_files=[],
        checks=[CheckResult("tests", ["pytest"], False, 1, "", "failed", 0.1, True)],
        artifacts=[],
        facts={},
    )
    gate = verifier.evaluate("goal", ["tests pass"], evidence, AgentResult(text="tests pass"), None, Path(tmp_path))
    assert gate.verdict is Verdict.PROGRESSING
    assert "vetoed met" in gate.reason.lower()


def test_backend_verifier_uses_isolated_workspace_snapshot(tmp_path):
    source = Path(tmp_path) / "source"
    source.mkdir()
    target = source / "important.txt"
    target.write_text("original", encoding="utf-8")

    def mutate_verifier_workspace(workspace, call):
        (workspace / "important.txt").write_text("mutated by verifier", encoding="utf-8")

    backend = FakeBackend([
        ScriptedStep(
            AgentResult(text='{"verdict":"MET","reason":"done","unmet_criteria":[]}'),
            mutate_verifier_workspace,
        )
    ])
    verifier = BackendVerifier(backend)
    evidence = EvidenceBundle(None, "", [], [], [], {})
    gate = verifier.evaluate("goal", ["done"], evidence, AgentResult(text="done"), None, source)
    assert gate.verdict is Verdict.MET
    assert target.read_text(encoding="utf-8") == "original"
    assert backend.calls[0].workspace != source
