from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ALL_ASSIGNED = "all_assigned"
PHASE_MODES = {"sequential", "collaborative", "parallel"}

# Vocabulary understood by the workflow engine for `transitions.*.requires`.
TRANSITION_REQUIREMENTS = {"phase_done", "artifact_exists", "hitl_gate_approved"}

# Phase keys with dedicated fields. Anything else on a phase is protocol
# detail (research_tracks, plan_format, ...) that is rendered into the prompt.
PHASE_KNOWN_KEYS = {
    "name", "description", "hitl_gate", "gate_id", "gate_description", "agents",
    "skills_enforced", "output", "checklist", "standards", "circuit_breaker",
    "moral_gate", "mode", "run_checks",
}


@dataclass(frozen=True)
class Skill:
    id: str
    category: str
    description: str
    path: Path
    allows: list[str] = field(default_factory=list)
    prohibits: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    output_requirements: list[str] = field(default_factory=list)
    failure_conditions: list[str] = field(default_factory=list)
    hitl_required_for: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    role: str
    path: Path
    skills_required: list[str] = field(default_factory=list)
    skills_optional: list[str] = field(default_factory=list)
    tools_access: list[str] = field(default_factory=list)
    voice: dict[str, Any] = field(default_factory=dict)
    responsibilities: dict[str, list[str]] = field(default_factory=dict)
    research_triggers: list[dict[str, Any]] = field(default_factory=list)
    role_constitution_path: Path | None = None


@dataclass(frozen=True)
class Phase:
    name: str
    description: str
    hitl_gate: bool = False
    gate_id: str | None = None
    gate_description: str | None = None
    agents: list[str] | str = field(default_factory=list)
    skills_enforced: list[str] = field(default_factory=list)
    output: str | None = None
    checklist: list[str] = field(default_factory=list)
    standards: list[str] = field(default_factory=list)
    max_turns: int | None = None
    stall_threshold: int | None = None
    moral_gate: bool = False
    mode: str | None = None
    run_checks: bool = False
    protocol: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Transition:
    source: str
    target: str
    requires: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Workflow:
    id: str
    name: str
    description: str
    path: Path
    phases: list[Phase]
    default_personas: list[str] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)

    def phase(self, name: str) -> Phase:
        for phase in self.phases:
            if phase.name == name:
                return phase
        raise KeyError(f"workflow {self.id!r} has no phase {name!r}")

    def transition(self, source: str, target: str) -> Transition | None:
        for transition in self.transitions:
            if transition.source == source and transition.target == target:
                return transition
        return None


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" | "warning"
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity.upper()}: {self.where}: {self.message}"


@dataclass
class Project:
    root: Path
    config: dict[str, Any]
    constitution_path: Path
    personas: dict[str, Persona]
    skills: dict[str, Skill]
    workflows: dict[str, Workflow]
    tools: set[str]
    default_workflow: str | None = None
    default_personas: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    def constitution(self) -> str:
        return self.constitution_path.read_text(encoding="utf-8")

    def role_constitution(self, persona_id: str) -> str:
        path = self.personas[persona_id].role_constitution_path
        return path.read_text(encoding="utf-8") if path and path.is_file() else ""

    def resolve_agents(self, phase: Phase, assigned: list[str]) -> list[str]:
        if phase.agents == ALL_ASSIGNED:
            return list(assigned)
        return list(phase.agents)
