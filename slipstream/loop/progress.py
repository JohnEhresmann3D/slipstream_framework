from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .evidence import EvidenceBundle


@dataclass(frozen=True)
class ProgressSnapshot:
    workspace_hash: str | None
    diff_hash: str | None
    changed_files: tuple[str, ...]
    passed_checks: int
    failed_checks: int
    unmet_criteria: tuple[str, ...]
    artifact_hashes: tuple[str, ...]
    prose_hash: str | None = None

    @classmethod
    def from_evidence(
        cls,
        evidence: EvidenceBundle,
        unmet_criteria: tuple[str, ...] = (),
        worker_text: str | None = None,
    ) -> "ProgressSnapshot":
        configured_hashes = evidence.facts.get("artifact_hashes") if isinstance(evidence.facts, dict) else None
        if isinstance(configured_hashes, dict):
            artifact_hashes = tuple(
                f"{name}:{configured_hashes[name]}" for name in sorted(configured_hashes)
            )
        else:
            artifact_hashes = tuple(
                hashlib.sha256(str(p).encode("utf-8")).hexdigest() for p in sorted(evidence.artifacts, key=str)
            )
        prose_hash = None
        if worker_text:
            normalized = " ".join(worker_text.lower().split())
            prose_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return cls(
            workspace_hash=evidence.workspace_hash,
            diff_hash=evidence.diff_hash,
            changed_files=tuple(sorted(evidence.changed_files)),
            passed_checks=evidence.passed_checks,
            failed_checks=evidence.failed_checks,
            unmet_criteria=tuple(sorted(unmet_criteria)),
            artifact_hashes=artifact_hashes,
            prose_hash=prose_hash,
        )

    def to_dict(self) -> dict:
        return {
            "workspace_hash": self.workspace_hash,
            "diff_hash": self.diff_hash,
            "changed_files": list(self.changed_files),
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "unmet_criteria": list(self.unmet_criteria),
            "artifact_hashes": list(self.artifact_hashes),
            "prose_hash": self.prose_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProgressSnapshot":
        return cls(
            workspace_hash=data.get("workspace_hash"),
            diff_hash=data.get("diff_hash"),
            changed_files=tuple(data.get("changed_files", [])),
            passed_checks=int(data.get("passed_checks", 0)),
            failed_checks=int(data.get("failed_checks", 0)),
            unmet_criteria=tuple(data.get("unmet_criteria", [])),
            artifact_hashes=tuple(data.get("artifact_hashes", [])),
            prose_hash=data.get("prose_hash"),
        )


@dataclass(frozen=True)
class ProgressDelta:
    has_progress: bool
    reasons: tuple[str, ...]
    prose_changed: bool


class ProgressDetector:
    """Evidence is primary; worker prose is a secondary diagnostic only."""

    def compare(self, previous: ProgressSnapshot | None, current: ProgressSnapshot) -> ProgressDelta:
        if previous is None:
            return ProgressDelta(True, ("first_snapshot",), True)

        reasons: list[str] = []
        if current.workspace_hash != previous.workspace_hash:
            reasons.append("workspace_changed")
        if current.diff_hash != previous.diff_hash:
            reasons.append("diff_changed")
        if current.changed_files != previous.changed_files:
            reasons.append("changed_file_set_changed")
        if current.passed_checks > previous.passed_checks:
            reasons.append("more_checks_passing")
        if current.failed_checks < previous.failed_checks:
            reasons.append("fewer_checks_failing")
        if current.unmet_criteria != previous.unmet_criteria:
            reasons.append("criteria_status_changed")
        if current.artifact_hashes != previous.artifact_hashes:
            reasons.append("artifacts_changed")

        prose_changed = current.prose_hash != previous.prose_hash
        return ProgressDelta(bool(reasons), tuple(reasons), prose_changed)
