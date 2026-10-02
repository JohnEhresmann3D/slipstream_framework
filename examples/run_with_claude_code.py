from pathlib import Path

from slipstream.loop.backends.claude_code import ClaudeCodeBackend, ClaudeCodeConfig
from slipstream.loop.evidence import CheckSpec, EvidenceCollector
from slipstream.loop.guardrails import GuardrailConfig
from slipstream.loop.operator import Operator
from slipstream.loop.verification import BackendVerifier

root = Path.cwd()
worker = ClaudeCodeBackend(ClaudeCodeConfig(estimated_max_call_cost_usd=1.00))
verifier_backend = ClaudeCodeBackend(ClaudeCodeConfig(estimated_max_call_cost_usd=0.25))

operator = Operator(
    root=root,
    worker=worker,
    verifier=BackendVerifier(verifier_backend),
    evidence_collector=EvidenceCollector(
        checks=[CheckSpec("pytest", ("python", "-m", "pytest", "-q"), timeout_sec=300)]
    ),
    guardrails=GuardrailConfig(max_iterations=6, max_cost_usd=8.00),
    required_worker_capabilities={"filesystem", "shell"},
)

result = operator.run(
    "Implement the requested feature.",
    ["Tests pass", "No provider-specific imports exist in the operator"],
)
print(result)
