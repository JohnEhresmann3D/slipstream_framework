"""`slipstream` command line: validate config, preview prompts, drive workflows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import ConfigError, find_project_root, load_project, render_static_context
from .loop import cli as loop_cli
from .loop.backends.factory import BackendConfig, make_backend
from .loop.evidence import CheckSpec
from .loop.verification import BackendVerifier
from .workflow import EngineLimits, WorkflowEngine, WorkflowError, WorkflowState

BACKENDS = ["pi", "claude-code", "openai"]


def _project(args: argparse.Namespace):
    root = args.project or find_project_root(args.root or Path.cwd())
    return load_project(root)


def _print_issues(issues) -> None:
    for issue in issues:
        print(str(issue), file=sys.stderr)


# ------------------------------------------------------------------ commands


def cmd_validate(args: argparse.Namespace) -> int:
    root = args.project or find_project_root(args.root or Path.cwd())
    project = load_project(root, strict=False)
    _print_issues(project.issues)
    print(
        f"{root}: {len(project.personas)} personas, {len(project.skills)} skills, "
        f"{len(project.workflows)} workflows, {len(project.errors)} errors, "
        f"{len(project.warnings)} warnings"
    )
    return 1 if project.errors else 0


def cmd_prompt(args: argparse.Namespace) -> int:
    project = _project(args)
    phase = None
    if args.phase:
        workflow = project.workflows[args.workflow or project.default_workflow]
        phase = workflow.phase(args.phase)
    persona = args.persona
    if persona is None:
        if phase is None or phase.agents == "all_assigned":
            raise SystemExit("--persona is required here")
        persona = phase.agents[0]
    text = render_static_context(project, persona, phase, args.consult or ())
    print(text)
    print(f"\n[{len(text)} chars, ~{len(text) // 4} tokens]", file=sys.stderr)
    return 0


def _launch_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "backend": args.backend,
        "backend_executable": args.backend_executable,
        "backend_model": args.backend_model,
        "backend_provider": args.backend_provider,
        "verifier_backend": args.verifier_backend,
        "verifier_executable": args.verifier_executable,
        "verifier_model": args.verifier_model,
        "verifier_provider": args.verifier_provider,
        "checks": [[c.name, list(c.command)] for c in args.check or []],
        "max_cost_usd": args.max_cost_usd,
        "timeout_sec": args.timeout_sec,
    }


def _merge_launch(saved: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Saved launch settings, overridden by anything given on this command line."""
    merged = dict(saved)
    for key, value in _launch_from_args(args).items():
        if value not in (None, []):
            merged[key] = value
    merged.setdefault("backend", "pi")
    return merged


def _engine(args: argparse.Namespace, launch: dict[str, Any] | None) -> tuple[WorkflowEngine, list]:
    project = _project(args)
    workspace = args.root or Path.cwd()
    closers: list = []
    worker = verifier = None
    if launch is not None:
        kind = launch.get("backend") or "pi"
        worker = make_backend(BackendConfig(kind, loop_cli._backend_options(
            kind, launch.get("backend_executable"), launch.get("backend_model"),
            launch.get("backend_provider"), None,
        )))
        verifier_kind = launch.get("verifier_backend") or kind
        verifier_backend = make_backend(BackendConfig(verifier_kind, loop_cli._backend_options(
            verifier_kind,
            launch.get("verifier_executable") or (launch.get("backend_executable") if verifier_kind == kind else None),
            launch.get("verifier_model") or (launch.get("backend_model") if verifier_kind == kind else None),
            launch.get("verifier_provider") or (launch.get("backend_provider") if verifier_kind == kind else None),
            None,
        )))
        verifier = BackendVerifier(verifier_backend)
        closers = [worker, verifier_backend]
    checks = [CheckSpec(name, tuple(command)) for name, command in (launch or {}).get("checks", [])]
    engine = WorkflowEngine(
        project,
        workspace,
        worker=worker,
        verifier=verifier,
        checks=checks,
        limits=EngineLimits(
            max_cost_usd=(launch or {}).get("max_cost_usd"),
            per_call_timeout_sec=(launch or {}).get("timeout_sec") or 900,
        ),
    )
    return engine, closers


def _report(state: WorkflowState) -> int:
    print(json.dumps(_summary(state), indent=2))
    if state.status.value == "AWAITING_APPROVAL":
        gate = state.pending_gate()
        print(
            f"\nWaiting on gate '{gate.gate_id}'. Review the artifact, then run:\n"
            f"  slipstream workflow approve {state.workflow_run_id} --continue\n"
            f"  slipstream workflow reject {state.workflow_run_id} --note \"what to change\" --continue",
            file=sys.stderr,
        )
    return {"DONE": 0, "AWAITING_APPROVAL": 0, "READY": 0}.get(state.status.value, 2)


def _summary(state: WorkflowState) -> dict[str, Any]:
    gate = state.pending_gate()
    return {
        "workflow_run_id": state.workflow_run_id,
        "workflow": state.workflow,
        "status": state.status.value,
        "reason": state.reason,
        "current_phase": state.current.name if state.current else None,
        "pending_gate": gate.gate_id if gate else None,
        "total_cost_usd": round(state.total_cost_usd, 6),
        "phases": [
            {"name": r.name, "status": r.status.value, "attempts": r.attempts, "artifact": r.artifact}
            for r in state.phases
        ],
    }


def _with_engine(args: argparse.Namespace, launch: dict[str, Any] | None, action) -> int:
    engine, closers = _engine(args, launch)
    try:
        return _report(action(engine))
    finally:
        for backend in closers:
            backend.close()


def cmd_workflow_start(args: argparse.Namespace) -> int:
    launch = _merge_launch({}, args)
    return _with_engine(args, launch, lambda e: e.start(
        args.task, workflow_id=args.workflow, personas=args.persona,
        workflow_run_id=args.id, launch=launch,
    ))


def cmd_workflow_resume(args: argparse.Namespace) -> int:
    saved = _engine(args, None)[0].status(args.id).launch
    return _with_engine(args, _merge_launch(saved, args), lambda e: e.resume(args.id))


def cmd_workflow_status(args: argparse.Namespace) -> int:
    engine, _ = _engine(args, None)
    if args.id:
        print(json.dumps(_summary(engine.status(args.id)), indent=2))
    else:
        for state in engine.list_runs():
            current = state.current.name if state.current else "-"
            print(f"{state.workflow_run_id}\t{state.status.value}\t{current}\t{state.reason}")
    return 0


def _decide(args: argparse.Namespace, decide) -> int:
    engine, _ = _engine(args, None)
    state = decide(engine)
    if not args.continue_:
        return _report(state)
    return _with_engine(args, _merge_launch(state.launch, args), lambda e: e.resume(args.id))


def cmd_workflow_approve(args: argparse.Namespace) -> int:
    return _decide(args, lambda e: e.approve(args.id, args.gate, note=args.note or "", by=args.by))


def cmd_workflow_reject(args: argparse.Namespace) -> int:
    return _decide(args, lambda e: e.reject(args.id, note=args.note, gate_id=args.gate, by=args.by))


# -------------------------------------------------------------------- parser


def _add_location(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", type=Path, help="Workspace the agents work in (default: cwd)")
    p.add_argument("--project", type=Path, help="Directory with slipstream.yaml (default: found from --root)")


def _add_backend(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("backends (saved with the run; resume reuses them)")
    g.add_argument("--backend", choices=BACKENDS)
    g.add_argument("--backend-executable")
    g.add_argument("--backend-model", help="e.g. openai-codex/gpt-6-astra for pi")
    g.add_argument("--backend-provider")
    g.add_argument("--verifier-backend", choices=BACKENDS)
    g.add_argument("--verifier-executable")
    g.add_argument("--verifier-model")
    g.add_argument("--verifier-provider")
    g.add_argument("--check", action="append", type=loop_cli._parse_check, default=[],
                   help="NAME=COMMAND, run in phases with run_checks: true")
    g.add_argument("--max-cost-usd", type=float, help="Budget for the whole workflow run")
    g.add_argument("--timeout-sec", type=int, help="Per agent call timeout")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="slipstream", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="Validate personas, skills, and workflows")
    _add_location(p)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("prompt", help="Print the static prompt context for a persona/phase")
    _add_location(p)
    p.add_argument("--persona")
    p.add_argument("--workflow")
    p.add_argument("--phase")
    p.add_argument("--consult", action="append", help="Persona to include as a consulted perspective")
    p.set_defaults(func=cmd_prompt)

    sub.add_parser("run", help="Run the single-goal operator loop (see `slipstream run --help`)", add_help=False)

    wf = sub.add_parser("workflow", help="Start and drive phase/gate workflows")
    wsub = wf.add_subparsers(dest="workflow_command", required=True)

    p = wsub.add_parser("start", help="Start a workflow run")
    _add_location(p)
    _add_backend(p)
    p.add_argument("--task", required=True)
    p.add_argument("--workflow", help="Workflow name (default from slipstream.yaml)")
    p.add_argument("--persona", action="append", help="Assigned persona (repeatable)")
    p.add_argument("--id", help="Workflow run id (default: generated)")
    p.set_defaults(func=cmd_workflow_start)

    p = wsub.add_parser("resume", help="Continue a stopped or crashed workflow run")
    _add_location(p)
    _add_backend(p)
    p.add_argument("id")
    p.set_defaults(func=cmd_workflow_resume)

    p = wsub.add_parser("status", help="Show one workflow run, or list all")
    _add_location(p)
    p.add_argument("id", nargs="?")
    p.set_defaults(func=cmd_workflow_status)

    for name, func, note_required in (
        ("approve", cmd_workflow_approve, False),
        ("reject", cmd_workflow_reject, True),
    ):
        p = wsub.add_parser(name, help=f"{name.capitalize()} the pending gate")
        _add_location(p)
        _add_backend(p)
        p.add_argument("id")
        p.add_argument("--gate", help="Gate id (default: the pending gate)")
        p.add_argument("--note", required=note_required)
        p.add_argument("--by", help="Who made the decision (recorded in the audit log)")
        p.add_argument("--continue", dest="continue_", action="store_true", help="Resume the run immediately")
        p.set_defaults(func=func)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Prompts and constitutions contain non-ASCII text; Windows consoles
    # default to a legacy code page that cannot encode it.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["run"]:
        return loop_cli.main(argv[1:])
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        _print_issues(exc.issues)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (WorkflowError, FileNotFoundError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
