from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class BackendCapabilities:
    sessions: bool = False
    tool_use: bool = False
    filesystem: bool = False
    shell: bool = False
    structured_output: bool = False
    cost_reporting: bool = False
    token_reporting: bool = False
    streaming: bool = False
    abort: bool = False


@dataclass(frozen=True)
class BackendPolicy:
    """Operator-facing policy for a concrete backend.

    `estimated_max_call_cost_usd` is a reservation used for hard-budget
    preflight when the backend cannot accept a native per-call cost ceiling.
    """

    estimated_max_call_cost_usd: float | None = None


@dataclass
class AgentRequest:
    prompt: str
    workspace: Path
    session_id: str | None = None
    allowed_tools: list[str] | None = None
    model: str | None = None
    max_turns: int | None = None
    timeout_sec: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    text: str
    session_id: str | None = None
    is_error: bool = False
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    turns: int | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    raw: Any = None
    stderr: str = ""


@runtime_checkable
class AgentBackend(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> BackendCapabilities: ...

    @property
    def policy(self) -> BackendPolicy: ...

    def run(self, request: AgentRequest) -> AgentResult: ...

    def abort(self) -> None: ...

    def close(self) -> None: ...


class BackendError(RuntimeError):
    pass


class BackendUnavailable(BackendError):
    pass


class BackendTimeout(BackendError):
    pass


class BackendProtocolError(BackendError):
    pass


class BackendAuthenticationError(BackendError):
    pass


class BackendCapabilityError(BackendError):
    pass
