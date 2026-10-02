from slipstream.loop.guardrails import BudgetStatus, GuardrailConfig, Guardrails
from tests.fakes.fake_backend import FakeBackend


def test_bounded_call_cannot_start_when_reserve_exceeds_remaining():
    guardrails = Guardrails(GuardrailConfig(max_cost_usd=1.0))
    backend = FakeBackend(reserve=0.6)
    preflight = guardrails.preflight(iteration=1, total_cost_usd=0.5, worker=backend)
    assert not preflight.allowed
    assert preflight.reason == "insufficient_remaining_budget_for_bounded_call"
    assert preflight.budget_status is BudgetStatus.EXHAUSTED


def test_unknown_cost_is_marked_unknown_not_zero():
    guardrails = Guardrails(GuardrailConfig(max_cost_usd=1.0))
    backend = FakeBackend(reserve=None, cost_reporting=False)
    preflight = guardrails.preflight(iteration=0, total_cost_usd=0.0, worker=backend)
    assert preflight.allowed
    assert preflight.budget_status is BudgetStatus.UNKNOWN
