from __future__ import annotations

import json
import os
from pathlib import Path

from slipstream.loop.backends.base import AgentRequest
from slipstream.loop.backends.claude_code import ClaudeCodeBackend, ClaudeCodeConfig


def _fake_claude(tmp_path: Path) -> Path:
    script = tmp_path / "fake_claude.py"
    script.write_text(
        """#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
session = None
if '--resume' in args:
    session = args[args.index('--resume') + 1]
print(json.dumps({
    'result': 'ok',
    'session_id': session or 'new-session',
    'usage': {'input_tokens': 11, 'output_tokens': 7},
    'num_turns': 2
}))
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_claude_adapter_parses_and_resumes_without_fabricating_cost(tmp_path):
    exe = _fake_claude(tmp_path)
    backend = ClaudeCodeBackend(ClaudeCodeConfig(executable=str(exe)))
    result = backend.run(
        AgentRequest(
            prompt="work",
            workspace=tmp_path,
            session_id="abc",
            allowed_tools=["Read", "Bash(git diff:*)"],
            max_turns=3,
        )
    )
    assert result.text == "ok"
    assert result.session_id == "abc"
    assert result.input_tokens == 11
    assert result.output_tokens == 7
    assert result.cost_usd is None


def test_claude_timeout_maps_to_backend_timeout(tmp_path):
    from slipstream.loop.backends.base import BackendTimeout

    script = tmp_path / "slow_claude.py"
    script.write_text(
        """#!/usr/bin/env python3
import time
time.sleep(2)
print('{}')
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    backend = ClaudeCodeBackend(ClaudeCodeConfig(executable=str(script)))
    try:
        backend.run(AgentRequest(prompt="wait", workspace=tmp_path, timeout_sec=1))
    except BackendTimeout:
        pass
    else:
        raise AssertionError("Expected BackendTimeout")
