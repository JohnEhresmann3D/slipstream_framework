# Slipstream Adapter Authoring Guide

A backend adapter is an edge module. It may understand a provider's CLI flags, RPC frames, model names, authentication, sessions, usage records, streaming events, and errors. The core operator may not.

## Required contract

Implement:

```python
class MyBackend:
    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> BackendCapabilities: ...

    @property
    def policy(self) -> BackendPolicy: ...

    def run(self, request: AgentRequest) -> AgentResult: ...
    def abort(self) -> None: ...
    def close(self) -> None: ...
```

### `AgentRequest`

- `prompt`: complete task/follow-up text.
- `workspace`: directory the wrapper must respect.
- `session_id`: opaque resume token when supported. It does not have to be the provider's human-facing session ID; for Pi, the adapter uses the durable `sessionFile` path because RPC resumes with `switch_session(sessionPath=...)`.
- `allowed_tools`: provider-neutral hint for restricted/read-only runs.
- `model`: optional adapter-level model override.
- `max_turns`, `timeout_sec`: limits to enforce when supported.
- `metadata`: operator context. Adapters may inspect it but should not require provider-specific keys from core.

### `AgentResult`

Normalize provider output into:

- `text`
- `session_id`
- `is_error`
- `cost_usd` (`None` when unknown)
- token counts (`None` when unknown)
- turns, tool calls, events
- raw provider payload for debugging
- stderr

Never invent a zero for unknown usage.

## Capabilities

Advertise actual runtime behavior. Do not make the operator assume a wrapper has filesystem, shell, sessions, structured output, cost reporting, streaming, or abort support.

The operator can enforce required capabilities at startup:

```python
Operator(..., required_worker_capabilities={"filesystem", "shell"})
```

## Budget policy

Set `BackendPolicy(estimated_max_call_cost_usd=...)` only when the configured reservation is a reliable upper bound for the call policy you are using. This lets Slipstream refuse a call before it can knowingly exceed the hard run budget.

If you cannot provide a bound, use `None`; Slipstream marks monetary enforcement `UNKNOWN` instead of pretending the cap is guaranteed.

## Error mapping

Map provider failures into the neutral taxonomy:

- `BackendUnavailable`
- `BackendTimeout`
- `BackendProtocolError`
- `BackendAuthenticationError`
- `BackendCapabilityError`

A nonzero provider exit may also be returned as `AgentResult(is_error=True)` when the provider produced a meaningful result payload.

## Verification adapters

A semantic verifier can use any backend through `BackendVerifier`. Deterministic evidence remains authoritative: a required failed check vetoes `MET`.

`BackendVerifier` snapshots the workspace into an isolated temporary directory by default, so a verifier cannot mutate the worker workspace even when its wrapper cannot enforce tool restrictions. Adapters should still honor `allowed_tools`/`read_only` when they can; isolation is defense in depth, not a reason to ignore provider controls.

## Contract-test checklist

Every new backend should prove:

1. Returns `AgentResult`.
2. Session resume round-trips when advertised.
3. Timeout maps to `BackendTimeout`.
4. Provider failure maps to `is_error` or neutral backend error.
5. Unknown usage remains `None`.
6. `abort()` works when advertised.
7. The request workspace is respected.
8. Raw provider payload is retained for debugging.

Then add the adapter only to edge factory/bootstrap code. Do not edit `operator.py`.
