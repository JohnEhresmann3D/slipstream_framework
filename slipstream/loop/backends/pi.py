from __future__ import annotations

import json
import os
import subprocess
import threading
import uuid
from dataclasses import dataclass
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
class PiConfig:
    executable: str = "pi"
    provider: str | None = None
    model: str | None = None
    extra_args: tuple[str, ...] = ()
    estimated_max_call_cost_usd: float | None = None
    env: dict[str, str] | None = None


class PiBackend:
    """pi.dev RPC adapter using `pi --mode rpc` JSONL over stdin/stdout.

    The resident process and Pi session mechanics are fully hidden behind the
    AgentBackend contract. A different requested workspace or session causes a
    controlled process restart.
    """

    def __init__(self, config: PiConfig | None = None):
        self.config = config or PiConfig()
        self._proc: subprocess.Popen[str] | None = None
        self._workspace: Path | None = None
        # AgentRequest.session_id is intentionally an opaque continuation token.
        # For Pi we use the durable sessionFile path, not Pi's display/session UUID,
        # because RPC restores sessions with switch_session(sessionPath=...).
        self._session_token: str | None = None
        self._model: str | None = None
        self._lock = threading.RLock()

    @property
    def name(self) -> str:
        return "pi"

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            sessions=True,
            tool_use=True,
            filesystem=True,
            shell=True,
            structured_output=False,
            cost_reporting=True,
            token_reporting=True,
            streaming=True,
            abort=True,
        )

    @property
    def policy(self) -> BackendPolicy:
        return BackendPolicy(self.config.estimated_max_call_cost_usd)

    def _start(self, workspace: Path, session_token: str | None, model: str | None) -> None:
        self.close()
        cmd = [*resolve_command(self.config.executable), "--mode", "rpc"]
        if self.config.provider:
            cmd += ["--provider", self.config.provider]
        selected_model = model or self.config.model
        if selected_model:
            cmd += ["--model", selected_model]
        cmd.extend(self.config.extra_args)
        env = os.environ.copy()
        if self.config.env:
            env.update(self.config.env)
        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=workspace,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
        except FileNotFoundError as exc:
            raise BackendUnavailable(f"Pi executable not found: {self.config.executable}") from exc
        self._workspace = workspace
        self._model = selected_model
        self._session_token = None
        if session_token:
            response = self._command({"type": "switch_session", "sessionPath": session_token})
            data = response.get("data") if isinstance(response.get("data"), dict) else {}
            if data.get("cancelled") is True:
                self.close()
                raise BackendProtocolError(f"Pi session switch was cancelled: {session_token}")
            self._session_token = session_token

    def _ensure_process(self, request: AgentRequest) -> None:
        workspace = Path(request.workspace).resolve()
        selected_model = request.model or self.config.model
        needs_restart = (
            self._proc is None
            or self._proc.poll() is not None
            or self._workspace != workspace
            or self._model != selected_model
            or (request.session_id is None and self._session_token is not None)
            or (request.session_id is not None and self._session_token not in (None, request.session_id))
        )
        if needs_restart:
            self._start(workspace, request.session_id, request.model)

    def _send(self, payload: dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            raise BackendProtocolError("Pi RPC process is not running")
        self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()

    def _read_json(self) -> dict[str, Any]:
        if not self._proc or not self._proc.stdout:
            raise BackendProtocolError("Pi RPC process is not running")
        line = self._proc.stdout.readline()
        if line == "":
            stderr = ""
            if self._proc.stderr:
                stderr = self._proc.stderr.read()
            raise BackendProtocolError(f"Pi RPC process ended unexpectedly: {stderr.strip()}")
        try:
            return json.loads(line.rstrip("\r\n"))
        except json.JSONDecodeError as exc:
            raise BackendProtocolError(f"Invalid Pi RPC JSONL record: {line[:200]!r}") from exc

    def _command(self, command: dict[str, Any]) -> dict[str, Any]:
        request_id = command.setdefault("id", uuid.uuid4().hex)
        self._send(command)
        while True:
            event = self._read_json()
            if event.get("type") == "response" and event.get("id") == request_id:
                if event.get("success") is False:
                    raise BackendProtocolError(f"Pi RPC command failed: {event}")
                return event

    @staticmethod
    def _text_from_message(message: Any) -> str:
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)

    def run(self, request: AgentRequest) -> AgentResult:
        # RPC itself is line-driven. Timeout is enforced conservatively by
        # aborting from a timer so the adapter remains synchronous to callers.
        with self._lock:
            self._ensure_process(request)
            timer: threading.Timer | None = None
            timed_out = threading.Event()

            def _timeout() -> None:
                timed_out.set()
                proc = self._proc
                if proc is not None and proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass

            if request.timeout_sec:
                timer = threading.Timer(request.timeout_sec, _timeout)
                timer.daemon = True
                timer.start()

            events: list[dict[str, Any]] = []
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            baseline_stats: dict[str, Any] = {}
            try:
                try:
                    baseline_response = self._command({"type": "get_session_stats"})
                    baseline_stats = baseline_response.get("data") if isinstance(baseline_response.get("data"), dict) else {}
                except BackendProtocolError:
                    baseline_stats = {}

                self._send({"type": "prompt", "message": request.prompt})
                try:
                    while True:
                        event = self._read_json()
                        events.append(event)
                        if event.get("type") == "message_update":
                            delta = event.get("assistantMessageEvent")
                            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                                value = delta.get("delta")
                                if isinstance(value, str):
                                    text_parts.append(value)
                            elif isinstance(delta, dict) and delta.get("type") == "toolcall_end":
                                call = delta.get("toolCall")
                                if isinstance(call, dict):
                                    tool_calls.append(call)
                        elif event.get("type") == "message_end":
                            fallback = self._text_from_message(event.get("message"))
                            if fallback and not text_parts:
                                text_parts.append(fallback)
                        elif event.get("type") == "agent_settled":
                            break
                except BackendProtocolError as exc:
                    if timed_out.is_set():
                        raise BackendTimeout(f"Pi timed out after {request.timeout_sec}s") from exc
                    raise
                if timed_out.is_set():
                    raise BackendTimeout(f"Pi timed out after {request.timeout_sec}s")

                state_response = self._command({"type": "get_state"})
                stats_response = self._command({"type": "get_session_stats"})
                state = state_response.get("data") if isinstance(state_response.get("data"), dict) else {}
                stats = stats_response.get("data") if isinstance(stats_response.get("data"), dict) else {}
                session_file = state.get("sessionFile")
                self._session_token = session_file if isinstance(session_file, str) and session_file else None
                tokens = stats.get("tokens") if isinstance(stats.get("tokens"), dict) else {}
                baseline_tokens = baseline_stats.get("tokens") if isinstance(baseline_stats.get("tokens"), dict) else {}
                cost = stats.get("cost")
                baseline_cost = baseline_stats.get("cost")

                call_cost = None
                if isinstance(cost, (int, float)):
                    if isinstance(baseline_cost, (int, float)):
                        call_cost = max(0.0, float(cost) - float(baseline_cost))
                    else:
                        call_cost = float(cost)

                def _delta_token(key: str) -> int | None:
                    value = tokens.get(key)
                    baseline = baseline_tokens.get(key)
                    if not isinstance(value, int):
                        return None
                    if isinstance(baseline, int):
                        return max(0, value - baseline)
                    return value

                return AgentResult(
                    text="".join(text_parts),
                    session_id=self._session_token,
                    cost_usd=call_cost,
                    input_tokens=_delta_token("input"),
                    output_tokens=_delta_token("output"),
                    tool_calls=tool_calls,
                    events=events,
                    raw={"state": state, "stats": stats},
                )
            finally:
                if timer:
                    timer.cancel()

    def abort(self) -> None:
        # Do not acquire the run lock here: abort must remain callable from a
        # different thread while `run()` is blocked reading RPC output.
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                # Pi RPC supports asynchronous abort. The run loop will consume
                # its response/event stream. Fall back to process termination only
                # when stdin is unavailable.
                if proc.stdin:
                    proc.stdin.write(json.dumps({"type": "abort"}) + "\n")
                    proc.stdin.flush()
                else:
                    proc.terminate()
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._workspace = None
        self._session_token = None
        self._model = None
