from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._process import resolve_command
from .base import (
    AgentRequest,
    AgentResult,
    BackendCapabilities,
    BackendPolicy,
    BackendProtocolError,
    BackendTimeout,
    BackendUnavailable,
)


@dataclass
class ClaudeCodeConfig:
    executable: str = "claude"
    model: str | None = None
    extra_args: tuple[str, ...] = ()
    permission_mode: str | None = None
    dangerously_skip_permissions: bool = False
    estimated_max_call_cost_usd: float | None = None
    env: dict[str, str] | None = None


class ClaudeCodeBackend:
    """Claude Code CLI adapter.

    Provider-specific command construction and JSON parsing live here, never in
    the operator. Unknown usage fields remain None rather than fabricated zero.
    """

    def __init__(self, config: ClaudeCodeConfig | None = None):
        self.config = config or ClaudeCodeConfig()
        self._active_process: subprocess.Popen[str] | None = None

    @property
    def name(self) -> str:
        return "claude-code"

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            sessions=True,
            tool_use=True,
            filesystem=True,
            shell=True,
            structured_output=True,
            cost_reporting=True,
            token_reporting=True,
            streaming=False,
            abort=True,
        )

    @property
    def policy(self) -> BackendPolicy:
        return BackendPolicy(self.config.estimated_max_call_cost_usd)

    def _command(self, request: AgentRequest) -> list[str]:
        # The prompt goes on stdin: Windows caps command lines at ~32K chars.
        cmd = [*resolve_command(self.config.executable), "-p", "--output-format", "json"]
        model = request.model or self.config.model
        if model:
            cmd += ["--model", model]
        if request.session_id:
            cmd += ["--resume", request.session_id]
        if request.max_turns is not None:
            cmd += ["--max-turns", str(request.max_turns)]
        if request.allowed_tools:
            cmd += ["--allowedTools", ",".join(request.allowed_tools)]
        if request.metadata.get("read_only"):
            cmd += ["--disallowedTools", "Write,Edit,NotebookEdit,Bash"]
        if self.config.permission_mode:
            cmd += ["--permission-mode", self.config.permission_mode]
        if self.config.dangerously_skip_permissions:
            cmd += ["--dangerously-skip-permissions"]
        cmd.extend(self.config.extra_args)
        return cmd

    @staticmethod
    def _number(data: dict[str, Any], *keys: str) -> int | float | None:
        cur: Any = data
        for key in keys:
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
        return cur if isinstance(cur, (int, float)) else None

    def run(self, request: AgentRequest) -> AgentResult:
        cmd = self._command(request)
        env = os.environ.copy()
        if self.config.env:
            env.update(self.config.env)
        try:
            self._active_process = subprocess.Popen(
                cmd,
                cwd=Path(request.workspace),
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            try:
                stdout_raw, stderr_raw = self._active_process.communicate(request.prompt, timeout=request.timeout_sec)
            except subprocess.TimeoutExpired as exc:
                self._active_process.kill()
                self._active_process.communicate()
                raise BackendTimeout(f"Claude Code timed out after {request.timeout_sec}s") from exc
            returncode = self._active_process.returncode or 0
        except FileNotFoundError as exc:
            raise BackendUnavailable(f"Claude Code executable not found: {self.config.executable}") from exc
        finally:
            self._active_process = None

        stdout = stdout_raw.strip()
        stderr = stderr_raw.strip()
        if not stdout:
            return AgentResult(
                text="",
                is_error=returncode != 0,
                stderr=stderr,
                raw={"returncode": returncode},
            )

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            if returncode != 0:
                return AgentResult(text=stdout, is_error=True, stderr=stderr, raw=stdout)
            raise BackendProtocolError("Claude Code returned invalid JSON") from exc

        text = payload.get("result") or payload.get("text") or ""
        session_id = payload.get("session_id") or payload.get("sessionId")
        cost = payload.get("total_cost_usd")
        if not isinstance(cost, (int, float)):
            cost = payload.get("cost_usd")
        if not isinstance(cost, (int, float)):
            cost = None

        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        if not isinstance(input_tokens, int):
            input_tokens = None
        if not isinstance(output_tokens, int):
            output_tokens = None

        turns = payload.get("num_turns") or payload.get("turns")
        if not isinstance(turns, int):
            turns = None

        is_error = returncode != 0 or bool(payload.get("is_error", False))
        return AgentResult(
            text=str(text),
            session_id=str(session_id) if session_id else None,
            is_error=is_error,
            cost_usd=float(cost) if cost is not None else None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            turns=turns,
            raw=payload,
            stderr=stderr,
        )

    def abort(self) -> None:
        if self._active_process and self._active_process.poll() is None:
            self._active_process.terminate()

    def close(self) -> None:
        self.abort()
