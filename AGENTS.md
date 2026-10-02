# Agent Instructions

## Required orchestration harness

Always use this project's **Slipstream operator** as the orchestration harness for agent-driven work in this repository.

- Slipstream owns orchestration, iteration, evidence collection, verification, budgets, checkpoints, and recovery.
- Agent/model providers are execution backends behind the vendor-neutral `AgentBackend` interface; do not couple orchestration logic directly to a specific vendor or model.
- Route worker and verifier activity through Slipstream whenever agent execution is available rather than creating an independent ad hoc agent loop.
- Preserve the worker → evidence → verifier → decision flow. Do not treat an agent's prose or self-reported success as proof of completion.
- Use deterministic checks and collected workspace evidence as the primary completion signal.
- When adding agent integrations, implement an adapter and capability declaration without adding provider-specific logic to `slipstream/loop/operator.py`.
- Keep run budgets, iteration/turn limits, state checkpoints, and recovery semantics enabled.

## Working on this repository

- Run `pytest -q` and `slipstream validate` before declaring a change done.
- Phase/gate orchestration lives in `slipstream/workflow/`; config loading and prompt assembly live in `slipstream/config/`. Neither may import a concrete backend.
- Workflow state must stay resumable: persist state before any agent call and after every status change, never block in-process on a human.
- Personas, skills, and workflows are YAML; keep `personas/_schema.yaml`, `skills/_schema.yaml`, and `workflows/_schema.yaml` in sync with what the loader enforces.

In short: **Slipstream is the control-plane harness; agents and models are replaceable execution workers.**
