from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import (
    AgentRequest,
    AgentResult,
    BackendCapabilities,
    BackendPolicy,
    BackendUnavailable,
    BackendCapabilityError,
)


@dataclass
class OpenAIConfig:
    model: str | None = None
    estimated_max_call_cost_usd: float | None = None
    client: Any = None


class OpenAIBackend:
    """Optional API-backed adapter.

    This adapter deliberately advertises no native filesystem/shell capability;
    those should be supplied by a separate tool host rather than leaked into
    the Slipstream operator.
    """

    def __init__(self, config: OpenAIConfig | None = None):
        self.config = config or OpenAIConfig()
        self._client = self.config.client

    @property
    def name(self) -> str:
        return "openai"

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            sessions=False,
            tool_use=False,
            filesystem=False,
            shell=False,
            structured_output=True,
            cost_reporting=False,
            token_reporting=True,
            streaming=False,
            abort=False,
        )

    @property
    def policy(self) -> BackendPolicy:
        return BackendPolicy(self.config.estimated_max_call_cost_usd)

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise BackendUnavailable("Install the optional 'openai' dependency to use OpenAIBackend") from exc
        self._client = OpenAI()
        return self._client

    def run(self, request: AgentRequest) -> AgentResult:
        client = self._get_client()
        model = request.model or self.config.model
        if not model:
            raise BackendCapabilityError("OpenAIBackend requires an explicit model in config or AgentRequest")
        response = client.responses.create(
            model=model,
            input=request.prompt,
        )
        usage = getattr(response, "usage", None)
        return AgentResult(
            text=getattr(response, "output_text", "") or "",
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
            raw=response,
        )

    def abort(self) -> None:
        return None

    def close(self) -> None:
        return None
