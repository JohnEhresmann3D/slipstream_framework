# Slipstream Framework

A protocol for agent collaboration, not a cognitive runtime.

## Philosophy

The intelligence stays in the models. Slipstream handles:

- **Coordination** between specialized personas
- **Grounding** through research before action
- **Governance** through constitutional constraints
- **Safety** through human-in-the-loop gates

This is not another "cognitive framework" that wraps LLMs in middleware complexity. It's a protocol for how agents communicate, share context, and stay grounded in reality.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      WORKFLOW ORCHESTRATOR                       │
│                                                                  │
│  Utilities:                                                      │
│  ├── circuit_breaker (prevent runaway conversations)             │
│  ├── hitl (human gates at phase boundaries)                      │
│  ├── audit (log decisions, tools, outputs)                       │
│  └── rate_limiter (API throttling)                               │
└──────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   PERSONAS    │    │    SKILLS     │    │     TOOLS     │
│  (who speaks) │    │ (how to work) │    │ (what to use) │
├───────────────┤    ├───────────────┤    ├───────────────┤
│ Producer      │    │ Constitution  │    │ deepsearch    │
│ Game Designer │    │ DeepResearcher│    │ codebase grep │
│ Gameplay Eng  │    │ Planning      │    │ web fetch     │
│ QA Engineer   │    │ Security      │    │ MCP servers   │
│ Sound Design  │    │ Requirements  │    │               │
└───────────────┘    └───────────────┘    └───────────────┘
```

## Directory Structure

```
Slipstream_Framework/
├── slipstream.yaml           # Main configuration
├── README.md
│
├── constitution/             # Governance
│   └── AI_Engineer_Constitution.md
│
├── personas/                 # Who speaks
│   ├── _schema.yaml
│   ├── producer.yaml
│   ├── game_designer.yaml
│   ├── gameplay_engineer.yaml
│   ├── qa_engineer.yaml
│   └── sound_designer.yaml
│
├── skills/                   # How to work
│   ├── _schema.yaml
│   ├── core/                 # Always available
│   │   ├── SKILL_DeepResearcher.md
│   │   ├── SKILL_PlanningAndScoping.md
│   │   └── SKILL_RequirementsClarification.md
│   ├── quality/              # Quality assurance
│   │   ├── SKILL_Security_Review.md
│   │   ├── SKILL_TestStrategy.md
│   │   └── ...
│   └── domain/               # Project-specific
│       ├── SKILL_SoundDesign.md
│       └── SKILL_DocumentationHandoff.md
│
├── workflows/                # Phase sequences
│   ├── _schema.yaml
│   ├── standard.yaml         # Full 5-phase workflow
│   ├── quick_fix.yaml        # Abbreviated workflow
│   └── research_only.yaml    # Research without implementation
│
├── tools/                    # Tool configurations
│   ├── deepsearch.yaml
│   ├── web_fetch.yaml
│   └── codebase.yaml
│
├── utilities/                # Runtime utilities
│   ├── __init__.py
│   ├── io.py
│   ├── circuit_breaker.py
│   ├── audit.py
│   ├── hitl.py
│   ├── rate_limiter.py
│   └── rules.yaml
│
└── sessions/                 # Runtime state
    └── {session_id}/
        ├── context.json
        ├── audit.log
        └── artifacts/
```

## Workflow Phases

### Standard Workflow

```
PHASE 1: INTAKE
├── Human provides task
├── Producer clarifies requirements
├── HITL gate: confirm understanding
└── Output: Task statement with acceptance criteria

PHASE 2: RESEARCH (DeepResearcher enforced)
├── All personas research their domain
├── Competitive analysis, failure analysis, tooling deep dive
├── Circuit breaker: max 10 turns
└── Output: Cited research artifacts

PHASE 3: POW-WOW (Planning + Debate)
├── Personas share findings
├── Challenge assumptions, fill gaps
├── Synthesize into plan
├── HITL gate: approve plan
└── Output: Approved implementation plan

PHASE 4: EXECUTION
├── Skills applied per Constitution
├── Moral Gate checked before code
├── Audit trail maintained
└── Output: Implementation

PHASE 5: HANDOFF
├── Verify acceptance criteria
├── Documentation complete
├── HITL gate: final review
└── Output: Complete
```

## Key Concepts

### Personas

Personas define **who speaks** and **what they care about**. Each persona has:

- **Role**: What they do
- **Skills**: What rules they follow
- **Voice**: What they focus on, what they challenge, who they defer to
- **Tools**: What they can use

Example persona interaction:

```
Producer: "This feature needs to ship by Friday."
Game Designer: "The UX flow isn't right yet. Players will be confused."
Gameplay Engineer: "I can simplify the implementation if we cut feature X."
Producer: "Let's cut X. Designer, can you validate the simplified flow?"
```

### Skills

Skills define **how to work**. They're applied based on context:

- **Phase 0 (Mandatory)**: DeepResearcher - always research first
- **Always**: PlanningAndScoping - unless trivial
- **Conditional**: SecurityReview if handling user data, etc.

Skills have precedence:
1. Safety/Security
2. Correctness/Verification
3. Maintainability
4. Speed/Convenience

### Constitution

The Constitution is **runtime law**. It defines:

- Safety constraints (no hidden risk, least privilege)
- Truth constraints (no hallucinated APIs, explicit uncertainty)
- Change control (no silent behavior changes)
- Escalation requirements (human review for risky changes)
- Moral Gate (checklist before producing code)

### Utilities

Utilities provide **safety infrastructure**:

- **circuit_breaker**: Stops runaway conversations
- **hitl**: Human approval gates at phase boundaries
- **audit**: Logs all decisions and tool calls
- **rate_limiter**: Prevents API abuse

## Usage

### Basic Session

```python
from utilities import CircuitBreaker, HITLManager, AuditTrail

# Initialize utilities
cb = CircuitBreaker(session_id="feature-123")
hitl = HITLManager(session_id="feature-123")
audit = AuditTrail()

# Check circuit before agent turn
if cb.can_execute():
    # Run agent turn
    result = run_agent_turn(...)

    # Record result
    cb.record_turn_result(TurnResult(
        turn_number=1,
        artifacts_produced=len(result.artifacts),
        new_information=result.has_new_info
    ))

    # Log to audit
    audit.log_event(
        session_id="feature-123",
        event_type="agent_turn",
        agent="gameplay_engineer",
        phase="execution",
        details=result.summary,
        tools_used=result.tools,
        skills_applied=["security_review", "test_strategy"]
    )

# Check HITL gate
gate_result = hitl.check_and_gate(
    gate_id="plan-approval",
    action_type="phase_transition",
    phase="powwow",
    description="Approve implementation plan",
    details={"plan": plan_content}
)

if not gate_result["ok"]:
    # Wait for human approval
    print(f"Waiting for approval: {gate_result['gate']['description']}")
```

### Adding a New Persona

1. Create `personas/your_persona.yaml`
2. Define role, skills, voice, tools
3. Reference in workflow phases

### Adding a New Skill

1. Create `skills/{category}/SKILL_YourSkill.md`
2. Follow the schema (Use When, Rules, Output Format)
3. Reference in persona definitions

### Adding a New Workflow

1. Create `workflows/your_workflow.yaml`
2. Define phases, gates, skills enforced
3. Reference in `slipstream.yaml` or use directly

## Attribution

Utilities adapted from [CLOCKWORK-CORE](https://github.com/JoshTellsTime/CLOCKWORK-CORE):
- circuit_breaker.py
- audit.py
- hitl.py
- rate_limiter.py

## License

MIT
