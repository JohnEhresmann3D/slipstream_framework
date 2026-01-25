# SKILL: Code Review & Refactor Integrity

## Use When
- refactoring
- PR review style feedback
- performance changes

## Rules
- Separate "behavior-preserving refactor" from "behavior change".
- Call out hidden complexity, unclear naming, missing tests.
- Identify security footguns.

## Output Format
- High-risk issues (must fix)
- Medium issues (should fix)
- Nits (optional)
- Suggested diffs (if writing code)
