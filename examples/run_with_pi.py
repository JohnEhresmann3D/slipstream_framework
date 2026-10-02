from pathlib import Path

from slipstream.loop.backends.pi import PiBackend, PiConfig
from slipstream.loop.evidence import CheckSpec, EvidenceCollector
from slipstream.loop.guardrails import GuardrailConfig
from slipstream.loop.operator import Operator
from slipstream.loop.verification import BackendVerifier
from slipstream.loop.workspaces import GitWorktreeWorkspaceManager

root = Path.cwd()
worker = PiBackend(PiConfig(provider="openai", model=None, estimated_max_call_cost_usd=1.00))
verifier_backend = PiBackend(PiConfig(provider="openai", model=None, estimated_max_call_cost_usd=0.25))

operator = Operator(
    root=root,
    worker=worker,
    verifier=BackendVerifier(verifier_backend),
    evidence_collector=EvidenceCollector(
        checks=[CheckSpec("pytest", ("python", "-m", "pytest", "-q"), timeout_sec=300)]
    ),
    guardrails=GuardrailConfig(max_iterations=6, max_cost_usd=8.00, max_stuck_iterations=2),
    workspace_manager=GitWorktreeWorkspaceManager(),
    required_worker_capabilities={"filesystem", "shell"},
)

try:
    result = operator.run(
        "Implement the requested feature without regressing existing behavior.",
        ["All tests pass", "Implementation follows repository architecture"],
    )
    print(result)
finally:
    worker.close()
    verifier_backend.close()
