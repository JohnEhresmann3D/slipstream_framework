"""
Slipstream Lite Runner
Entry point for the Slipstream Framework.

Run with: python -m slipstream_framework.runner [session_id]
"""

import sys
import os
import argparse
from pathlib import Path
from typing import Dict, Any, List

# Add parent directory to path so we can import modules
sys.path.append(str(Path(__file__).parent.parent))

from slipstream_framework.utilities.io import load_json_gracefully, atomic_write_json
from slipstream_framework.utilities.audit import get_audit_trail

DEFAULT_SESSION_ID = "default_session"
HISTORY_LIMIT = 5  # Pruning limit

def get_session_path(session_id: str) -> Path:
    return Path(f"slipstream_framework/sessions/{session_id}")

def initialize_session(session_id: str):
    """Creates a new session context if it doesn't exist."""
    path = get_session_path(session_id)
    path.mkdir(parents=True, exist_ok=True)
    
    context_file = path / "context.json"
    if not context_file.exists():
        initial_state = {
            "session_id": session_id,
            "phase": "intake",
            "active_persona": "producer",
            "goals": [],
            "artifacts_index": []
        }
        atomic_write_json(context_file, initial_state)
        print(f"Initialized new session: {session_id}")

def prune_history_for_context(session_id: str, limit: int = HISTORY_LIMIT) -> List[Dict]:
    """
    PRUNING STRATEGY:
    1. Load audit log.
    2. Take only the last N entries.
    3. Filter out massive 'details' blocks if needed (not implemented yet, but good for future).
    """
    auditor = get_audit_trail()
    events = auditor.get_session_events(session_id, limit=limit * 10) # Get more to filter
    
    # Simple pruning: just take last N
    pruned = events[-limit:]
    
    # Advanced pruning opportunity: Summarize older events 
    # (In a real implementation, we would use an LLM to summarize events[:-limit])
    
    return pruned

def generate_system_prompt(session_id: str) -> str:
    """
    Generates the pruned context for the Agent.
    """
    path = get_session_path(session_id) / "context.json"
    state = load_json_gracefully(path)
    
    if not state:
        return "Error: Session not initialized."
        
    # 1. Load Specific Persona
    persona_name = state.get("active_persona", "producer")
    # In a real app, reading local file:
    # persona_def = Path(f"slipstream_framework/personas/{persona_name}.yaml").read_text()
    
    # 2. Get Pruned History
    history = prune_history_for_context(session_id)
    
    prompt = f"""
=== SLIPSTREAM CONTEXT ===
Session: {session_id}
Phase: {state['phase']}
Persona: {persona_name}

=== GOALS ===
{json.dumps(state['goals'], indent=2)}

=== RECENT HISTORY (Last {len(history)} items) ===
"""
    for event in history:
        # Minimal format to save tokens
        e = event['artifact']
        prompt += f"[{e['timestamp']}] {e['agent']} ({e['event_type']}): {str(e['details'])[:200]}...\n"
        
    return prompt

def main():
    parser = argparse.ArgumentParser(description="Slipstream Runner")
    parser.add_argument("--session", default=DEFAULT_SESSION_ID, help="Session ID")
    parser.add_argument("--action", choices=["init", "status", "context"], default="status")
    
    args = parser.parse_args()
    
    if args.action == "init":
        initialize_session(args.session)
    elif args.action == "status":
        print(f"Session: {args.session}")
        path = get_session_path(args.session) / "context.json"
        if path.exists():
            print(path.read_text())
        else:
            print("Not initialized.")
    elif args.action == "context":
        # Show what the agent would see (Pruned)
        print(generate_system_prompt(args.session))

import json

if __name__ == "__main__":
    main()
