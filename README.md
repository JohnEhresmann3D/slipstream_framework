# Slipstream Framework v2.0

A sterile, agent-friendly scaffolding and template system for building AI-assisted developer workflows and repository automation.

This repository provides a base for defining:
- **Agents** — defined personas with domain ownership and constitutions  
- **Skills/Subskills** — modular procedural units of work  
- **Constitutions** — governance rules and priority orders  
- **Workflows** — standardized task execution and routing patterns  

It’s designed for use by **humans**, **AI assistants**, or multi-agent systems (Claude, Codex, Anti-Gravity, etc.) to build out structured processes in your project.

---

## 🚀 Overview

Slipstream v2.0 is *purpose-neutral* — it does **not ship pre-built agents or skills**. Instead, it supplies reusable **templates** and a mechanism to instantiate them so you can build your own agentic system.

This README explains:
1. How to use Slipstream templates to build agent workflows
2. How to integrate with AI agent systems (Claude, Codex, Anti-Gravity)
3. The intended hierarchy/structure across templates and agents
4. Current features and scaffold contents

---

## 📦 Scaffold Structure

After running:

```sh
python bootstrap_slipstream_framework.py
or equivalent initialization, you should have:

slipstream_v_2_0/
├── LICENSE
├── NOTICE
├── .gitignore
└── templates/
    ├── agents/
    │   └── AGENT_TEMPLATE.md
    ├── skills/
    │   ├── SKILL_TEMPLATE.md
    │   ├── SUBSKILL_TEMPLATE.md
    │   └── SKILL_REGISTRY_TEMPLATE.md
    ├── constitutions/
    │   └── CONSTITUTION_TEMPLATE.md
    └── workflows/
        ├── WORKFLOW_TEMPLATE.md
📘 How to Use
🧠 1. Create Skills
Copy SKILL_TEMPLATE.md to a new skill folder:

skills/<domain-name>/
  SKILL.md
  subskills/
    <id>-<slug>.md
Fill in:

Purpose

Triggers (when this applies)

Inputs/Outputs

Procedure

Quality Gate

Subskills

Each subskill gets its own file under subskills/ using SUBSKILL_TEMPLATE.md.

Add entry to your SKILL_REGISTRY.md using SKILL_REGISTRY_TEMPLATE.md as a guide.

🤖 2. Create Agents
Agents define who executes which skills.

Duplicate AGENT_TEMPLATE.md per persona.

Define:

Mission and domain ownership

Allowed skills

Activation criteria (triggers)

Input/Output expectations

Agent-level constitution

Agents can be used to control workflows, code generation tasks, quality checks, or specialized responsibilities.

📜 3. Define Constitutions
Constitutions govern behavior for:

Project scope

Agent behavior constraints

Decision policies

Duplicate and customize CONSTITUTION_TEMPLATE.md per project or agent.

🔄 4. Workflows
Workflows define patterns of work across agents and skills.

Use WORKFLOW_TEMPLATE.md as a starting point.

Define:

Entry criteria

Step sequence

Exit criteria

Failure modes / escalation

Examples:

Task execution workflow

Routing between agents

Orchestrator → worker delegation

Evaluator → optimizer loop

🤝 Working with AI Agents
Many modern development workflows leverage AI agents to generate, review, and validate content. In your README (or in an AGENTS.md file), you should:

🧠 Provide clear agent instructions
Tools like AGENTS.md can define agent context, role, and boundaries. A strong AGENTS.md generally includes: 

Agent identity and purpose

Project structure

Tech stack & commands

Roles & limitations

Example (conceptual):

---
name: docs_agent
description: Generate docs for this Slipstream system using templates.
---

You are a documentation engineer. Use templates in `templates/` to create skills and workflows. Do NOT modify source files unrelated to docs.
Commands available:
- Read and write `templates/`
- Validate `SKILL_REGISTRY.md`
- Generate skill/subskill scaffolds
🧩 Model-Aware Routing
Different agents excel at different tasks:

Goal	Best Fit
Architectural planning	Claude Claude
Code generation	Codex (OpenAI GPT)
Reasoning + validation	Claude (Anthropic)
Formal specification	Anti-Gravity
Your agent orchestration system should include a router that:

Identifies domain

Picks skill

Assigns agent

Handles handoffs

This pattern ensures consistent execution without ambiguity.

🏛️ Intended Hierarchy
🧩 Skills & Subskills
Skills are procedural building blocks that describe:

What to do

When to apply

What success looks like

Subskills are specific patterns within skills that break tasks down further.

🤖 Agents
Agents are domain owners that:

Select skills

Generate outputs manually or via AI

Respect constitutions and handoff rules

Report results with validations

🛠️ Workflows
Workflows orchestrate how agents interact and how work flows from:

Task assignment

Execution

Validation

Reporting

This meeting of skills, agents, and workflows forms the backbone of AI-augmented development.

🎯 Current Features
The Slipstream v2.0 scaffold includes:

✔️ Agent template (AGENT_TEMPLATE.md)
✔️ Skill templates (SKILL_TEMPLATE.md, SUBSKILL_TEMPLATE.md)
✔️ Skill registry template (SKILL_REGISTRY_TEMPLATE.md)
✔️ Constitution template (CONSTITUTION_TEMPLATE.md)
✔️ Base workflow template (WORKFLOW_TEMPLATE.md)
✔️ Apache 2.0 license + NOTICE file
✔️ .gitignore for common project files

This gives you zero assumptions about your domain and maximum flexibility to design your own agentic system.

📚 Best Practices
Based on industry README guidance: 

Start with a clear Purpose section at the top.

Use table of contents for navigation.

Provide clear installation/setup steps for contributors.

Document agent roles & responsibilities explicitly.

Keep AI agent context (triggers, tools, boundaries) clear.

Link to templates rather than duplicating contents.

📝 Contributing
To contribute improvements to Slipstream v2.0:

Fork the repo

Add new templates and update README accordingly

Submit a pull request

Update CHANGELOG.md with your changes

🧑‍💻 License
This project is licensed under the Apache License 2.0. See the LICENSE file for details.
