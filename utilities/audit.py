"""
Slipstream Audit Trail

Handles cryptographic signing of artifacts and decision logging.
Adapted from CLOCKWORK-CORE.
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional

from .io import atomic_write_json, get_data_dir


class AuditTrail:
    """Handles cryptographic signing of workflow artifacts."""

    def __init__(self, secret: str = None):
        """
        Initialize audit trail with signing secret.

        Args:
            secret: Signing secret. Falls back to SLIPSTREAM_AUDIT_SECRET env var.
        """
        self.secret = secret or os.environ.get("SLIPSTREAM_AUDIT_SECRET")

        is_test = os.environ.get("PYTEST_CURRENT_TEST") is not None

        if not self.secret:
            if is_test:
                self.secret = "slipstream-test-secret"
            else:
                # In production, generate a session-specific secret if none provided
                import uuid
                self.secret = f"slipstream-{uuid.uuid4().hex}"
                os.environ["SLIPSTREAM_AUDIT_SECRET"] = self.secret

    def sign_artifact(self, artifact: Dict[str, Any]) -> str:
        """Generate a SHA-256 signature for an artifact."""
        canonical = json.dumps(artifact, sort_keys=True)
        payload = f"{canonical}:{self.secret}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def attach_signature(self, state: Dict[str, Any], metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Sign the artifact and attach the signature to the state."""
        if "artifact" not in state:
            return state

        signature = self.sign_artifact(state["artifact"])
        state["_audit"] = {
            "signature": signature,
            "timestamp": time.time(),
            "signer": "SLIPSTREAM_v1",
            "metadata": metadata
        }
        return state

    def verify_signature(self, state: Dict[str, Any]) -> bool:
        """Verify that the artifact hasn't been tampered with."""
        if "artifact" not in state or "_audit" not in state:
            return False

        expected = self.sign_artifact(state["artifact"])
        return state["_audit"]["signature"] == expected

    def log_event(self,
                  session_id: str,
                  event_type: str,
                  agent: str,
                  phase: str,
                  details: Dict[str, Any],
                  tools_used: list = None,
                  skills_applied: list = None) -> None:
        """
        Log a workflow event to the audit trail.

        Args:
            session_id: Current session identifier
            event_type: Type of event (decision, tool_call, phase_transition, etc.)
            agent: Which persona/agent generated this event
            phase: Current workflow phase
            details: Event-specific details
            tools_used: List of tools invoked
            skills_applied: List of skills that were applied
        """
        log_dir = get_data_dir("audit") / session_id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "events.jsonl"

        entry = {
            "artifact": {
                "event_type": event_type,
                "agent": agent,
                "phase": phase,
                "details": details,
                "tools_used": tools_used or [],
                "skills_applied": skills_applied or [],
                "timestamp": time.time()
            }
        }
        signed = self.attach_signature(entry)

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(signed) + "\n")

    def get_session_events(self, session_id: str, limit: int = 100) -> list:
        """Retrieve events for a session."""
        log_file = get_data_dir("audit") / session_id / "events.jsonl"
        if not log_file.exists():
            return []

        events = []
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return events[-limit:]


# Module-level singleton
_audit_trail: Optional[AuditTrail] = None


def get_audit_trail() -> AuditTrail:
    """Get or create the global audit trail instance."""
    global _audit_trail
    if _audit_trail is None:
        _audit_trail = AuditTrail()
    return _audit_trail


def sign_and_save(file_path: Path, state: Dict[str, Any], metadata: Optional[Dict] = None) -> None:
    """Helper to sign a state and save it atomically."""
    auditor = get_audit_trail()
    signed_state = auditor.attach_signature(state, metadata)
    atomic_write_json(file_path, signed_state)
