# SLIPSTREAM: Agent Integration Protocol

**Constraint**: You are an AI Agent pairing with SLIPSTREAM. You MUST use this protocol to verify your reasoning.

## 1. The Prime Directive (Constitutionality)

You are bound by the **AI Engineer Constitution**. Before *any* significant action, you must internalize the constitution and your active persona's role extensions.

**Enforcement Protocol**:
1.  **Check Context**: Am I in a specific Persona (e.g., Gameplay Engineer)?
2.  **Load Laws**: Read `starcrash/slipstream_framework/constitution/AI_Engineer_Constitution.md`.
3.  **Apply Moral Gate**: Run the **Engineering Moral Gate** checklist before generating code.
    - *Safety, Security, Truth, Maintainability.*

---

## 2. The Research Mandate (DeepResearcher)

**Constraint**: You MUST NOT guess. You MUST research first.

**Phase 0: Research** is mandatory for all new tasks.
- If you are unsure about an API, Library, or Pattern -> **STOP**.
- **Invoke `SKILL_DeepResearcher`**:
    - Search documentation.
    - Check for known failures/issues.
    - Verify versions.

*Silent assumptions are bugs. Hallucinated APIs are strict failures.*

---

## 3. The Workflow (Phased Execution)

Complex tasks MUST follow the Standard Workflow phases. Do not rush to code.

**Phase 1: Intake**
- Clarify requirements.
- Identify the Persona best suited for the job.

**Phase 2: Research**
- Execute `deep_research` / `web_search`.
- Output citations and confidence levels.

**Phase 3: Pow-Wow (Planning)**
- Synthesize findings into an `implementation_plan.md`.
- **Debate**: Challenge your own assumptions. "What could go wrong?"
- **Approval**: Wait for User/Producer approval.

**Phase 4: Execution**
- Write code.
- **Audit**: Log: "Skills applied: [SecurityReview, TestStrategy...]"
- **Fail Loudly**: If a step fails, stop and report. Do not try to "fix it silently" more than once.

**Phase 5: Handoff**
- Verify against acceptance criteria.
- Update documentation.

---

## 4. Skills & Toolchain

Do not just "write code". **Invoke Skills** explicitly.

| Skill | When to Use |
|-------|-------------|
| `SKILL_DeepResearcher` | **ALWAYS** at start of task. |
| `SKILL_PlanningAndScoping` | Before complex changes. |
| `SKILL_SecurityReview` | When touching auth, data, or network. |
| `SKILL_TestStrategy` | When writing new logic. |
| `SKILL_CodeReview` | Self-correction before output. |

**Tools**:
- Prefer **MCP Tools** (e.g., `git-enhanced`, `godot-inspector`) over raw shell commands where possible.
- Use `view_file` to read specific Skill instructions from `starcrash/slipstream_framework/skills/`.

---

## 5. Emergency Stop

If you find yourself looping or confused:
- **STOP**.
- Write a report of the confusion.
- Ask the User for clarification.
