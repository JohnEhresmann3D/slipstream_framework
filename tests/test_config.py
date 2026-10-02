from __future__ import annotations

import sys
from pathlib import Path

import pytest

from slipstream.config import ConfigError, find_project_root, load_project
from slipstream.loop.backends._process import resolve_command
from slipstream.loop.backends.base import AgentRequest
from slipstream.loop.backends.claude_code import ClaudeCodeBackend, ClaudeCodeConfig


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def broken_project(tmp_path: Path) -> Path:
    _write(tmp_path, "slipstream.yaml", "defaults:\n  workflow: wf\n  personas: [dev]\n")
    _write(tmp_path, "constitution/AI_Engineer_Constitution.md", "# Constitution\n")
    _write(tmp_path, "skills/core/planning.yaml", "name: planning\ndescription: Plan things\n")
    _write(
        tmp_path,
        "personas/dev.yaml",
        "name: Dev\nrole: Builds\nskills_required: [planning, telepathy]\nvoice: {focus: code}\n",
    )
    _write(
        tmp_path,
        "workflows/wf.yaml",
        """name: wf
description: Broken on purpose
phases:
  - name: build
    description: Build it
    agents: [dev, ghost]
    skills_enforced: [planning]
    output: thing
    hitl_gate: true
  - name: ship
    description: Ship it
    agents: [dev]
    output: shipped
transitions:
  build_to_ship:
    requires: [vibes_are_good]
""",
    )
    return tmp_path


def test_validation_reports_every_broken_reference(broken_project):
    with pytest.raises(ConfigError) as excinfo:
        load_project(broken_project)
    messages = "\n".join(str(i) for i in excinfo.value.issues)
    assert "unknown skill 'telepathy'" in messages
    assert "unknown agent persona 'ghost'" in messages
    assert "gate_id is missing" in messages
    assert "unknown requirement 'vibes_are_good'" in messages
    assert "role constitution not found" in messages  # warning, still reported


def test_non_strict_load_returns_issues(broken_project):
    project = load_project(broken_project, strict=False)
    assert project.errors
    assert "dev" in project.personas


def test_find_project_root_walks_up(broken_project):
    nested = broken_project / "a" / "b"
    nested.mkdir(parents=True)
    assert find_project_root(nested) == broken_project.resolve()


def test_resolve_command_runs_python_scripts_with_interpreter(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text("", encoding="utf-8")
    assert resolve_command(str(script)) == [sys.executable, str(script)]
    assert resolve_command("definitely-not-a-real-binary") == ["definitely-not-a-real-binary"]


def test_claude_prompt_goes_on_stdin_not_argv(tmp_path):
    script = tmp_path / "fake_claude.py"
    script.write_text(
        "import json, sys\n"
        "sys.stdin.reconfigure(encoding='utf-8')\n"
        "prompt = sys.stdin.read()\n"
        "print(json.dumps({'result': f'{len(prompt)}:{prompt in sys.argv}', 'session_id': 's'}))\n",
        encoding="utf-8",
    )
    backend = ClaudeCodeBackend(ClaudeCodeConfig(executable=str(script)))
    long_prompt = "x" * 40_000 + " é"  # past the Windows command-line limit, non-ASCII
    result = backend.run(AgentRequest(prompt=long_prompt, workspace=tmp_path))
    assert result.text == f"{len(long_prompt)}:False"
