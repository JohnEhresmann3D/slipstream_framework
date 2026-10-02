from __future__ import annotations

from .verification import GateResult
from .evidence import EvidenceBundle


class PromptBuilder:
    def __init__(self, constitution: str | None = None, persona: str | None = None, skills: list[str] | None = None):
        self.constitution = constitution or ""
        self.persona = persona or ""
        self.skills = skills or []

    def initial(self, goal: str, criteria: list[str]) -> str:
        sections = [
            "You are the worker agent operating under Slipstream orchestration.",
            f"GOAL:\n{goal}",
            "ACCEPTANCE CRITERIA:\n" + "\n".join(f"- {c}" for c in criteria),
            "Work directly in the provided workspace. Do not claim checks passed unless you actually ran them.",
        ]
        if self.constitution:
            sections.append("CONSTITUTION:\n" + self.constitution)
        if self.persona:
            sections.append("PERSONA:\n" + self.persona)
        if self.skills:
            sections.append("SKILLS:\n" + "\n".join(f"- {s}" for s in self.skills))
        return "\n\n".join(sections)

    def followup(self, goal: str, criteria: list[str], gate: GateResult, evidence: EvidenceBundle) -> str:
        failed = [c.name for c in evidence.checks if c.passed is False]
        return "\n\n".join(
            [
                "Continue the same task. Slipstream verification has not accepted completion.",
                f"GOAL:\n{goal}",
                "UNMET / QUESTIONED CRITERIA:\n" + ("\n".join(f"- {c}" for c in gate.unmet_criteria) or "- See verifier reason"),
                f"VERIFIER REASON:\n{gate.reason}",
                "FAILED DETERMINISTIC CHECKS:\n" + ("\n".join(f"- {name}" for name in failed) or "- none"),
                "Make concrete workspace progress, run the relevant checks, and report what changed.",
            ]
        )
