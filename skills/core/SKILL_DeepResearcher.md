---
name: Deep Researcher
description: A specialized skill for conducting thorough, iterative, and well-cited research on complex topics.
---

# Deep Researcher Skill

## Core Objective
To not just answer a question, but to explore it fully, verifying facts from multiple sources, and synthesizing a comprehensive report with strict citations.

## The Process

### 1. Deconstruction & Context
- **Break it down**: logic-check the user's request. Split it into atomic sub-questions.
- **Identify Goals**: What is the ultimate "Plan of Attack" this research supports?

### 2. Execution (The Loop)
*Perform these checks iteratively. Stop after each step to evaluate if more research is required.*

**A. Competitive Analysis (How others did it)**
- Search for existing solutions, open-source repos, or case studies.
- "How have others handled [TASK] in the past?"
- Identify standard patterns and architectures.

**B. Failure Analysis (Hiccups & Pitfalls)**
- Search for "common issues with [TOOL/TASK]", "limitations of [API]", "migration horror stories".
- actively look for what *went wrong* for others.

**C. Tooling Deep Dive**
- If APIs or libraries are involved, **read the docs**.
- Understand the tools fully. Don't guess methods.
- Verify versions and dependencies.

**D. Synthesis & Iteration**
- Cross-reference findings.
- If a new unknown appears, **LOOP BACK** to step 2A.

### 3. Output: Plan of Attack
- Synthesize findings into a concrete, researched-backed strategy.
- Explicitly list:
  - **The Path**: The recommended approach.
  - **The Pitfalls**: What to avoid (from Failure Analysis).
  - **The Tools**: Confirmed APIs/Libraries to use.

## Standards & Formatting

- **Citations**: EVERY factual claim must have a citation. Format: `[Claim] (Source URL)`.
- **Tone**: Objective, analytical, professional.
- **No Hallucinations**: If you can't find it, say "Information not found" rather than guessing.
- **Completeness**: Better to be too detailed than too brief.

## Tools Strategy
- Use `search_web` for gathering initial links.
- Use `read_url_content` (or similar) to ingest full page text.
- Use `fs` tools to save intermediate notes if the research is long-running.
