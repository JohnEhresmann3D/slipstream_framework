# Slipstream Framework

A protocol for agent collaboration, not a cognitive runtime.

The intelligence stays in the models. Slipstream handles:

- **Coordination**: personas, phases, and handoffs between them
- **Governance**: a constitution and skills injected into every agent prompt
- **Verification**: completion is judged from workspace evidence and deterministic checks, never from an agent saying "done"
- **Safety**: human approval gates, budgets, iteration limits, and crash recovery

Agents and models are replaceable workers. The same workflow runs on [pi](https://pi.dev) (any model pi supports), Claude Code, or the OpenAI API.

## Install

```bash
python -m pip install -e ".[dev]"
pytest -q
slipstream validate
```

Requires Python 3.11+ and git. The backend CLI you choose (`pi` or `claude`) must be installed and logged in.

## Quickstart

Run a workflow against a repository, using pi with the model of your choice as both worker and verifier:

```bash
cd path/to/your/repo
slipstream workflow start \
  --project path/to/slipstream_framework \
  --workflow quick_fix \
  --task "Fix the double-jump bug when landing on moving platforms" \
  --backend pi --backend-model openai-codex/gpt-6-astra \
  --check "tests=python -m pytest -q" \
  --max-cost-usd 5
```

Each phase runs until an independent verifier accepts it. A phase with a human gate stops the run:

```text
Waiting on gate 'quick-fix-review'. Review the artifact, then run:
  slipstream workflow approve quick_fix-1a2b3c4d --continue
  slipstream workflow reject quick_fix-1a2b3c4d --note "what to change" --continue
```

Phase outputs are Markdown files under `.slipstream/workflows/<run>/artifacts/`. Read them, then approve, or reject with a note. Rejecting re-runs the phase with your feedback. Backend settings are saved with the run, so `resume`, `approve --continue`, and `reject --continue` reuse them.

Other commands:

```bash
slipstream workflow status                 # list runs
slipstream workflow status <run>           # one run, as JSON
slipstream workflow resume <run>           # continue after a crash or a NEEDS_HUMAN stop
slipstream prompt --workflow standard --phase execution   # show what the agent will see
slipstream run --goal "..." --criterion "..."              # single-goal operator loop, no phases
```

## How it works

```text
workflow (workflows/*.yaml)
 └─ phase ──────────────► one operator run, fresh agent session
     │                     worker ─► evidence ─► verifier ─► decision ─┐
     │                        ▲                                        │
     │                        └──────────── not MET yet ◄──────────────┘
     ├─ prompt:  constitution + role constitution + lead persona
     │           + consulted personas + enforced skills + phase protocol
     │           + earlier phase artifacts + reviewer feedback + task
     ├─ output:  .slipstream/workflows/<run>/artifacts/NN_<phase>_<output>.md
     ├─ checks:  "artifact exists" always; your --check commands where run_checks: true
     └─ gate:    hitl_gate: true ─► AWAITING_APPROVAL until approve / reject
```

- **Evidence beats prose.** The verifier sees git changes, check results, and artifact contents. A failed required check vetoes "MET" no matter what any model says.
- **Phases hand off through files, not chat history.** Each phase starts a fresh session and reads earlier artifacts by path, which keeps context small.
- **Stops are durable.** Every state change is checkpointed under `.slipstream/`. A crash mid-phase resumes the same operator run; a gate waits for as long as it needs to.
- **Limits are explicit.** Per-phase `circuit_breaker.max_turns` and `stall_threshold` cap iterations and no-progress loops. `--max-cost-usd` caps the whole run when the backend reports cost.

A phase with several agents runs one **lead** persona (the first listed). The others appear as **consulted perspectives**: the lead must address their concerns and record any disagreement. That gives you most of the value of a persona debate for one agent's cost.

## Project layout

```text
slipstream.yaml          paths, primary constitution, default workflow and personas
constitution/            primary constitution + per-role constitutions
personas/                who speaks: role, voice, skills, research triggers
skills/{core,quality,domain}/   how to work: allows, prohibits, output requirements
workflows/               phases, gates, checklists, transitions
tools/                   tool definitions personas may reference
slipstream/
  config/                YAML loading, validation, prompt assembly
  workflow/              phase/gate engine and its persisted state
  loop/                  operator loop, evidence, verifier, guardrails, checkpoints
    backends/            pi, Claude Code, OpenAI adapters
  cli.py                 the `slipstream` command
docs/                    operator design, adapter guide, persona guide
```

## Extending

- **Persona:** add `personas/<id>.yaml` (and optionally `constitution/roles/<id>_constitution.md`), then reference it from a workflow phase's `agents`.
- **Skill:** add `skills/<category>/<name>.yaml` (see `skills/_schema.yaml`), then list it in a persona's skills or a phase's `skills_enforced`.
- **Workflow:** add `workflows/<name>.yaml`. Every phase needs `name`, `description`, `agents`, and `output`; gated phases need a `gate_id`. Transition `requires` accepts `phase_done`, `artifact_exists`, and `hitl_gate_approved`.
- **Backend:** implement the `AgentBackend` protocol; see `docs/ADAPTER_AUTHORING.md`.

Run `slipstream validate` after any change. It reports unknown skills, personas, and tools, missing constitutions, bad transitions, and missing gate ids.

## License

Apache License 2.0. See [`LICENSE.md`](./LICENSE.md).
