# Migration Notes

## Intended source alignment

The update follows the September 2026 Slipstream technical design that assessed the prior operator loop as:

- `loop/operator.py`
- `loop/claude_cli.py`
- `loop/verify_gate.py`
- `loop/guardrails.py`
- `loop/prompt_builder.py`
- `loop/decision_log.py`
- `tests/fake_claude.py`

The target package moves that functionality under `slipstream/loop/` and extracts provider-specific behavior into `slipstream/loop/backends/`.

## Important merge detail

The original `slipstream_operator_loop.zip` attachment was not available to the execution environment when this build was generated. For that reason this deliverable is an **additive, self-contained implementation/overlay** built against the exact architecture and behavioral assessment in the technical design rather than a byte-for-byte patch of that archive.

Compatibility shims are included at:

- `slipstream/loop/claude_cli.py`
- `slipstream/loop/verify_gate.py`

If the older loop already lives inside a `slipstream/` package, copy/merge this `slipstream/loop/` tree over it and port any project-specific prompt/config wiring into `PromptBuilder` or bootstrap code. If it lives as a top-level `loop/`, move callers to `slipstream.loop` as part of the migration.

## Recommended merge sequence

1. Add `backends/base.py` and the fake-backend tests.
2. Migrate Claude integration behind `ClaudeCodeBackend`.
3. Switch `Operator` construction to injected `worker` and `verifier` objects.
4. Add evidence and deterministic checks.
5. Enable evidence-based progress and bounded-call budget reservations.
6. Enable state/checkpoint directories.
7. Add Pi as the second adapter and run the same contract tests.
8. Turn on git-worktree isolation for autonomous coding runs.

## Behavior changes that are intentional

- A worker saying "tests passed" is no longer evidence.
- Required deterministic check failures prevent `MET`.
- The operator accounts verifier spend as well as worker spend when the verifier reports it.
- A hard monetary cap is only described as enforced when calls have a configured reliable reservation; otherwise state is `UNKNOWN`.
- Progress is repository/evidence based, not prose-hash based.
- `.slipstream/` runtime state is ignored by progress evidence so the operator does not mistake its own checkpoints for agent progress.
