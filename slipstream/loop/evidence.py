from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class CheckSpec:
    name: str
    command: tuple[str, ...]
    timeout_sec: int = 120
    required: bool = True


@dataclass
class CheckResult:
    name: str
    command: list[str] | None
    passed: bool | None
    exit_code: int | None
    stdout: str
    stderr: str
    duration_sec: float
    required: bool = True


@dataclass
class EvidenceBundle:
    workspace_revision: str | None
    diff_summary: str
    changed_files: list[str]
    checks: list[CheckResult]
    artifacts: list[Path]
    facts: dict[str, Any]
    workspace_hash: str | None = None
    diff_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["artifacts"] = [str(p) for p in self.artifacts]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceBundle":
        return cls(
            workspace_revision=data.get("workspace_revision"),
            diff_summary=data.get("diff_summary", ""),
            changed_files=list(data.get("changed_files", [])),
            checks=[CheckResult(**item) for item in data.get("checks", [])],
            artifacts=[Path(p) for p in data.get("artifacts", [])],
            facts=dict(data.get("facts", {})),
            workspace_hash=data.get("workspace_hash"),
            diff_hash=data.get("diff_hash"),
        )

    @property
    def has_required_failure(self) -> bool:
        return any(c.required and c.passed is False for c in self.checks)

    @property
    def passed_checks(self) -> int:
        return sum(c.passed is True for c in self.checks)

    @property
    def failed_checks(self) -> int:
        return sum(c.passed is False for c in self.checks)


class EvidenceCollector:
    """Collects repository state and deterministic command results.

    The collector never trusts the worker's prose as proof. It inspects the
    workspace directly and runs configured checks itself.
    """

    def __init__(
        self,
        checks: Iterable[CheckSpec] = (),
        artifact_globs: Iterable[str] = (),
        max_output_chars: int = 20_000,
        ignore_prefixes: Iterable[str] = (".slipstream/",),
        artifact_excerpt_chars: int = 8_000,
    ):
        self.checks = tuple(checks)
        self.artifact_globs = tuple(artifact_globs)
        self.max_output_chars = max_output_chars
        self.artifact_excerpt_chars = artifact_excerpt_chars
        self.ignore_prefixes = tuple(ignore_prefixes)

    @staticmethod
    def _run_git(workspace: Path, *args: str) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=workspace,
                text=True,
                capture_output=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return 127, "", "git unavailable"
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    @staticmethod
    def _sha256_text(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()

    def _workspace_hash(self, workspace: Path, changed_files: list[str]) -> str | None:
        if not changed_files:
            return None
        digest = hashlib.sha256()
        for rel in sorted(changed_files):
            path = workspace / rel
            digest.update(rel.encode("utf-8", errors="replace"))
            if path.is_file():
                try:
                    digest.update(path.read_bytes())
                except OSError:
                    digest.update(b"<unreadable>")
            elif not path.exists():
                digest.update(b"<deleted>")
        return digest.hexdigest()

    def _collect_git(self, workspace: Path) -> tuple[str | None, str, list[str], str | None]:
        rev_code, revision, _ = self._run_git(workspace, "rev-parse", "HEAD")
        workspace_revision = revision if rev_code == 0 else None

        status_code, status, _ = self._run_git(workspace, "status", "--porcelain", "--untracked-files=all")
        changed_files: list[str] = []
        if status_code == 0:
            for line in status.splitlines():
                if len(line) < 4:
                    continue
                candidate = line[3:]
                if " -> " in candidate:
                    candidate = candidate.split(" -> ", 1)[1]
                candidate = candidate.strip()
                if not any(candidate == prefix.rstrip("/") or candidate.startswith(prefix) for prefix in self.ignore_prefixes):
                    changed_files.append(candidate)

        diff_args = ["diff", "--stat", "HEAD", "--", "."]
        for prefix in self.ignore_prefixes:
            diff_args.append(f":(exclude){prefix}**")
        diff_code, diff_summary, _ = self._run_git(workspace, *diff_args)
        if diff_code != 0:
            diff_summary = ""
        # Include untracked files in the summary so progress isn't invisible.
        untracked = [p for p in changed_files if (workspace / p).exists() and p not in diff_summary]
        if untracked:
            suffix = "\n".join(f"untracked: {p}" for p in untracked)
            diff_summary = (diff_summary + "\n" + suffix).strip()
        diff_hash = self._sha256_text(diff_summary) if diff_summary or changed_files else None
        return workspace_revision, diff_summary, sorted(set(changed_files)), diff_hash

    def _run_check(self, workspace: Path, spec: CheckSpec) -> CheckResult:
        started = time.monotonic()
        try:
            proc = subprocess.run(
                list(spec.command),
                cwd=workspace,
                text=True,
                capture_output=True,
                timeout=spec.timeout_sec,
                env=os.environ.copy(),
            )
            duration = time.monotonic() - started
            return CheckResult(
                name=spec.name,
                command=list(spec.command),
                passed=proc.returncode == 0,
                exit_code=proc.returncode,
                stdout=proc.stdout[-self.max_output_chars :],
                stderr=proc.stderr[-self.max_output_chars :],
                duration_sec=duration,
                required=spec.required,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - started
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            return CheckResult(
                name=spec.name,
                command=list(spec.command),
                passed=False,
                exit_code=None,
                stdout=stdout[-self.max_output_chars :],
                stderr=(stderr + f"\nTimed out after {spec.timeout_sec}s")[-self.max_output_chars :],
                duration_sec=duration,
                required=spec.required,
            )
        except FileNotFoundError as exc:
            duration = time.monotonic() - started
            return CheckResult(
                name=spec.name,
                command=list(spec.command),
                passed=False,
                exit_code=127,
                stdout="",
                stderr=str(exc),
                duration_sec=duration,
                required=spec.required,
            )

    def collect(self, workspace: Path, criteria: list[str] | None = None) -> EvidenceBundle:
        workspace = Path(workspace)
        revision, diff_summary, changed_files, diff_hash = self._collect_git(workspace)
        checks = [self._run_check(workspace, spec) for spec in self.checks]
        artifacts: list[Path] = []
        for pattern in self.artifact_globs:
            for path in workspace.glob(pattern):
                if path.is_file():
                    artifacts.append(path.relative_to(workspace))

        workspace_hash = self._workspace_hash(workspace, changed_files)
        artifact_hashes: dict[str, str] = {}
        # Excerpts let a verifier judge artifact content even when its
        # isolated snapshot excludes the directory the artifact lives in.
        artifact_excerpts: dict[str, str] = {}
        for rel in artifacts:
            path = workspace / rel
            try:
                data = path.read_bytes()
            except OSError:
                artifact_hashes[str(rel)] = "<unreadable>"
                continue
            artifact_hashes[str(rel)] = hashlib.sha256(data).hexdigest()
            if self.artifact_excerpt_chars > 0:
                text = data.decode("utf-8", errors="replace")
                excerpt = text[: self.artifact_excerpt_chars]
                if len(text) > len(excerpt):
                    excerpt += f"\n...[truncated, {len(text) - len(excerpt)} more chars]"
                artifact_excerpts[str(rel)] = excerpt

        facts = {
            "criteria_count": len(criteria or []),
            "required_checks_passed": all(c.passed is True for c in checks if c.required) if checks else None,
            "changed_file_count": len(changed_files),
            "artifact_hashes": artifact_hashes,
            "artifact_excerpts": artifact_excerpts,
        }
        return EvidenceBundle(
            workspace_revision=revision,
            diff_summary=diff_summary,
            changed_files=changed_files,
            checks=checks,
            artifacts=sorted(set(artifacts), key=str),
            facts=facts,
            workspace_hash=workspace_hash,
            diff_hash=diff_hash,
        )

    @staticmethod
    def dump(bundle: EvidenceBundle, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(bundle.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def load(path: Path) -> EvidenceBundle:
        return EvidenceBundle.from_dict(json.loads(path.read_text(encoding="utf-8")))
