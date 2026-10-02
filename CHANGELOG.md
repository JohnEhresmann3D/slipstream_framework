# Changelog

## Unreleased — Workflows on the operator

- Installable `slipstream` package and `slipstream` CLI (`validate`, `prompt`, `workflow start|status|approve|reject|resume`, `run`).
- `slipstream.config`: loads and cross-validates personas, skills, workflows, tools, and constitutions.
- Prompt assembly: constitution, role constitution, persona, consulted personas, and enforced skills form a stable prefix ahead of the task.
- `slipstream.workflow`: each phase is an operator run; phases hand off through artifacts; human gates pause durably; rejected gates re-run the phase with feedback; mid-phase crashes resume the same operator run; whole-run cost budget.
- Evidence bundles include artifact excerpts so verifiers can judge artifact content.
- Windows: backends resolve `.cmd` shims, Claude prompts go over stdin (no 32K command-line limit), backend and CLI I/O is UTF-8.
- Removed `runner.py`, `utilities/`, and runner-era docs; the operator replaces them.
- License is Apache 2.0 throughout.

## Unreleased — Vendor-Neutral Operator Update

- Extracted provider-neutral agent backend contract.
- Added Claude Code, pi.dev RPC, and optional OpenAI adapters.
- Added capability negotiation and edge-only backend factory.
- Added deterministic repository evidence and false-claim protection.
- Replaced prose-first stuck detection with evidence-based progress snapshots.
- Hardened run budgets with bounded-call reservations and verifier cost accounting.
- Added manifests, atomic checkpoints, decision logs, evidence snapshots, and crash recovery.
- Added direct and git-worktree workspace managers.
- Added compatibility shims for earlier Claude/verify module names.
- Added offline tests and CLI/programmatic examples.
