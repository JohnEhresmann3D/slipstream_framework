"""
Slipstream Circuit Breaker

Prevents runaway agent conversations by detecting stagnation.
Based on Michael Nygard's circuit breaker pattern.

States:
    CLOSED     - Normal operation, progress is being made
    HALF_OPEN  - Monitoring mode, checking for recovery
    OPEN       - Failure detected, execution halted

Transitions:
    CLOSED -> HALF_OPEN: 2 consecutive turns without progress
    HALF_OPEN -> CLOSED: Progress detected (recovery)
    HALF_OPEN -> OPEN: 3+ turns without progress
    OPEN -> CLOSED: Manual reset only

Adapted from CLOCKWORK-CORE.
"""

import json
import hashlib
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

from .io import get_data_dir


class CircuitState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "CLOSED"
    HALF_OPEN = "HALF_OPEN"
    OPEN = "OPEN"


@dataclass
class CircuitBreakerState:
    """Persistent state for circuit breaker"""
    state: str = CircuitState.CLOSED.value
    last_change: str = ""
    consecutive_no_progress: int = 0
    consecutive_same_error: int = 0
    last_progress_turn: int = 0
    total_opens: int = 0
    reason: str = ""
    current_turn: int = 0
    context_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CircuitBreakerState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TurnResult:
    """Result of a single agent turn"""
    turn_number: int
    artifacts_produced: int = 0
    has_errors: bool = False
    error_signature: Optional[str] = None
    new_information: bool = False


class CircuitBreaker:
    """
    3-state circuit breaker for agent conversation protection.

    Usage:
        cb = CircuitBreaker(session_id="my-session")

        # Before each agent turn
        if not cb.can_execute():
            print("Circuit is OPEN - execution halted")
            return

        # After each agent turn
        result = TurnResult(turn_number=5, artifacts_produced=1, new_information=True)
        should_continue = cb.record_turn_result(result)

        if not should_continue:
            print("Circuit breaker tripped!")
    """

    # Configuration thresholds
    NO_PROGRESS_THRESHOLD = 3    # Open circuit after N turns with no progress
    SAME_ERROR_THRESHOLD = 5     # Open circuit after N turns with same error
    HALF_OPEN_THRESHOLD = 2      # Enter monitoring after N turns without progress

    def __init__(self, session_id: str = "default", data_dir: Path = None):
        """Initialize circuit breaker with persistent storage."""
        if data_dir is None:
            data_dir = get_data_dir("circuit_breaker")

        self.data_dir = Path(data_dir) / session_id
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.state_file = self.data_dir / "state.json"
        self.history_file = self.data_dir / "history.json"

        self._init_state()

    def _init_state(self):
        """Initialize or load state from disk."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self._state = CircuitBreakerState.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                self._state = CircuitBreakerState(last_change=self._timestamp())
                self._save_state()
        else:
            self._state = CircuitBreakerState(last_change=self._timestamp())
            self._save_state()

        if not self.history_file.exists():
            with open(self.history_file, 'w') as f:
                json.dump([], f)

    def _save_state(self):
        """Persist state to disk."""
        with open(self.state_file, 'w') as f:
            json.dump(self._state.to_dict(), f, indent=2)

    def _timestamp(self) -> str:
        """ISO format timestamp."""
        return datetime.now().isoformat()

    def _log_transition(self, from_state: str, to_state: str, reason: str, turn_number: int):
        """Log state transition to history file."""
        try:
            with open(self.history_file, 'r') as f:
                history = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            history = []

        history.append({
            "timestamp": self._timestamp(),
            "turn": turn_number,
            "from_state": from_state,
            "to_state": to_state,
            "reason": reason
        })

        with open(self.history_file, 'w') as f:
            json.dump(history, f, indent=2)

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return CircuitState(self._state.state)

    def can_execute(self, context: Optional[str] = None) -> bool:
        """
        Check if circuit allows execution.
        If context is provided, automatically resets OPEN circuit if context has changed.
        """
        if context and self.state == CircuitState.OPEN:
            new_hash = hashlib.sha256(context.encode()).hexdigest()
            if new_hash != self._state.context_hash:
                self.reset(f"Context change detected")
                self._state.context_hash = new_hash
                self._save_state()
                return True

        return self.state != CircuitState.OPEN

    def record_turn_result(self, result: TurnResult, context: Optional[str] = None) -> bool:
        """
        Record an agent turn result and update circuit state.

        Returns:
            True if execution should continue, False if circuit opened
        """
        if context:
            self._state.context_hash = hashlib.sha256(context.encode()).hexdigest()

        current_state = self.state
        new_state = current_state
        reason = ""

        # Detect progress
        has_progress = result.artifacts_produced > 0 or result.new_information

        if has_progress:
            self._state.consecutive_no_progress = 0
            self._state.last_progress_turn = result.turn_number
        else:
            self._state.consecutive_no_progress += 1

        # Detect error repetition
        if result.has_errors:
            self._state.consecutive_same_error += 1
        else:
            self._state.consecutive_same_error = 0

        self._state.current_turn = result.turn_number

        # State transitions
        if current_state == CircuitState.CLOSED:
            if self._state.consecutive_no_progress >= self.NO_PROGRESS_THRESHOLD:
                new_state = CircuitState.OPEN
                reason = f"No progress in {self._state.consecutive_no_progress} consecutive turns"
            elif self._state.consecutive_same_error >= self.SAME_ERROR_THRESHOLD:
                new_state = CircuitState.OPEN
                reason = f"Same error repeated {self._state.consecutive_same_error} times"
            elif self._state.consecutive_no_progress >= self.HALF_OPEN_THRESHOLD:
                new_state = CircuitState.HALF_OPEN
                reason = f"Monitoring: {self._state.consecutive_no_progress} turns without progress"

        elif current_state == CircuitState.HALF_OPEN:
            if has_progress:
                new_state = CircuitState.CLOSED
                reason = "Progress detected, circuit recovered"
            elif self._state.consecutive_no_progress >= self.NO_PROGRESS_THRESHOLD:
                new_state = CircuitState.OPEN
                reason = f"No recovery after {self._state.consecutive_no_progress} turns"

        # Track opens
        if new_state == CircuitState.OPEN and current_state != CircuitState.OPEN:
            self._state.total_opens += 1

        # Update state
        if new_state != current_state:
            self._state.state = new_state.value
            self._state.last_change = self._timestamp()
            self._state.reason = reason
            self._log_transition(current_state.value, new_state.value, reason, result.turn_number)

        self._save_state()

        return new_state != CircuitState.OPEN

    def reset(self, reason: str = "Manual reset") -> None:
        """Reset circuit to CLOSED state."""
        old_state = self.state

        self._state = CircuitBreakerState(
            state=CircuitState.CLOSED.value,
            last_change=self._timestamp(),
            reason=reason
        )
        self._save_state()

        if old_state != CircuitState.CLOSED:
            self._log_transition(old_state.value, CircuitState.CLOSED.value, reason, 0)

    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            "state": self._state.state,
            "can_execute": self.can_execute(),
            "consecutive_no_progress": self._state.consecutive_no_progress,
            "consecutive_same_error": self._state.consecutive_same_error,
            "last_progress_turn": self._state.last_progress_turn,
            "current_turn": self._state.current_turn,
            "total_opens": self._state.total_opens,
            "reason": self._state.reason,
            "last_change": self._state.last_change
        }

    def get_history(self, limit: int = 10) -> list:
        """Get recent state transitions."""
        try:
            with open(self.history_file, 'r') as f:
                history = json.load(f)
            return history[-limit:]
        except (json.JSONDecodeError, FileNotFoundError):
            return []
