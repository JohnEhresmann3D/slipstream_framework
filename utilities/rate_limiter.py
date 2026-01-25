"""
Slipstream Rate Limiter

Prevents API abuse with configurable call limits.
Adapted from CLOCKWORK-CORE.
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass, asdict

from .io import get_data_dir


@dataclass
class CallRecord:
    """Record of a single API call"""
    timestamp: float
    endpoint: str = "default"
    agent: str = "unknown"


class RateLimiter:
    """
    Rate limiter with configurable limits per endpoint.

    Usage:
        limiter = RateLimiter(session_id="my-session")

        # Configure limits
        limiter.set_limit("deepsearch", calls_per_hour=10)
        limiter.set_limit("web_fetch", calls_per_hour=20)
        limiter.set_limit("llm", calls_per_hour=100)

        # Before making a call
        if limiter.can_call("deepsearch"):
            limiter.record_call("deepsearch", agent="researcher")
            # Make API call
        else:
            wait_time = limiter.seconds_until_available("deepsearch")
            print(f"Rate limited. Wait {wait_time}s")
    """

    DEFAULT_CALLS_PER_HOUR = 100

    def __init__(self, session_id: str = "default", data_dir: Path = None):
        """
        Initialize rate limiter with persistent storage.

        Args:
            session_id: Session identifier for isolation
            data_dir: Directory for persistent storage
        """
        if data_dir is None:
            data_dir = get_data_dir("rate_limiter")

        self.data_dir = Path(data_dir) / session_id
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.calls_file = self.data_dir / "calls.json"
        self.limits_file = self.data_dir / "limits.json"

        self.window_seconds = 3600  # 1 hour
        self.calls: List[CallRecord] = []
        self.limits: Dict[str, int] = {}

        self._load_state()

    def _load_state(self):
        """Load call history and limits from disk."""
        # Load calls
        if self.calls_file.exists():
            try:
                with open(self.calls_file, 'r') as f:
                    data = json.load(f)
                    self.calls = [CallRecord(**c) for c in data.get("calls", [])]
            except (json.JSONDecodeError, KeyError):
                self.calls = []

        # Load limits
        if self.limits_file.exists():
            try:
                with open(self.limits_file, 'r') as f:
                    self.limits = json.load(f)
            except json.JSONDecodeError:
                self.limits = {}

    def _save_state(self):
        """Persist state to disk."""
        self._prune_old_calls()

        with open(self.calls_file, 'w') as f:
            json.dump({
                "calls": [asdict(c) for c in self.calls],
                "window_seconds": self.window_seconds
            }, f, indent=2)

        with open(self.limits_file, 'w') as f:
            json.dump(self.limits, f, indent=2)

    def _prune_old_calls(self):
        """Remove calls older than the window."""
        cutoff = time.time() - self.window_seconds
        self.calls = [c for c in self.calls if c.timestamp > cutoff]

    def _calls_in_window(self, endpoint: str) -> int:
        """Count calls for an endpoint in the current window."""
        self._prune_old_calls()
        return sum(1 for c in self.calls if c.endpoint == endpoint)

    def set_limit(self, endpoint: str, calls_per_hour: int) -> None:
        """Set the rate limit for an endpoint."""
        self.limits[endpoint] = calls_per_hour
        self._save_state()

    def get_limit(self, endpoint: str) -> int:
        """Get the rate limit for an endpoint."""
        return self.limits.get(endpoint, self.DEFAULT_CALLS_PER_HOUR)

    def can_call(self, endpoint: str) -> bool:
        """Check if a call is allowed under rate limit."""
        limit = self.get_limit(endpoint)
        return self._calls_in_window(endpoint) < limit

    def record_call(self, endpoint: str, agent: str = "unknown") -> None:
        """Record a new API call."""
        self.calls.append(CallRecord(
            timestamp=time.time(),
            endpoint=endpoint,
            agent=agent
        ))
        self._save_state()

    def seconds_until_available(self, endpoint: str) -> int:
        """
        Calculate seconds until a call slot becomes available.

        Returns:
            0 if calls are available, otherwise seconds to wait
        """
        if self.can_call(endpoint):
            return 0

        # Find oldest call for this endpoint in window
        self._prune_old_calls()
        endpoint_calls = [c for c in self.calls if c.endpoint == endpoint]
        if not endpoint_calls:
            return 0

        oldest = min(c.timestamp for c in endpoint_calls)
        reset_time = oldest + self.window_seconds
        wait = reset_time - time.time()

        return max(0, int(wait))

    def get_status(self, endpoint: str = None) -> Dict[str, Any]:
        """
        Get current rate limiter status.

        Args:
            endpoint: Specific endpoint, or None for all endpoints
        """
        if endpoint:
            calls_used = self._calls_in_window(endpoint)
            limit = self.get_limit(endpoint)
            return {
                "endpoint": endpoint,
                "calls_used": calls_used,
                "calls_remaining": max(0, limit - calls_used),
                "limit": limit,
                "seconds_until_available": self.seconds_until_available(endpoint),
                "can_call": self.can_call(endpoint)
            }
        else:
            # Return status for all tracked endpoints
            endpoints = set(self.limits.keys()) | set(c.endpoint for c in self.calls)
            return {ep: self.get_status(ep) for ep in endpoints}

    def reset(self, endpoint: str = None) -> None:
        """
        Reset call history.

        Args:
            endpoint: Specific endpoint to reset, or None for all
        """
        if endpoint:
            self.calls = [c for c in self.calls if c.endpoint != endpoint]
        else:
            self.calls = []
        self._save_state()


# Default limits for common tools
DEFAULT_TOOL_LIMITS = {
    "deepsearch": 10,
    "web_fetch": 20,
    "web_search": 15,
    "llm_call": 100,
    "codebase_grep": 50,
    "file_read": 200,
}


def create_rate_limiter(session_id: str = "default") -> RateLimiter:
    """Factory function to create rate limiter with default limits."""
    limiter = RateLimiter(session_id=session_id)
    for endpoint, limit in DEFAULT_TOOL_LIMITS.items():
        if endpoint not in limiter.limits:
            limiter.set_limit(endpoint, limit)
    return limiter
