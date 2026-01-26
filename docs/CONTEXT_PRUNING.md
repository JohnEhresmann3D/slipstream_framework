# How to Prune Context in Slipstream

Context window management is critical for agent performance and cost.

## 1. The Strategy: "Rolling Window + Summary"

Instead of feeding the entire chat history, we feed:
1.  **Static**: The Constitution (Mandatory).
2.  **State**: The current Phase and Goals (from `context.json`).
3.  **Recent History**: The last 5-10 turns (from `audit.log`).
4.  **Reference**: Links to artifacts (not the content itself).

## 2. The Implementation (`runner.py`)

I have included a `prune_history_for_context` function in the new `runner.py`.

```python
def prune_history_for_context(session_id: str, limit: int = HISTORY_LIMIT) -> List[Dict]:
    auditor = get_audit_trail()
    events = auditor.get_session_events(session_id, limit=limit)
    return events[-limit:] 
```

## 3. Usage

Run the runner to see the pruned context:

```bash
python -m slipstream_framework.runner --session test_session --action init
python -m slipstream_framework.runner --session test_session --action context
```

## 4. Advanced Pruning (Future)

For very long running sessions, implementing a "Summarizer" step is recommended:
- Every 10 turns, an Agent reads the last 10 turns and writes a 1-paragraph summary to `context.json` under `summary`.
- The Runner then loads `summary` + `last_10_turns`.
