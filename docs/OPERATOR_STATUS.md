# Implementation Status

This build implements the vendor-neutral architecture as a self-contained Slipstream operator overlay.

| Design milestone | Status | Implementation |
|---|---|---|
| Protocol extraction | Complete | `backends/base.py`; operator imports neutral contracts only |
| Claude migration | Complete | `backends/claude_code.py` plus compatibility shim |
| Fake backend tests | Complete | in-memory scripted backend; no provider/network spend |
| Independent evidence | Complete | git state, deterministic checks, artifacts, hashes |
| False-claim protection | Complete | deterministic required failures veto `MET` at verifier and operator layers |
| Budget hardening | Complete for bounded-call policy | worker + verifier reservations; breach detection; `UNKNOWN` when unbounded |
| Evidence-based progress | Complete | workspace/diff/check/artifact/criteria deltas; prose secondary |
| Checkpointing | Complete | manifest + atomic state after worker/evidence/verify/decision transitions |
| Capability negotiation | Complete | backend capability declarations + required worker preflight |
| Second adapter | Complete | Pi RPC adapter using official JSONL mode and durable session-file continuation |
| API adapter | Complete as optional baseline | OpenAI Responses API adapter, intentionally no filesystem/shell claims |
| Workspace isolation | Complete | detached git worktree manager with preserve/delete policy |
| Recovery | Complete | resumes from saved stage without repeating completed worker/evidence/verify stages |
| Verifier isolation | Complete | semantic verifier receives an isolated temporary snapshot by default |
| Adapter guide | Complete | `docs/ADAPTER_AUTHORING.md` |

## Validation

The offline suite covers the operator loop, false-success defense, evidence/progress semantics, worker and verifier budget behavior, backend failure classification, recovery checkpoints, workspace isolation, provider-independence, Claude Code parsing/timeout/resume, and Pi RPC text/usage/session-file resume/timeout.

When first delivered, the operator's offline suite was 26 tests. The full suite now also covers the config loader, the workflow engine and the CLI; run `pytest -q`.

## Source-package limitation

The technical architecture PDF was recoverable, but the original `slipstream_operator_loop.zip` attachment from the prior conversation was not exposed to this execution environment. This build therefore targets the module names, behaviors, gaps, migration plan, and acceptance conditions documented in that PDF. See `OPERATOR_MIGRATION_NOTES.md`.
