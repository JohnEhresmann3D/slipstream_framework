from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from .backends.base import AgentBackend, AgentRequest, AgentResult, BackendError
from .evidence import EvidenceBundle


class Verdict(str, Enum):
    MET = "MET"
    PROGRESSING = "PROGRESSING"
    STUCK = "STUCK"


@dataclass
class GateResult:
    verdict: Verdict
    reason: str
    unmet_criteria: list[str] = field(default_factory=list)
    raw: Any = None
    cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "reason": self.reason,
            "unmet_criteria": list(self.unmet_criteria),
            "raw": self.raw if isinstance(self.raw, (dict, list, str, int, float, bool, type(None))) else repr(self.raw),
            "cost_usd": self.cost_usd,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GateResult":
        return cls(
            verdict=Verdict(data["verdict"]),
            reason=data.get("reason", ""),
            unmet_criteria=list(data.get("unmet_criteria", [])),
            raw=data.get("raw"),
            cost_usd=data.get("cost_usd"),
        )


class RunHistory(Protocol):
    def summary(self) -> str: ...


class Verifier(Protocol):
    def evaluate(
        self,
        goal: str,
        criteria: list[str],
        evidence: EvidenceBundle,
        worker_result: AgentResult,
        history: Any,
        workspace: Path,
    ) -> GateResult: ...


class BackendVerifier:
    """Read-only semantic verifier backed by any AgentBackend.

    Deterministic evidence has veto power: a required failed check prevents MET
    even if the verifier model says the task is complete.
    """

    def __init__(self, backend: AgentBackend, timeout_sec: int = 300, isolate_workspace: bool = True):
        self.backend = backend
        self.timeout_sec = timeout_sec
        self.isolate_workspace = isolate_workspace

    @staticmethod
    def _snapshot_workspace(source: Path, destination: Path) -> None:
        ignored = shutil.ignore_patterns(
            ".git", ".slipstream", ".pytest_cache", "__pycache__",
            ".venv", "venv", "node_modules", "dist", "build",
            # Generated Unreal Engine directories can contain multiple gigabytes
            # and are never useful to a read-only semantic verifier.
            "Binaries", "DerivedDataCache", "Intermediate", "Saved", ".vs", ".vscode",
        )
        shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=True, ignore=ignored)

    @staticmethod
    def _copy_artifacts(source: Path, destination: Path, evidence: EvidenceBundle) -> None:
        # Collected artifacts may live in directories the snapshot skips
        # (e.g. .slipstream/); the verifier still needs to read them in full.
        root = source.resolve()
        for rel in evidence.artifacts:
            src = (source / rel).resolve()
            if not src.is_file() or not src.is_relative_to(root):
                continue
            dst = destination / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    @staticmethod
    def _render_evidence(evidence: EvidenceBundle) -> str:
        checks = []
        for c in evidence.checks:
            checks.append(
                {
                    "name": c.name,
                    "required": c.required,
                    "passed": c.passed,
                    "exit_code": c.exit_code,
                    "stdout_tail": c.stdout[-3000:],
                    "stderr_tail": c.stderr[-3000:],
                }
            )
        return json.dumps(
            {
                "workspace_revision": evidence.workspace_revision,
                "diff_summary": evidence.diff_summary,
                "changed_files": evidence.changed_files,
                "checks": checks,
                "artifacts": [str(p) for p in evidence.artifacts],
                "facts": evidence.facts,
            },
            indent=2,
        )

    @staticmethod
    def _parse(text: str) -> GateResult:
        text = text.strip()
        # Some RPC/model combinations echo prompt material containing other JSON
        # before the requested verdict. Decode every possible JSON object and use
        # the final object that actually carries a valid verdict.
        decoder = json.JSONDecoder()
        verdict_payloads: list[dict[str, Any]] = []
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                payload, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            try:
                Verdict(str(payload.get("verdict", "")).upper())
            except ValueError:
                continue
            verdict_payloads.append(payload)

        if verdict_payloads:
            payload = verdict_payloads[-1]
            verdict = Verdict(str(payload["verdict"]).upper())
            reason = str(payload.get("reason", ""))
            unmet = payload.get("unmet_criteria", [])
            if not isinstance(unmet, list):
                unmet = []
            return GateResult(verdict, reason, [str(v) for v in unmet], raw=payload)

        upper = text.upper()
        verdict = Verdict.STUCK
        if "MET" in upper and "PROGRESSING" not in upper:
            verdict = Verdict.MET
        elif "PROGRESSING" in upper:
            verdict = Verdict.PROGRESSING
        return GateResult(verdict, text[:2000] or "Verifier returned no parseable result", raw=text)

    def evaluate(
        self,
        goal: str,
        criteria: list[str],
        evidence: EvidenceBundle,
        worker_result: AgentResult,
        history: Any,
        workspace: Path,
    ) -> GateResult:
        prompt = f"""You are Slipstream's independent verification gate.
Judge the goal only from acceptance criteria and evidence. Worker prose is context, not proof.
Return ONLY JSON with keys: verdict (MET|PROGRESSING|STUCK), reason, unmet_criteria (array of strings).

GOAL:
{goal}

ACCEPTANCE CRITERIA:
{json.dumps(criteria, indent=2)}

DETERMINISTIC EVIDENCE:
{self._render_evidence(evidence)}

WORKER REPORT (not proof):
{worker_result.text[-8000:]}
"""
        try:
            if self.isolate_workspace:
                with tempfile.TemporaryDirectory(prefix="slipstream-verify-") as tmp:
                    verify_workspace = Path(tmp) / "workspace"
                    self._snapshot_workspace(Path(workspace), verify_workspace)
                    self._copy_artifacts(Path(workspace), verify_workspace, evidence)
                    try:
                        result = self.backend.run(
                            AgentRequest(
                                prompt=prompt,
                                workspace=verify_workspace,
                                allowed_tools=["Read", "Grep", "Glob"],
                                timeout_sec=self.timeout_sec,
                                metadata={"role": "verifier", "read_only": True, "isolated_snapshot": True},
                            )
                        )
                    finally:
                        # Resident backends retain their workspace as the child
                        # process working directory. Windows cannot remove the
                        # temporary snapshot until that process is closed.
                        self.backend.close()
            else:
                result = self.backend.run(
                    AgentRequest(
                        prompt=prompt,
                        workspace=workspace,
                        allowed_tools=["Read", "Grep", "Glob"],
                        timeout_sec=self.timeout_sec,
                        metadata={"role": "verifier", "read_only": True, "isolated_snapshot": False},
                    )
                )
        except (BackendError, OSError) as exc:
            return GateResult(Verdict.STUCK, f"Verifier infrastructure error: {exc}", list(criteria), raw=repr(exc))

        gate = self._parse(result.text)
        gate.cost_usd = result.cost_usd
        if evidence.has_required_failure and gate.verdict is Verdict.MET:
            failed = [c.name for c in evidence.checks if c.required and c.passed is False]
            return GateResult(
                Verdict.PROGRESSING,
                "Deterministic evidence vetoed MET because required checks failed: " + ", ".join(failed),
                gate.unmet_criteria or failed,
                raw=gate.raw,
                cost_usd=gate.cost_usd,
            )
        return gate
