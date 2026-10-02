from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .backends.base import AgentBackend


class BudgetStatus(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    ENFORCED = "ENFORCED"
    UNKNOWN = "UNKNOWN"
    EXHAUSTED = "EXHAUSTED"
    BREACHED = "BREACHED"


@dataclass(frozen=True)
class GuardrailConfig:
    max_iterations: int = 8
    max_cost_usd: float | None = None
    max_stuck_iterations: int = 2
    max_consecutive_backend_errors: int = 2
    per_call_timeout_sec: int = 900
    max_turns: int | None = None


@dataclass(frozen=True)
class PreflightResult:
    allowed: bool
    reason: str | None
    budget_status: BudgetStatus
    remaining_cost_usd: float | None


class Guardrails:
    def __init__(self, config: GuardrailConfig):
        self.config = config

    def cost_preflight(self, *, total_cost_usd: float, backend: AgentBackend) -> PreflightResult:
        cap = self.config.max_cost_usd
        if cap is None:
            return PreflightResult(True, None, BudgetStatus.NOT_CONFIGURED, None)

        remaining = cap - total_cost_usd
        if remaining <= 0:
            return PreflightResult(False, "monetary_budget_exhausted", BudgetStatus.EXHAUSTED, remaining)

        reserve = backend.policy.estimated_max_call_cost_usd
        if reserve is not None:
            if remaining < reserve:
                return PreflightResult(False, "insufficient_remaining_budget_for_bounded_call", BudgetStatus.EXHAUSTED, remaining)
            return PreflightResult(True, None, BudgetStatus.ENFORCED, remaining)

        # Without a bounded-call reservation, a monetary hard cap cannot be
        # guaranteed. We still account reported cost, but status is UNKNOWN.
        return PreflightResult(True, None, BudgetStatus.UNKNOWN, remaining)

    def preflight(self, *, iteration: int, total_cost_usd: float, worker: AgentBackend) -> PreflightResult:
        if iteration >= self.config.max_iterations:
            return PreflightResult(False, "max_iterations_reached", BudgetStatus.NOT_CONFIGURED, None)
        return self.cost_preflight(total_cost_usd=total_cost_usd, backend=worker)

    def should_stop_for_no_progress(self, no_progress_count: int) -> bool:
        return no_progress_count >= self.config.max_stuck_iterations

    def should_stop_for_backend_errors(self, consecutive_errors: int) -> bool:
        return consecutive_errors >= self.config.max_consecutive_backend_errors
