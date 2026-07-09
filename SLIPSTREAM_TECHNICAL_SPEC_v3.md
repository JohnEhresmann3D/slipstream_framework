# Slipstream — Technical Specification v3.0

**Status:** Draft — supersedes the Python-engine architecture (v2.x)
**Change in one line:** Slipstream is a markdown-native persona, constitution, and
skill system for governing Claude's behavior inside a project. It is not a
runtime, and it does not execute.

---

## 1. Purpose

Slipstream gives a Claude-powered project three things:

1. **Identity** — who Claude is acting as, with a real point of view, not a job
   description. (Persona layer.)
2. **Authority** — what that identity is and isn't allowed to decide, and when it
   must stop and ask a human. (Constitution layer.)
3. **Capability** — a library of reusable procedures Claude can apply, portable
   across projects regardless of what tools are actually connected. (Skill layer.)

It is meant to be **dropped into any project** — a Claude Project, a Claude Code
repo, or an API system prompt — and read, not run. Game development is the
worked example this spec ships with. It is not the product.

---

## 2. Design Principle: Sort Every Feature by Enforcement Reality

Before anything goes into Slipstream, it's classified by *how* it actually
constrains Claude's behavior:

| Tier | Mechanism | Example | Reliability |
|---|---|---|---|
| **A — Platform-enforced** | The host platform blocks the action outside the model's control | A Claude Code hook denying a bash command | Real, mechanical |
| **B — Injected-once** | Stated identity or constraint present in every relevant turn | A constitution clause, a persona's stated bias | Strong, non-mechanical |
| **C — Protocol-dependent** | Multi-step process the model must faithfully self-administer across many turns with no outside check | "Track your own context budget across 40 turns," "spot-check each subagent's output before proceeding" | Weak — degrades with session length, unverifiable |

**Rule: Slipstream ships Tier A when the host platform offers it, Tier B always,
and treats Tier C as a design smell to be rewritten, not elaborated.**

This is the lesson of both prior architectures reviewed for this spec: an
internal Python engine that no host platform actually runs is Tier C dressed as
Tier A — it looks like enforcement but has no execution context to enforce
*in*. A sister framework's multi-phase orchestrator asking a model to track its
own context budget in prose is the same failure from the opposite direction. Both
were elaborate Tier C. Slipstream v3 does not repeat this.

---

## 3. Repository Structure

```
slipstream/
├── MANIFEST.template.md        # per-project config, copied and filled in
├── core/
│   ├── constitution/
│   │   └── BASE_CONSTITUTION.md    # domain-neutral, supreme authority
│   ├── skills/                     # universal, portable skill library
│   │   ├── deep_researcher.md
│   │   ├── planning_and_scoping.md
│   │   ├── requirements_clarification.md
│   │   ├── security_review.md
│   │   └── ...
│   └── capabilities.md             # capability vocabulary (see §6)
├── factory/
│   ├── persona_author.md           # SKILL.md: mints new personas
│   ├── constitution_author.md      # SKILL.md: mints new role constitutions
│   └── skill_author.md             # SKILL.md: mints new skills
├── packs/
│   └── gamedev/                    # WORKED EXAMPLE, not the framework
│       ├── constitution/
│       │   └── roles/
│       │       ├── game_designer_constitution.md
│       │       ├── gameplay_engineer_constitution.md
│       │       └── ...
│       ├── personas/
│       │   ├── game_designer.md
│       │   ├── gameplay_engineer.md
│       │   ├── producer.md
│       │   └── ...
│       └── skills/
│           └── balance_tuning.md
├── deploy/
│   ├── claude-project/
│   │   └── README.md               # how to load Slipstream into a Project
│   ├── claude-code/
│   │   ├── README.md                # maps personas -> agents/*.md, hooks
│   │   └── hooks.example.json       # Tier A enforcement, platform-native
│   └── api/
│       └── engine/                  # OPTIONAL. Not installed by default.
│           └── README.md            # "if you need programmatic Tier-A
│                                     #  enforcement outside Claude Code,
│                                     #  here's a reference runtime"
└── README.md
```

The `deploy/api/engine/` directory is where the prior Python runtime (circuit
breaker, HITL manager, audit trail, agent loop) lives going forward. It is
explicitly out-of-band: nothing in `core/`, `factory/`, or `packs/` depends on
it, references it, or assumes it's running. It exists for the one legitimate
use case — someone driving Slipstream personas through the raw Anthropic API,
where Tier-A enforcement is achievable because the caller owns the loop.

---

## 4. Persona Format

One file per persona. YAML frontmatter for what a host platform can mechanically
key off; prose body for what actually conditions the model.

```markdown
---
name: game_designer
role: Designs game mechanics, systems, and player experience
constitution:
  primary: core/constitution/BASE_CONSTITUTION.md
  role: packs/gamedev/constitution/roles/game_designer_constitution.md
skills_required: [deep_researcher, planning_and_scoping]
capabilities_used: [web_research, file_read]
prohibits: [override_engineer_on_feasibility, expand_scope_without_signoff]
hitl_required: [monetization_mechanic, difficulty_default_change_post_launch]
defers_to:
  - gameplay_engineer on technical feasibility
  - producer on timeline and scope
---

[Prose body: formative experience, a stated bias the persona owns, a specific
opinion they'll defend, a self-aware flaw, explicit boundaries with other
roles. Specific and idiosyncratic, not a job description. See
factory/persona_author.md for the authoring method and §8 for why specificity
is load-bearing.]
```

**Frontmatter fields are Tier B by default everywhere.** On Claude Code, a
subset (`prohibits` mapped to bash/write patterns, `hitl_required` mapped to a
confirmation hook) can be promoted to Tier A via `deploy/claude-code/hooks.example.json`.
Elsewhere, frontmatter is metadata the model reads like the rest of the file —
useful for a human or a build script to reason about the persona set, not
mechanically enforced.

**The body is the product.** A persona whose body is two sentences of role
description ("focuses on player experience, challenges scope creep") produces a
generic-assistant output wearing a name tag. A persona with a real point of
view shifts the actual output distribution. This is the whole thesis Slipstream
is built to encode, and it is the single most important quality bar for
anything the factory mints.

---

## 5. Constitution Library

Two-tier hierarchy, unchanged in shape from v2, corrected in content:

- **`core/constitution/BASE_CONSTITUTION.md`** — domain-neutral. Supreme
  authority. Covers: research-before-acting, escalation triggers (irreversible
  actions, money, security, safety-critical decisions), honesty about
  uncertainty, and the behavioral (Tier B) versions of what used to be
  code-enforced gates — e.g. *"If you have gone several turns without making
  verifiable progress on the stated goal, stop and say so explicitly rather
  than continuing"* — stated as an instruction a model can actually follow, not
  a threshold a circuit breaker used to check.
- **`packs/{pack}/constitution/roles/*.md`** — subordinate. Role-specific
  identity, research mandates, and don'ts. Must never restate or override
  anything in the base constitution; only narrow it.

**Correction from v2:** the base constitution previously carried game-dev
assumptions (examples, escalation triggers phrased around shipping a game).
v3's base constitution is audited to be genuinely domain-neutral; anything
game-specific moves to the gamedev pack's role constitutions.

---

## 6. Skill Library and the Capability Indirection

Skills are `SKILL.md` files — Anthropic's own skill convention, which is also
what Claude Code natively discovers. Each skill declares what it needs in terms
of **capabilities**, not concrete tools:

```yaml
---
name: deep_researcher
description: "Research methodology before proposing designs or decisions..."
capabilities_needed: [web_research, file_read]
allows: [propose_findings, flag_gaps]
prohibits: [make_final_decisions, lock_scope]
---
```

`core/capabilities.md` defines the vocabulary (`web_research`, `file_read`,
`codebase_search`, `issue_tracking`, `design_lookup`, ...) and each project's
`MANIFEST.md` maps capabilities to whatever is actually connected:

```markdown
## Capability Map
- web_research -> WebSearch (Claude Code) | web_search tool (claude.ai)
- issue_tracking -> Linear MCP
- design_lookup -> Figma MCP
```

This one indirection is what makes a skill written for one project usable
in another with completely different MCP connections — the skill never
hardcodes a tool name, so nothing breaks when the underlying integration
changes.

**Split:** `core/skills/` holds universal skills (research, planning,
requirements clarification, security review). `packs/{pack}/skills/` holds
domain-specific ones (e.g. `balance_tuning.md` in gamedev). A new non-gamedev
project takes all of `core/skills/` and none of any pack by default.

---

## 7. Per-Project Manifest

Every project using Slipstream gets one small file, copied from
`MANIFEST.template.md`, that says what's actually active — because the library
is meant to hold far more than any one project uses:

```markdown
# Project Manifest — {project name}

## Active Personas
- game_designer (packs/gamedev)
- gameplay_engineer (packs/gamedev)

## Constitution Stack
- core/constitution/BASE_CONSTITUTION.md
- packs/gamedev/constitution/roles/*.md (for active personas only)

## Capability Map
[see §6]

## Deployment
- Host: Claude Code
- Tier-A hooks enabled: credential_guard, destructive_bash_guard
```

Without this file, Claude has to infer which library contents are live for a
given project. With it, onboarding a new project is: copy the template, list
personas, map capabilities, done.

---

## 8. The Factory

The gamedev pack is not "the framework with an example bolted on" — it is the
**few-shot exemplar set** for a generative skill: `factory/persona_author.md`.

Given a short project brief, the factory produces a new persona file (and,
alongside `constitution_author.md`, a matching role constitution if the
project needs a new role type) by:

1. Identifying the *player-of-the-role's* actual stake and bias — not a
   job description, a point of view someone with this job would develop.
2. Writing a formative detail or specific opinion that couldn't be swapped
   into a different role's persona unchanged. (The test for a weak persona:
   if you could paste the body into a different role file and it would still
   basically work, it's too generic.)
3. Populating frontmatter from the constitution and capability vocabulary
   already in the project.
4. Checking the draft against the existing gamedev personas as calibration
   examples for tone and specificity, not for content.

This is the resolution to "library vs. factory": the library doesn't
anticipate every domain, and the factory without exemplars produces generic
output. Together, the gamedev pack is simultaneously a usable example and the
factory's training wheel.

---

## 9. Deployment Tiers

| | Claude Project | Claude Code | API (optional) |
|---|---|---|---|
| Persona loading | Pasted/attached to project knowledge | `agents/*.md` per Claude Code convention | Injected into system prompt by caller |
| Constitution | Project knowledge, read every session | `CLAUDE.md` + referenced role files | Injected into system prompt |
| Skills | Project knowledge | Native `SKILL.md` discovery | Loaded and injected by caller |
| Tier-A enforcement | None available — Tier B only | Hooks (`deploy/claude-code/hooks.example.json`) | Caller's own code (`deploy/api/engine/`, optional) |
| Manifest | Read manually by Claude at session start | Same, or scripted via a hook | Read by caller's orchestration code |

No tier is the "main" one. Claude Code gets real mechanical enforcement for
free via hooks — use it there. Projects get identity and authority without
enforcement — that's the honest ceiling, and the constitution is written to be
followed as instruction, not to imply a guarantee the platform can't back.

---

## 10. What Was Cut, and Why

| Removed from core | Reason |
|---|---|
| `engine.py` agent loop | Tier C outside its one legitimate context (raw API use). Moved to `deploy/api/engine/`, optional. |
| Circuit breaker / HITL manager / rate limiter / audit trail as always-on utilities | Same — real enforcement only when the caller owns the loop. Their *behavioral* equivalents are now constitution clauses (§5). Code preserved under `deploy/api/engine/` for that one use case. |
| Five-persona mandatory pow-wow | Multi-agent token cost for a benefit obtainable from forced-perspective review inside a single pass (see `core/skills/plan_check.md`, adapted from the critic/minimalist/skeptic/reverser pattern). Personas still exist; the phase requiring all five to convene by default does not. |
| Pure-YAML persona format | Couldn't carry the conditioning prose that does the actual work. Fully replaced by frontmatter-markdown (§4). |
| Game-dev assumptions in the base constitution | Moved to the gamedev pack's role constitutions; base is now domain-neutral. |

---

## 11. Open Questions

- **Sticky rejection semantics for Tier-B "hard no" clauses.** A constitution
  clause like "never do X without signoff" has no state to check against on
  re-prompt the way a coded HITL gate did. Worth a convention (e.g., a
  project's STATE.md logs prior rejections for Claude to re-read) but not yet
  specified here.
- **Pack governance.** As more packs appear (web-app, data-pipeline, etc.),
  do they share `core/skills/` verbatim or fork? Current assumption is
  verbatim share, packs only add.
- **Versioning.** Personas and constitutions will drift per-project once
  edited locally. No migration/upgrade path is specified yet for pulling
  core updates into a project that has diverged.
