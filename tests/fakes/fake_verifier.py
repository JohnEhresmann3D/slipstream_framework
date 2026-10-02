from __future__ import annotations

from collections import deque

from slipstream.loop.verification import GateResult, Verdict


class FakeVerifier:
    def __init__(self, results: list[GateResult] | None = None):
        self.results = deque(results or [GateResult(Verdict.MET, "done")])
        self.calls = []

    def evaluate(self, goal, criteria, evidence, worker_result, history, workspace):
        self.calls.append((goal, criteria, evidence, worker_result, workspace))
        if len(self.results) > 1:
            return self.results.popleft()
        return self.results[0]
