from __future__ import annotations

from typing import Iterable

import yaml

from ..loop.prompt_builder import PromptBuilder
from .models import Persona, Phase, Project, Skill

PRECEDENCE = (
    "Authority: primary constitution > role constitution > skill rules.\n"
    "When skills conflict: Safety/Security > Correctness/Verification > "
    "Maintainability > Speed/Convenience."
)


def _bullets(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _render_skill(skill: Skill) -> str:
    parts = [f"### {skill.id}\n{skill.description}"]
    for label, items in (
        ("Allowed", skill.allows),
        ("Prohibited", skill.prohibits),
        ("Output requirements", skill.output_requirements),
        ("Stop and escalate when", skill.failure_conditions),
        ("Human approval required for", skill.hitl_required_for),
    ):
        if items:
            parts.append(f"{label}:\n{_bullets(items)}")
    return "\n".join(parts)


def _render_persona(persona: Persona, phase: Phase | None) -> str:
    voice = persona.voice
    parts = [f"## Persona: {persona.name}\n{persona.role}"]
    if voice.get("focus"):
        parts.append(f"Focus: {' '.join(str(voice['focus']).split())}")
    if voice.get("challenges"):
        parts.append(f"Push back on: {' '.join(str(voice['challenges']).split())}")
    if voice.get("defers_to"):
        parts.append("Defer to:\n" + _bullets(str(d) for d in voice["defers_to"]))
    if phase and persona.responsibilities.get(phase.name):
        parts.append(f"Responsibilities in {phase.name}:\n" + _bullets(persona.responsibilities[phase.name]))
    if persona.research_triggers:
        parts.append(
            "Research before acting when:\n"
            + _bullets(f"{t.get('condition')}: {t.get('action')}" for t in persona.research_triggers)
        )
    return "\n".join(parts)


def _render_consultant(persona: Persona) -> str:
    focus = " ".join(str(persona.voice.get("focus", "")).split())
    challenges = " ".join(str(persona.voice.get("challenges", "")).split())
    line = f"- {persona.name} ({persona.role})"
    if focus:
        line += f"\n  Cares about: {focus}"
    if challenges:
        line += f"\n  Would challenge: {challenges}"
    return line


def render_static_context(
    project: Project,
    persona_id: str,
    phase: Phase | None = None,
    consultants: Iterable[str] = (),
) -> str:
    """Render the stable prompt prefix: constitutions, persona, and skills.

    This text does not depend on the task or iteration, so backends that
    support prompt caching can reuse it across calls.
    """
    persona = project.personas[persona_id]
    enforced = list(phase.skills_enforced) if phase else list(persona.skills_required)
    available = [
        s for s in dict.fromkeys(persona.skills_required + persona.skills_optional)
        if s not in enforced
    ]

    sections = [
        "# SLIPSTREAM OPERATING CONTEXT",
        "## Primary constitution (supreme authority)\n" + project.constitution().strip(),
    ]
    role = project.role_constitution(persona_id).strip()
    if role:
        sections.append(f"## Role constitution: {persona.name}\n{role}")
    sections.append(_render_persona(persona, phase))

    consultant_ids = [c for c in consultants if c != persona_id and c in project.personas]
    if consultant_ids:
        sections.append(
            "## Consulted perspectives\n"
            "You lead this phase. Before finalizing, address the concerns each of these "
            "roles would raise, and record where you disagree with them and why.\n"
            + "\n".join(_render_consultant(project.personas[c]) for c in consultant_ids)
        )

    if enforced:
        sections.append(
            "## Enforced skills (apply all of these)\n"
            + "\n\n".join(_render_skill(project.skills[s]) for s in enforced if s in project.skills)
        )
    if available:
        sections.append(
            "## Other skills (apply when relevant)\n"
            + _bullets(f"{s}: {project.skills[s].description}" for s in available if s in project.skills)
        )
    sections.append("## Precedence\n" + PRECEDENCE)
    return "\n\n".join(sections)


def render_phase_brief(phase: Phase) -> str:
    """Render phase-specific instructions that sit between context and task."""
    parts = [f"## Phase: {phase.name}\n{phase.description}"]
    if phase.protocol:
        parts.append(
            "Phase protocol:\n"
            + yaml.safe_dump(phase.protocol, sort_keys=False, allow_unicode=True).strip()
        )
    if phase.moral_gate:
        parts.append(
            "The constitution's Engineering Moral Gate is required in this phase. "
            "Answer each Moral Gate item in your phase output before making code changes."
        )
    return "\n\n".join(parts)


class PhasePromptBuilder(PromptBuilder):
    """PromptBuilder that puts project context first so it forms a cacheable prefix."""

    def __init__(
        self,
        project: Project,
        persona_id: str,
        phase: Phase | None = None,
        consultants: Iterable[str] = (),
        extra_sections: Iterable[str] = (),
    ):
        persona = project.personas[persona_id]
        skills = list(phase.skills_enforced) if phase else list(persona.skills_required)
        super().__init__(
            constitution=project.constitution(),
            persona=persona.name,
            skills=skills,
        )
        self.static_context = render_static_context(project, persona_id, phase, consultants)
        self.phase = phase
        self.extra_sections = [s for s in extra_sections if s]

    def initial(self, goal: str, criteria: list[str]) -> str:
        sections = [self.static_context, "# CURRENT ASSIGNMENT"]
        if self.phase:
            sections.append(render_phase_brief(self.phase))
        sections.extend(self.extra_sections)
        sections += [
            f"## Goal\n{goal}",
            "## Acceptance criteria\n" + _bullets(criteria),
            "You are the worker agent operating under Slipstream orchestration. Work directly "
            "in the provided workspace. An independent verifier will judge your work from "
            "workspace evidence; do not claim checks passed unless you actually ran them.",
        ]
        return "\n\n".join(sections)
