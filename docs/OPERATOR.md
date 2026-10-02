# The Slipstream Operator

This package implements the September 2026 **Vendor-Neutral Agent Operator Architecture** target:

> Slipstream owns orchestration. Agent wrappers own execution.

The core operator knows only `AgentBackend`, `AgentRequest`, `AgentResult`, evidence, verifier, state, guardrails, and workspace interfaces. Claude Code, pi.dev, OpenAI/Codex-style API access, and future wrappers live behind adapters.

## What is implemented

- Provider-neutral `AgentBackend` protocol and capability declaration.
- Claude Code adapter with print-mode JSON parsing and session resume.
- pi.dev adapter using the official `pi --mode rpc` JSONL protocol.
- Optional OpenAI Responses API adapter.
- Independent `EvidenceCollector` with deterministic checks, git delta inspection, artifact hashing, and internal Slipstream-state exclusion.
- Verification gate where deterministic required-check failures veto `MET`; semantic verifier calls run in an isolated workspace snapshot by default.
- Evidence-based progress snapshots; worker prose is a secondary signal only.
- Hard-budget preflight using per-backend bounded-call reservations and explicit `UNKNOWN` status when a hard monetary cap cannot be guaranteed.
- Worker **and verifier** spend accounting.
- Run manifests, atomic state checkpoints, append-only decisions, per-iteration evidence, and worker outputs.
- Crash recovery from worker/evidence/verification checkpoints without repeating completed stages.
- Direct workspace or isolated git-worktree execution.
- Compatibility shims for the old `claude_cli.py` and `verify_gate.py` module names.
- CLI and programmatic examples.
- Offline regression and adapter tests (`pytest -q`).

## Package layout

```text
slipstream/
  loop/
    operator.py
    prompt_builder.py
    guardrails.py
    progress.py
    evidence.py
    verification.py
    state.py
    decision_log.py
    cli.py
    backends/
      base.py
      claude_code.py
      pi.py
      openai.py
      factory.py
    workspaces/
      base.py
      git_worktree.py
```

## Install for development

```bash
python -m pip install -e ".[dev]"
pytest -q
```

## pi.dev example

Pi's RPC mode is the cleanest wrapper seam for a Python Slipstream controller because Pi owns model/provider selection, tools, sessions, retries, and context management while Slipstream only sees normalized requests/results.

```bash
slipstream-operator \
  --root . \
  --backend pi \
  --backend-provider openai \
  --backend-call-reserve 1.00 \
  --verifier-backend pi \
  --verifier-provider openai \
  --verifier-call-reserve 0.25 \
  --goal "Implement the feature" \
  --criterion "Tests pass" \
  --criterion "No architecture regressions" \
  --check 'pytest=python -m pytest -q' \
  --max-iterations 6 \
  --max-cost-usd 8 \
  --require-capability filesystem \
  --require-capability shell \
  --worktree
```

The adapter launches `pi --mode rpc`, sends JSONL commands over stdin, consumes normalized events, records usage, and hides the resident process from the operator. Pi's durable `sessionFile` path is used as Slipstream's opaque continuation token, allowing `switch_session` recovery after a controller restart.

## Claude Code example

```bash
slipstream-operator \
  --root . \
  --backend claude-code \
  --backend-call-reserve 1.00 \
  --verifier-backend claude-code \
  --verifier-call-reserve 0.25 \
  --goal "Implement the feature" \
  --criterion "Tests pass" \
  --check 'pytest=python -m pytest -q'
```

## Run artifacts

By default each run writes:

```text
.slipstream/runs/<run_id>/
  manifest.json
  state.json
  decisions.jsonl
  evidence/
    iteration_001.json
  outputs/
    iteration_001.md
  artifacts/
```

`manifest.json` is immutable. `state.json` is atomically replaced after worker, evidence, verify, and decision transitions.

## Recovery

```python
result = operator.resume("<run_id>")
```

If the previous process died after the worker checkpoint, Slipstream starts at evidence. If it died after evidence, Slipstream starts at verification. It does not infer success from worker narration.

## Budget semantics

For a true bounded-call hard cap, configure `estimated_max_call_cost_usd` on each paid backend. Before each worker **and verifier** call, Slipstream reserves that amount against the remaining run cap. If the reservation no longer fits, the call is not launched.

If an adapter cannot provide a reliable bound, budget state is `UNKNOWN`; iteration, turn, and timeout caps remain enforceable. Missing provider cost is represented as `None`, never fabricated as `$0`.

## Architectural litmus test

A new wrapper is integrated correctly when it can implement `AgentBackend`, declare capabilities, pass the contract tests, and participate in the same worker/evidence/verifier loop without editing `operator.py`.
