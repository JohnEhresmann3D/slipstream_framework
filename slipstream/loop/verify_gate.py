"""Compatibility shim for the previous VerifyGate name."""

from .verification import BackendVerifier, GateResult, Verdict

VerifyGate = BackendVerifier

__all__ = ["VerifyGate", "BackendVerifier", "GateResult", "Verdict"]
