from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import AgentBackend
from .claude_code import ClaudeCodeBackend, ClaudeCodeConfig
from .openai import OpenAIBackend, OpenAIConfig
from .pi import PiBackend, PiConfig


@dataclass
class BackendConfig:
    kind: str
    options: dict[str, Any] = field(default_factory=dict)


def make_backend(config: BackendConfig) -> AgentBackend:
    kind = config.kind.lower().strip()
    if kind in {"claude", "claude-code", "claude_code"}:
        return ClaudeCodeBackend(ClaudeCodeConfig(**config.options))
    if kind in {"pi", "pi.dev", "pi-dev"}:
        return PiBackend(PiConfig(**config.options))
    if kind in {"openai", "codex"}:
        return OpenAIBackend(OpenAIConfig(**config.options))
    raise ValueError(f"Unknown backend kind: {config.kind}")
