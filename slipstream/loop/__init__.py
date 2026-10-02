"""Slipstream orchestration core."""

from .operator import Operator, OperatorResult
from .verification import GateResult, Verdict

__all__ = ["Operator", "OperatorResult", "GateResult", "Verdict"]
