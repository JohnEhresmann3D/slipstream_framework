#!/usr/bin/env python3
"""
bootstrap_slipstream_framework.py

Creates a sterile Slipstream framework scaffold AND
adds Apache 2.0 license + NOTICE file.

Root directory defaults to: slipstream_v_2_0
"""

from pathlib import Path
import argparse
from datetime import datetime


# -------------------------------------------------
# Helpers
# -------------------------------------------------

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def write_file(path: Path, content: str, force: bool):
    if path.exists() and not force:
        return
    ensure_dir(path.parent)
    path.write_text(content.strip() + "\n", encoding="utf-8")


# -------------------------------------------------
# Apache License Generator
# -------------------------------------------------

def generate_apache_license(year: str, owner: str) -> str:
    return f"""
Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

Copyright {year} {owner}

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

NOTICE_TEMPLATE = """
Slipstream Framework v2.0

Licensed under Apache License 2.0.

Copyright (c) {year} {owner}
"""

# -------------------------------------------------
# Framework Templates (Sterile)
# -------------------------------------------------

AGENT_TEMPLATE = """
---
template: agent
name: <agent_slug>
title: <Agent Title>
version: 2.0
---

# <Agent Title>

## Mission
<Describe purpose>

## Domain Ownership
### Owns
- <Domain>

### Does NOT Own
- <Exclusions>

---

# Constitution

## Non-Negotiables
- Follow project scope.
- Do not fabricate artifacts.
- Record significant decisions.

## Decision Policy
Record decisions in implementation_decisions.md

Required fields:
- Decision:
- Rationale:
- Alternatives:
- Revisit:

## Quality Policy
Every output must include:
- Definition of Done
- Validation plan
- Risks / failure modes
"""

SKILL_TEMPLATE = """
---
template: skill
name: <skill_slug>
title: <Skill Title>
version: 2.0
---

# <Skill Title>

## Purpose
<What this enables>

## Use When
- <Trigger>

## Inputs
- <Inputs>

## Outputs
- <Outputs>

## Procedure
1. <Step>
2. <Step>

## Quality Gate
- <DoD>

## Subskills
subskills/<id>-<slug>.md
"""

SUBSKILL_TEMPLATE = """
---
template: subskill
name: <skill_slug>:<id>
title: <Subskill Title>
version: 2.0
---

# <id> — <Subskill Title>

## Goal
<Completion definition>

## Workflow
1. Minimal implementation
2. Validation

## Definition of Done
- <Objective check>
"""

SKILL_REGISTRY_TEMPLATE = """
---
template: skill_registry
version: 2.0
---

# Skill Registry

## Usage
1. Identify domain
2. Select skill
3. Select subskill
4. Follow handoffs
"""

CONSTITUTION_TEMPLATE = """
---
template: constitution
scope: <project|agent|team>
version: 2.0
---

# Constitution

## Priority
1. Scope
2. Project Constitution
3. Agent Constitution
4. Skills

## Principles
- Be explicit
- Minimal safe change
- Validate before completion

## Decision Rules
Document decisions in implementation_decisions.md
"""

WORKFLOW_TEMPLATE = """
---
template: workflow
version: 2.0
---

# Workflow

1. Clarify
2. Plan
3. Execute
4. Validate
5. Report
"""

GITIGNORE = """
__pycache__/
*.pyc
.env
.vscode/
.DS_Store
"""

# -------------------------------------------------
# Main
# -------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="slipstream_v_2_0")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--owner", default="Your Name or Organization")
    parser.add_argument("--year", default=str(datetime.now().year))
    args = parser.parse_args()

    root = Path(args.root)

    # Directory structure
    dirs = [
        root / "templates/agents",
        root / "templates/skills",
        root / "templates/constitutions",
        root / "templates/workflows"
    ]

    for d in dirs:
        ensure_dir(d)

    # Write templates
    write_file(root / "templates/agents/AGENT_TEMPLATE.md", AGENT_TEMPLATE, args.force)
    write_file(root / "templates/skills/SKILL_TEMPLATE.md", SKILL_TEMPLATE, args.force)
    write_file(root / "templates/skills/SUBSKILL_TEMPLATE.md", SUBSKILL_TEMPLATE, args.force)
    write_file(root / "templates/skills/SKILL_REGISTRY_TEMPLATE.md", SKILL_REGISTRY_TEMPLATE, args.force)
    write_file(root / "templates/constitutions/CONSTITUTION_TEMPLATE.md", CONSTITUTION_TEMPLATE, args.force)
    write_file(root / "templates/workflows/WORKFLOW_TEMPLATE.md", WORKFLOW_TEMPLATE, args.force)

    # License
    write_file(Path("LICENSE"), generate_apache_license(args.year, args.owner), args.force)
    write_file(Path("NOTICE"), NOTICE_TEMPLATE.format(year=args.year, owner=args.owner), args.force)
    write_file(Path(".gitignore"), GITIGNORE, args.force)

    print(f"✅ Slipstream v2.0 scaffold created at: {root.resolve()}")
    print("✅ Apache 2.0 LICENSE generated.")
    print("✅ NOTICE file generated.")


if __name__ == "__main__":
    main()
