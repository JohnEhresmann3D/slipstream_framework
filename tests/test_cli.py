from slipstream.loop.cli import build_parser


def test_resume_parser_does_not_require_goal_or_criterion():
    args = build_parser().parse_args(["--resume", "abc123"])
    assert args.resume == "abc123"
    assert args.goal is None
    assert args.criteria is None


# --- top-level `slipstream` CLI -------------------------------------------

import json
from pathlib import Path

from slipstream import cli
from slipstream.config import load_project
from slipstream.workflow import WorkflowEngine
from tests.fakes.fake_verifier import FakeVerifier
from tests.test_workflow import ArtifactWorker

REPO = Path(__file__).resolve().parents[1]


def test_validate_passes_on_repo(capsys):
    assert cli.main(["validate", "--project", str(REPO)]) == 0
    assert "0 errors" in capsys.readouterr().out


def test_prompt_preview_needs_no_backend(capsys):
    assert cli.main(["prompt", "--project", str(REPO), "--workflow", "quick_fix", "--phase", "implement"]) == 0
    assert "## Persona: Gameplay Engineer" in capsys.readouterr().out


def test_status_and_approve_work_without_backends(git_repo, capsys):
    engine = WorkflowEngine(load_project(REPO), git_repo, worker=ArtifactWorker(), verifier=FakeVerifier())
    engine.start("Fix it", workflow_id="quick_fix", workflow_run_id="cli1")
    location = ["--project", str(REPO), "--root", str(git_repo)]

    assert cli.main(["workflow", "status", *location]) == 0
    assert "cli1\tAWAITING_APPROVAL\tverify" in capsys.readouterr().out

    assert cli.main(["workflow", "approve", "cli1", *location, "--by", "tester"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "READY"

    assert cli.main(["workflow", "approve", "cli1", *location]) == 1
    assert "no gate awaiting approval" in capsys.readouterr().err
