"""Compatibility shim for the pre-vendor-neutral module name.

New code should import `ClaudeCodeBackend` from `slipstream.loop.backends.claude_code`.
"""

from pathlib import Path

from .backends.base import AgentRequest
from .backends.claude_code import ClaudeCodeBackend, ClaudeCodeConfig


class ClaudeCLI(ClaudeCodeBackend):
    """Legacy facade preserving `run(prompt, resume=...)` for incremental migration."""

    def run(self, request, resume=None, workspace=None):  # type: ignore[override]
        if isinstance(request, AgentRequest):
            return super().run(request)
        result = super().run(
            AgentRequest(
                prompt=str(request),
                workspace=Path(workspace or "."),
                session_id=resume,
            )
        )
        return result


__all__ = ["ClaudeCLI", "ClaudeCodeBackend", "ClaudeCodeConfig"]
