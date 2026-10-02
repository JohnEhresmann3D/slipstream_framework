from __future__ import annotations

import sys

from slipstream.loop.evidence import CheckSpec, EvidenceCollector


def test_collects_git_delta_and_checks(git_repo):
    (git_repo / "feature.txt").write_text("hello\n", encoding="utf-8")
    collector = EvidenceCollector(
        checks=[CheckSpec("pass", (sys.executable, "-c", "print('ok')"))],
        artifact_globs=["*.txt"],
    )
    evidence = collector.collect(git_repo, ["feature exists"])
    assert "feature.txt" in evidence.changed_files
    assert evidence.passed_checks == 1
    assert evidence.failed_checks == 0
    assert evidence.has_required_failure is False
    assert evidence.workspace_hash is not None
    assert any(str(p) == "feature.txt" for p in evidence.artifacts)


def test_required_failure_is_explicit(git_repo):
    collector = EvidenceCollector(
        checks=[CheckSpec("fails", (sys.executable, "-c", "raise SystemExit(3)"))]
    )
    evidence = collector.collect(git_repo, [])
    assert evidence.failed_checks == 1
    assert evidence.has_required_failure is True
