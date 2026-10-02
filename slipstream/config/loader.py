from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import (
    ALL_ASSIGNED,
    PHASE_KNOWN_KEYS,
    PHASE_MODES,
    TRANSITION_REQUIREMENTS,
    Issue,
    Persona,
    Phase,
    Project,
    Skill,
    Transition,
    Workflow,
)

CONFIG_FILE = "slipstream.yaml"


class ConfigError(RuntimeError):
    """Raised when a project cannot be loaded or fails validation."""

    def __init__(self, message: str, issues: list[Issue] | None = None):
        super().__init__(message)
        self.issues = issues or []


def find_project_root(start: Path) -> Path:
    """Walk up from `start` to the nearest directory containing slipstream.yaml."""
    start = Path(start).resolve()
    for candidate in (start, *start.parents):
        if (candidate / CONFIG_FILE).is_file():
            return candidate
    raise ConfigError(f"No {CONFIG_FILE} found in {start} or any parent directory")


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        return [str(value)]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            # Workflow lists sometimes use `- key: "description"` entries.
            if isinstance(item, dict):
                out.extend(f"{k}: {v}" for k, v in item.items())
            else:
                out.append(str(item))
        return out
    return [str(value)]


def _path(root: Path, value: Any, default: str) -> Path:
    return (root / str(value or default)).resolve()


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _load_skills(root: Path, skill_dirs: dict[str, Path], issues: list[Issue]) -> dict[str, Skill]:
    skills: dict[str, Skill] = {}
    for category, directory in skill_dirs.items():
        if not directory.is_dir():
            issues.append(Issue("error", _rel(root, directory), "skill directory does not exist"))
            continue
        for path in sorted(directory.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            where = _rel(root, path)
            data = _read_yaml(path)
            if not isinstance(data, dict):
                issues.append(Issue("error", where, "skill file must be a mapping"))
                continue
            for key in ("name", "description"):
                if not data.get(key):
                    issues.append(Issue("error", where, f"missing required field {key!r}"))
            skill_id = str(data.get("name") or path.stem)
            if skill_id != path.stem:
                issues.append(Issue("warning", where, f"name {skill_id!r} differs from file name {path.stem!r}"))
            if skill_id in skills:
                issues.append(Issue("error", where, f"duplicate skill id {skill_id!r}"))
            hitl = data.get("hitl") if isinstance(data.get("hitl"), dict) else {}
            skills[skill_id] = Skill(
                id=skill_id,
                category=str(data.get("category") or category),
                description=" ".join(str(data.get("description", "")).split()),
                path=path,
                allows=_str_list(data.get("allows")),
                prohibits=_str_list(data.get("prohibits")),
                produces=_str_list(data.get("produces")),
                output_requirements=_str_list(data.get("output_requirements")),
                failure_conditions=_str_list(data.get("failure_conditions")),
                hitl_required_for=_str_list(hitl.get("required_for")),
            )
    return skills


def _load_tools(tools_dir: Path) -> set[str]:
    tools: set[str] = set()
    if not tools_dir.is_dir():
        return tools
    for path in sorted(tools_dir.glob("*.yaml")):
        data = _read_yaml(path)
        if not isinstance(data, dict):
            continue
        if data.get("name"):
            tools.add(str(data["name"]))
        if isinstance(data.get("tools"), dict):
            tools.update(str(k) for k in data["tools"])
    return tools


def _load_personas(
    root: Path,
    personas_dir: Path,
    role_dir: Path,
    skills: dict[str, Skill],
    tools: set[str],
    issues: list[Issue],
) -> dict[str, Persona]:
    personas: dict[str, Persona] = {}
    if not personas_dir.is_dir():
        issues.append(Issue("error", _rel(root, personas_dir), "persona directory does not exist"))
        return personas
    for path in sorted(personas_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        where = _rel(root, path)
        data = _read_yaml(path)
        if not isinstance(data, dict):
            issues.append(Issue("error", where, "persona file must be a mapping"))
            continue
        for key in ("name", "role", "skills_required", "voice"):
            if not data.get(key):
                issues.append(Issue("error", where, f"missing required field {key!r}"))
        persona_id = path.stem
        required = _str_list(data.get("skills_required"))
        optional = _str_list(data.get("skills_optional"))
        for skill in required + optional:
            if skill not in skills:
                issues.append(Issue("error", where, f"references unknown skill {skill!r}"))
        tools_access = _str_list(data.get("tools_access"))
        for tool in tools_access:
            if tool not in tools:
                issues.append(Issue("warning", where, f"tool {tool!r} has no definition under tools/"))

        constitution = data.get("constitution") if isinstance(data.get("constitution"), dict) else {}
        role_path = (
            _path(root, constitution["role"], "")
            if constitution.get("role")
            else role_dir / f"{persona_id}_constitution.md"
        )
        if not role_path.is_file():
            issues.append(Issue("warning", where, f"role constitution not found: {_rel(root, role_path)}"))

        research = data.get("research_mandate") if isinstance(data.get("research_mandate"), dict) else {}
        raw_triggers = research.get("triggers")
        triggers = [t for t in raw_triggers if isinstance(t, dict)] if isinstance(raw_triggers, list) else []
        responsibilities = data.get("responsibilities") if isinstance(data.get("responsibilities"), dict) else {}
        voice = data.get("voice") if isinstance(data.get("voice"), dict) else {}
        personas[persona_id] = Persona(
            id=persona_id,
            name=str(data.get("name", persona_id)),
            role=str(data.get("role", "")),
            path=path,
            skills_required=required,
            skills_optional=optional,
            tools_access=tools_access,
            voice=voice,
            responsibilities={str(k): _str_list(v) for k, v in responsibilities.items()},
            research_triggers=triggers,
            role_constitution_path=role_path,
        )
    return personas


def _phase_shape_issues(raw: dict[str, Any], at: str) -> tuple[dict[str, Any], list[Issue]]:
    """Check scalar types so bad YAML becomes an Issue instead of a crash.

    Returns a copy of the phase with invalid values dropped.
    """
    data = dict(raw)
    issues: list[Issue] = []
    for key in ("gate_id", "gate_description", "mode", "output", "name", "description"):
        if key in data and data[key] is not None and not isinstance(data[key], (str, int, float)):
            issues.append(Issue("error", at, f"{key} must be a string"))
            data.pop(key)
    for key in ("hitl_gate", "run_checks"):
        if key in data and not isinstance(data[key], bool):
            issues.append(Issue("error", at, f"{key} must be true or false"))
            data.pop(key)
    breaker = data.get("circuit_breaker")
    if breaker is not None:
        if not isinstance(breaker, dict):
            issues.append(Issue("error", at, "circuit_breaker must be a mapping"))
            data.pop("circuit_breaker")
        else:
            clean = dict(breaker)
            for key in ("max_turns", "stall_threshold"):
                value = clean.get(key)
                if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
                    issues.append(Issue("error", at, f"circuit_breaker.{key} must be a positive integer"))
                    clean.pop(key)
            data["circuit_breaker"] = clean
    return data, issues


def _parse_phase(data: dict[str, Any]) -> Phase:
    breaker = data.get("circuit_breaker") if isinstance(data.get("circuit_breaker"), dict) else {}
    agents = data.get("agents")
    return Phase(
        name=str(data.get("name", "")),
        description=" ".join(str(data.get("description", "")).split()),
        hitl_gate=bool(data.get("hitl_gate", False)),
        gate_id=data.get("gate_id"),
        gate_description=data.get("gate_description"),
        agents=agents if agents == ALL_ASSIGNED else _str_list(agents),
        skills_enforced=_str_list(data.get("skills_enforced")),
        output=data.get("output"),
        checklist=_str_list(data.get("checklist")),
        standards=_str_list(data.get("standards")),
        max_turns=breaker.get("max_turns"),
        stall_threshold=breaker.get("stall_threshold"),
        moral_gate=str(data.get("moral_gate", "")).lower() in {"required", "true"},
        mode=data.get("mode"),
        run_checks=bool(data.get("run_checks", False)),
        protocol={k: v for k, v in data.items() if k not in PHASE_KNOWN_KEYS},
    )


def _load_workflows(
    root: Path,
    workflows_dir: Path,
    personas: dict[str, Persona],
    skills: dict[str, Skill],
    issues: list[Issue],
) -> dict[str, Workflow]:
    workflows: dict[str, Workflow] = {}
    if not workflows_dir.is_dir():
        issues.append(Issue("error", _rel(root, workflows_dir), "workflow directory does not exist"))
        return workflows
    for path in sorted(workflows_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        where = _rel(root, path)
        data = _read_yaml(path)
        if not isinstance(data, dict):
            issues.append(Issue("error", where, "workflow file must be a mapping"))
            continue
        for key in ("name", "description", "phases"):
            if not data.get(key):
                issues.append(Issue("error", where, f"missing required field {key!r}"))

        default_personas = _str_list(data.get("default_personas"))
        for persona in default_personas:
            if persona not in personas:
                issues.append(Issue("error", where, f"default_personas references unknown persona {persona!r}"))

        phases: list[Phase] = []
        seen_gates: set[str] = set()
        raw_phases = data.get("phases") or []
        if not isinstance(raw_phases, list):
            issues.append(Issue("error", where, "phases must be a list"))
            raw_phases = []
        for index, raw in enumerate(raw_phases):
            if not isinstance(raw, dict):
                issues.append(Issue("error", where, f"phase #{index + 1} must be a mapping"))
                continue
            at = f"{where}: phase {str(raw.get('name') or index + 1)!r}"
            raw, shape_issues = _phase_shape_issues(raw, at)
            issues.extend(shape_issues)
            phase = _parse_phase(raw)
            if not phase.name or not phase.description:
                issues.append(Issue("error", at, "phase needs a name and a description"))
            if any(p.name == phase.name for p in phases):
                issues.append(Issue("error", at, "duplicate phase name"))
            if not phase.agents:
                issues.append(Issue("error", at, "phase has no agents"))
            elif phase.agents != ALL_ASSIGNED:
                for agent in phase.agents:
                    if agent not in personas:
                        issues.append(Issue("error", at, f"unknown agent persona {agent!r}"))
            for skill in phase.skills_enforced:
                if skill not in skills:
                    issues.append(Issue("error", at, f"unknown enforced skill {skill!r}"))
            if not phase.output:
                issues.append(Issue("error", at, "phase must name an output artifact"))
            if phase.hitl_gate:
                if not phase.gate_id:
                    issues.append(Issue("error", at, "hitl_gate is true but gate_id is missing"))
                elif phase.gate_id in seen_gates:
                    issues.append(Issue("error", at, f"duplicate gate_id {phase.gate_id!r}"))
                else:
                    seen_gates.add(phase.gate_id)
            if phase.mode and phase.mode not in PHASE_MODES:
                issues.append(Issue("error", at, f"mode must be one of {sorted(PHASE_MODES)}"))
            if phase.mode == "parallel":
                issues.append(Issue("warning", at, "parallel mode runs as one lead agent with consulted perspectives"))
            phases.append(phase)

        names = [p.name for p in phases]
        transitions: list[Transition] = []
        raw_transitions = data.get("transitions") if isinstance(data.get("transitions"), dict) else {}
        if data.get("transitions") is not None and not isinstance(data.get("transitions"), dict):
            issues.append(Issue("error", where, "transitions must be a mapping"))
        for key, spec in raw_transitions.items():
            at = f"{where}: transition {key!r}"
            if spec is not None and not isinstance(spec, dict):
                issues.append(Issue("error", at, "transition must be a mapping with a requires list"))
                continue
            source, sep, target = str(key).partition("_to_")
            if not sep or source not in names or (target not in names and target != "complete"):
                issues.append(Issue("error", at, "must be named <phase>_to_<phase|complete>"))
                continue
            if target != "complete" and names.index(target) != names.index(source) + 1:
                issues.append(Issue("error", at, "transitions must follow phase order"))
            requires = _str_list((spec or {}).get("requires"))
            for requirement in requires:
                if requirement not in TRANSITION_REQUIREMENTS:
                    issues.append(Issue(
                        "error", at,
                        f"unknown requirement {requirement!r}; use one of {sorted(TRANSITION_REQUIREMENTS)}",
                    ))
            source_phase = next(p for p in phases if p.name == source)
            if "hitl_gate_approved" in requires and not source_phase.hitl_gate:
                issues.append(Issue(
                    "error", at,
                    f"requires hitl_gate_approved but phase {source!r} has no hitl_gate, so it could never pass",
                ))
            transitions.append(Transition(source, target, requires))

        workflow_id = str(data.get("name") or path.stem)
        workflows[workflow_id] = Workflow(
            id=workflow_id,
            name=workflow_id,
            description=" ".join(str(data.get("description", "")).split()),
            path=path,
            phases=phases,
            default_personas=default_personas,
            transitions=transitions,
        )
    return workflows


def load_project(root: Path, *, strict: bool = True) -> Project:
    """Load and validate a Slipstream project.

    With `strict`, any error-severity issue raises ConfigError. Warnings never
    raise; they are available on `Project.issues`.
    """
    root = Path(root).resolve()
    config_path = root / CONFIG_FILE
    if not config_path.is_file():
        raise ConfigError(f"{config_path} not found")
    config = _read_yaml(config_path) or {}
    if not isinstance(config, dict):
        raise ConfigError(f"{config_path} must be a mapping")

    issues: list[Issue] = []
    paths = config.get("paths") if isinstance(config.get("paths"), dict) else {}
    skill_paths = paths.get("skills") if isinstance(paths.get("skills"), dict) else {}
    skill_dirs = {
        str(category): _path(root, location, "")
        for category, location in (skill_paths or {"core": "skills/core", "quality": "skills/quality", "domain": "skills/domain"}).items()
    }

    constitution_cfg = config.get("constitution") if isinstance(config.get("constitution"), dict) else {}
    primary = constitution_cfg.get("primary") if isinstance(constitution_cfg.get("primary"), dict) else {}
    constitution_path = _path(root, primary.get("path"), "constitution/AI_Engineer_Constitution.md")
    if not constitution_path.is_file():
        issues.append(Issue("error", CONFIG_FILE, f"primary constitution not found: {_rel(root, constitution_path)}"))

    skills = _load_skills(root, skill_dirs, issues)
    tools = _load_tools(_path(root, paths.get("tools"), "tools"))
    personas = _load_personas(
        root,
        _path(root, paths.get("personas"), "personas"),
        _path(root, paths.get("constitution_roles"), "constitution/roles"),
        skills,
        tools,
        issues,
    )
    workflows = _load_workflows(root, _path(root, paths.get("workflows"), "workflows"), personas, skills, issues)

    defaults = config.get("defaults") if isinstance(config.get("defaults"), dict) else {}
    default_workflow = defaults.get("workflow")
    if default_workflow and default_workflow not in workflows:
        issues.append(Issue("error", CONFIG_FILE, f"default workflow {default_workflow!r} not found"))
    default_personas = _str_list(defaults.get("personas"))
    for persona in default_personas:
        if persona not in personas:
            issues.append(Issue("error", CONFIG_FILE, f"default persona {persona!r} not found"))

    project = Project(
        root=root,
        config=config,
        constitution_path=constitution_path,
        personas=personas,
        skills=skills,
        workflows=workflows,
        tools=tools,
        default_workflow=default_workflow,
        default_personas=default_personas,
        issues=issues,
    )
    if strict and project.errors:
        raise ConfigError(
            f"{len(project.errors)} configuration error(s) in {root}",
            project.issues,
        )
    return project
