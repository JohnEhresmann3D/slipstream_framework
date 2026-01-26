# Slipstream Framework: Technical Implementation Report

**Date**: 2026-01-25
**Version**: 1.1

## 1. Executive Summary

This report documents the successful implementation of the **Slipstream Framework**, a file-based, constitution-driven agentic architecture that replaces the runtime-heavy Clockwork framework. Key achievements include the development of a stateless `runner.py`, a "Rolling Window" context pruning strategy that reduces token usage by ~54%, and verification of crash-recovery via persistent JSON state.

## 2. Architecture Overview

Slipstream operates on a **"Brain on Disk"** philosophy.

*   **State**: Stored in `sessions/{id}/context.json` (Goals, Phase, Active Persona).
*   **History**: Stored in `sessions/{id}/audit.jsonl` (Append-only log of events).
*   **Logic**: Stateless Python scripts (`runner.py`) that load state, execute *one* decision, and exit.

### 2.1 The Runner (`runner.py`)

A new CLI entry point was created to standardize agent interaction.

*   **Usage**: `python -m slipstream_framework.runner --session {id}`
*   **Function**:
    1.  Loads `context.json` to identify the Active Persona (e.g., Gameplay Engineer).
    2.  Loads the relevant **Constitution** and **Persona Definition**.
    3.  Prunes the Audit Log (see 2.2).
    4.  Generates a "System Prompt" representing the agent's current reality.

## 3. Context Pruning Strategy ("The Rolling Window")

To prevent context bloat and ensure infinite session viability, we implemented a strict pruning strategy.

### 3.1 Algorithm
Instead of feeding the entire conversation history to the LLM, the Runner constructs the prompt using:
1.  **Static**: Constitution + Persona Constraints (Always Present).
2.  **State**: The `goals` list from `context.json` (The "Long-term Memory").
3.  **Window**: The last **5** events from `audit.log` (The "Short-term Memory").

### 3.2 Performance Metrics
A simulation of a 20-turn research session ("Researching Platformer Powerups") yielded the following results:

| Metric | Full Context | Pruned Context (Window=5) | Savings |
| :--- | :--- | :--- | :--- |
| **Tokens** | ~407 | ~185 | **222** |
| **Percent** | 100% | 45.6% | **54.4%** |

*Note: Tokens calculated via character heuristic (4 chars/token).*

## 4. Resilience & Recovery

The framework was verified to be **Crash Proof**.

*   **Test**: A script updated the Agent's Goal in `context.json` and immediately terminated the process.
*   **Result**: Upon restart, the Runner correctly loaded the updated Goal and Persona from disk.
*   **Implication**: Agents can be interrupted, rebooted, or moved between machines without amnesia, provided the `sessions/` directory is preserved.

## 5. Artifacts Created

1.  **`runner.py`**: The core execution CLI.
2.  **`docs/SLIPSTREAM_RULES.md`**: User rules/system prompt documentation.
3.  **`docs/CONTEXT_PRUNING.md`**: Detailed strategy for context management.
