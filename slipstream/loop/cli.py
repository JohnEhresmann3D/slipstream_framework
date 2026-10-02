from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

from .backends.factory import BackendConfig, make_backend
from .evidence import CheckSpec, EvidenceCollector
from .guardrails import GuardrailConfig
from .operator import Operator
from .verification import BackendVerifier
from .workspaces import DirectWorkspaceManager, GitWorktreeWorkspaceManager


def _backend_options(kind: str, executable: str | None, model: str | None, provider: str | None, reserve: float | None) -> dict:
    options: dict = {}
    if executable:
        options["executable"] = executable
    if model:
        options["model"] = model
    if reserve is not None:
        options["estimated_max_call_cost_usd"] = reserve
    if kind.lower() in {"pi", "pi.dev", "pi-dev"} and provider:
        options["provider"] = provider
    return options


def _parse_check(value: str) -> CheckSpec:
    if "=" not in value:
        raise argparse.ArgumentTypeError("check must be NAME=COMMAND")
    name, command = value.split("=", 1)
    parts = tuple(shlex.split(command))
    if not name.strip() or not parts:
        raise argparse.ArgumentTypeError("check must be NAME=COMMAND")
    return CheckSpec(name.strip(), parts)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run the vendor-neutral Slipstream operator")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--goal")
    p.add_argument("--criterion", action="append", dest="criteria")
    p.add_argument("--backend", default="pi", choices=["pi", "claude-code", "openai"])
    p.add_argument("--backend-executable")
    p.add_argument("--backend-model")
    p.add_argument("--backend-provider")
    p.add_argument("--backend-call-reserve", type=float)
    p.add_argument("--verifier-backend", choices=["pi", "claude-code", "openai"])
    p.add_argument("--verifier-executable")
    p.add_argument("--verifier-model")
    p.add_argument("--verifier-provider")
    p.add_argument("--verifier-call-reserve", type=float)
    p.add_argument("--check", action="append", type=_parse_check, default=[])
    p.add_argument("--artifact", action="append", default=[])
    p.add_argument("--max-iterations", type=int, default=8)
    p.add_argument("--max-cost-usd", type=float)
    p.add_argument("--max-stuck-iterations", type=int, default=2)
    p.add_argument("--timeout-sec", type=int, default=900)
    p.add_argument("--max-turns", type=int)
    p.add_argument("--worktree", action="store_true", help="Run in an isolated git worktree")
    p.add_argument("--require-capability", action="append", default=[])
    p.add_argument("--resume")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.resume:
        if not args.goal:
            parser.error("--goal is required unless --resume is used")
        if not args.criteria:
            parser.error("at least one --criterion is required unless --resume is used")

    worker = make_backend(
        BackendConfig(
            args.backend,
            _backend_options(
                args.backend,
                args.backend_executable,
                args.backend_model,
                args.backend_provider,
                args.backend_call_reserve,
            ),
        )
    )
    verifier_kind = args.verifier_backend or args.backend
    verifier_backend = make_backend(
        BackendConfig(
            verifier_kind,
            _backend_options(
                verifier_kind,
                args.verifier_executable,
                args.verifier_model,
                args.verifier_provider,
                args.verifier_call_reserve,
            ),
        )
    )
    operator = Operator(
        root=args.root,
        worker=worker,
        verifier=BackendVerifier(verifier_backend),
        evidence_collector=EvidenceCollector(args.check, args.artifact),
        guardrails=GuardrailConfig(
            max_iterations=args.max_iterations,
            max_cost_usd=args.max_cost_usd,
            max_stuck_iterations=args.max_stuck_iterations,
            per_call_timeout_sec=args.timeout_sec,
            max_turns=args.max_turns,
        ),
        workspace_manager=GitWorktreeWorkspaceManager() if args.worktree else DirectWorkspaceManager(),
        required_worker_capabilities=set(args.require_capability),
    )
    try:
        result = operator.resume(args.resume) if args.resume else operator.run(args.goal, args.criteria or [])
        print(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "status": result.status.value,
                    "reason": result.reason,
                    "iterations": result.iterations,
                    "total_cost_usd": result.total_cost_usd,
                    "budget_status": result.budget_status,
                    "workspace": str(result.workspace),
                    "last_gate": result.last_gate.to_dict() if result.last_gate else None,
                },
                indent=2,
            )
        )
        return 0 if result.status.value == "DONE" else 2
    finally:
        worker.close()
        verifier_backend.close()


if __name__ == "__main__":
    raise SystemExit(main())
