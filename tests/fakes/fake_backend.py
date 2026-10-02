from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from slipstream.loop.backends.base import (
    AgentRequest,
    AgentResult,
    BackendCapabilities,
    BackendPolicy,
)


@dataclass
class ScriptedStep:
    result: AgentResult
    mutate: Callable[[Path, int], None] | None = None


class FakeBackend:
    def __init__(
        self,
        steps: list[ScriptedStep] | None = None,
        *,
        name: str = "fake",
        reserve: float | None = None,
        cost_reporting: bool = True,
    ):
        self._steps = deque(steps or [])
        self._name = name
        self._reserve = reserve
        self._cost_reporting = cost_reporting
        self.calls: list[AgentRequest] = []
        self.closed = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            sessions=True,
            tool_use=True,
            filesystem=True,
            shell=True,
            structured_output=True,
            cost_reporting=self._cost_reporting,
            token_reporting=self._cost_reporting,
            abort=True,
        )

    @property
    def policy(self) -> BackendPolicy:
        return BackendPolicy(self._reserve)

    def run(self, request: AgentRequest) -> AgentResult:
        self.calls.append(request)
        if not self._steps:
            return AgentResult(text="no-op", session_id=request.session_id or "fake-session")
        step = self._steps.popleft()
        if step.mutate:
            step.mutate(Path(request.workspace), len(self.calls))
        if step.result.session_id is None:
            step.result.session_id = request.session_id or "fake-session"
        return step.result

    def abort(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True
