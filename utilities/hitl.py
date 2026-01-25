"""
Slipstream Human-in-the-Loop (HITL) Manager

Provides gates for human approval at critical workflow points.
Adapted from CLOCKWORK-CORE.
"""

import json
import time
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, List

from .io import get_data_dir
from .audit import sign_and_save, get_audit_trail


class RiskLevel(str, Enum):
    """Risk levels for actions requiring human review."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GateStatus(str, Enum):
    """Status of a HITL gate."""
    PENDING = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class HITLManager:
    """
    Human-in-the-Loop gate manager for workflow checkpoints.

    Usage:
        hitl = HITLManager(session_id="my-session")

        # Create a gate for human approval
        gate = hitl.create_gate(
            gate_id="plan-review",
            phase="powwow",
            description="Review the proposed implementation plan",
            risk=RiskLevel.HIGH,
            details={"plan": "..."}
        )

        # Check if gate is resolved
        if hitl.is_gate_approved("plan-review"):
            # Proceed with execution
            pass
        else:
            # Wait for human input
            pass

        # Human approves (typically via UI or CLI)
        hitl.approve_gate("plan-review", feedback={"notes": "Looks good"})
    """

    def __init__(self, session_id: str = "default", data_dir: Path = None):
        """Initialize HITL manager with persistent storage."""
        if data_dir is None:
            data_dir = get_data_dir("hitl")

        self.data_dir = Path(data_dir) / session_id
        self.gates_dir = self.data_dir / "gates"
        self.gates_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id

    def assess_risk(self, action_type: str, details: Dict[str, Any]) -> RiskLevel:
        """
        Heuristic-based risk assessment for actions.

        Override this method for custom risk assessment logic.
        """
        # Critical: Code modifications
        if action_type == "code_change":
            files = details.get("files", [])
            if any("config" in f.lower() or "secret" in f.lower() for f in files):
                return RiskLevel.CRITICAL
            return RiskLevel.HIGH

        # Critical: External API calls with side effects
        if action_type == "external_api" and details.get("method") in ["POST", "PUT", "DELETE"]:
            return RiskLevel.CRITICAL

        # High: Phase transitions
        if action_type == "phase_transition":
            return RiskLevel.HIGH

        # Medium: Research synthesis
        if action_type == "synthesize_research":
            return RiskLevel.MEDIUM

        # Medium: Plan finalization
        if action_type == "finalize_plan":
            return RiskLevel.MEDIUM

        return RiskLevel.LOW

    def create_gate(self,
                    gate_id: str,
                    phase: str,
                    description: str,
                    risk: RiskLevel,
                    details: Dict[str, Any],
                    agents_involved: List[str] = None,
                    artifacts: List[str] = None) -> Dict[str, Any]:
        """
        Create a gate that requires human approval.

        Returns:
            Gate state dict
        """
        gate_path = self.gates_dir / f"{gate_id}.gate.json"

        state = {
            "artifact": {
                "gate_id": gate_id,
                "session_id": self.session_id,
                "phase": phase,
                "description": description,
                "risk_level": risk.value,
                "details": details,
                "agents_involved": agents_involved or [],
                "artifacts": artifacts or [],
                "status": GateStatus.PENDING.value,
                "created_at": time.time(),
                "resolved_at": None,
                "feedback": None
            }
        }

        sign_and_save(gate_path, state)

        return state["artifact"]

    def get_gate(self, gate_id: str) -> Optional[Dict[str, Any]]:
        """Get the current state of a gate."""
        gate_path = self.gates_dir / f"{gate_id}.gate.json"
        if not gate_path.exists():
            return None

        try:
            data = json.loads(gate_path.read_text())
            return data.get("artifact")
        except json.JSONDecodeError:
            return None

    def is_gate_approved(self, gate_id: str) -> bool:
        """Check if a gate has been approved."""
        gate = self.get_gate(gate_id)
        if not gate:
            return False
        return gate.get("status") == GateStatus.APPROVED.value

    def is_gate_pending(self, gate_id: str) -> bool:
        """Check if a gate is pending approval."""
        gate = self.get_gate(gate_id)
        if not gate:
            return False
        return gate.get("status") == GateStatus.PENDING.value

    def approve_gate(self, gate_id: str, feedback: Optional[Dict] = None) -> bool:
        """
        Approve a gate, allowing workflow to proceed.

        Args:
            gate_id: The gate to approve
            feedback: Optional feedback from the human reviewer

        Returns:
            True if approved successfully
        """
        gate_path = self.gates_dir / f"{gate_id}.gate.json"
        if not gate_path.exists():
            return False

        try:
            raw_data = json.loads(gate_path.read_text())
            artifact = raw_data.get("artifact", {})

            artifact["status"] = GateStatus.APPROVED.value
            artifact["resolved_at"] = time.time()
            artifact["feedback"] = feedback

            new_state = {"artifact": artifact}
            sign_and_save(gate_path, new_state, metadata={"action": "approved"})
            return True
        except Exception:
            return False

    def reject_gate(self, gate_id: str, reason: str, feedback: Optional[Dict] = None) -> bool:
        """
        Reject a gate, blocking workflow progression.

        Args:
            gate_id: The gate to reject
            reason: Why the gate was rejected
            feedback: Optional additional feedback

        Returns:
            True if rejected successfully
        """
        gate_path = self.gates_dir / f"{gate_id}.gate.json"
        if not gate_path.exists():
            return False

        try:
            raw_data = json.loads(gate_path.read_text())
            artifact = raw_data.get("artifact", {})

            artifact["status"] = GateStatus.REJECTED.value
            artifact["resolved_at"] = time.time()
            artifact["rejection_reason"] = reason
            artifact["feedback"] = feedback

            new_state = {"artifact": artifact}
            sign_and_save(gate_path, new_state, metadata={"action": "rejected"})
            return True
        except Exception:
            return False

    def get_pending_gates(self) -> List[Dict[str, Any]]:
        """Get all pending gates for this session."""
        pending = []
        for gate_file in self.gates_dir.glob("*.gate.json"):
            try:
                data = json.loads(gate_file.read_text())
                artifact = data.get("artifact", {})
                if artifact.get("status") == GateStatus.PENDING.value:
                    pending.append(artifact)
            except json.JSONDecodeError:
                continue
        return pending

    def clear_gates(self) -> None:
        """Clear all gates for this session."""
        for gate_file in self.gates_dir.glob("*.gate.json"):
            gate_file.unlink()


def check_and_gate(session_id: str,
                   gate_id: str,
                   action_type: str,
                   phase: str,
                   description: str,
                   details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Helper to check risk and create gate if necessary.

    Returns:
        {"ok": True} if action can proceed
        {"ok": False, "gate": ..., "message": ...} if gate required
    """
    mgr = HITLManager(session_id=session_id)
    risk = mgr.assess_risk(action_type, details)

    # Only gate HIGH and CRITICAL risk actions
    if risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
        if not mgr.is_gate_approved(gate_id):
            if not mgr.is_gate_pending(gate_id):
                gate = mgr.create_gate(
                    gate_id=gate_id,
                    phase=phase,
                    description=description,
                    risk=risk,
                    details=details
                )
            else:
                gate = mgr.get_gate(gate_id)

            return {
                "ok": False,
                "status": "PENDING_APPROVAL",
                "risk": risk.value,
                "gate": gate,
                "message": f"Action '{gate_id}' requires human approval (risk: {risk.value})"
            }

    return {"ok": True, "risk": risk.value}
