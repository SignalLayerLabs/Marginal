"""First-class accounting for the cost and mistakes of MARGINAL itself."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GovernanceTracker:
    """Account for governance overhead and explicitly reviewed false stops.

    False stops are never inferred from task success. They are counted only when an external
    reviewer or counterfactual process explicitly labels a denied recommendation as an action
    that would have helped.
    """

    decisions: int = 0
    decision_latency_ms: float = 0.0
    external_tokens: int = 0
    external_usd: float = 0.0
    external_latency_ms: float = 0.0
    reviewed_stops: int = 0
    false_stops: int = 0

    def record_decision(self, *, latency_ms: float = 0.0) -> None:
        self._validate_non_negative_number("latency_ms", latency_ms)
        self.decisions += 1
        self.decision_latency_ms += float(latency_ms)

    def record_external_overhead(
        self,
        *,
        tokens: int = 0,
        usd: float = 0.0,
        latency_ms: float = 0.0,
    ) -> None:
        if isinstance(tokens, bool) or not isinstance(tokens, int):
            raise TypeError("tokens must be an integer")
        if tokens < 0:
            raise ValueError("tokens must be non-negative")
        self._validate_non_negative_number("usd", usd)
        self._validate_non_negative_number("latency_ms", latency_ms)
        self.external_tokens += tokens
        self.external_usd += float(usd)
        self.external_latency_ms += float(latency_ms)

    def record_stop_review(self, *, would_have_helped: bool) -> None:
        if not isinstance(would_have_helped, bool):
            raise TypeError("would_have_helped must be a boolean")
        self.reviewed_stops += 1
        if would_have_helped:
            self.false_stops += 1

    def summary(self) -> dict[str, Any]:
        false_stop_rate = self.false_stops / self.reviewed_stops if self.reviewed_stops else None
        total_latency = self.decision_latency_ms + self.external_latency_ms
        return {
            "scope": "treasury_tree",
            "decisions": self.decisions,
            "decision_latency_ms": round(self.decision_latency_ms, 6),
            "external_tokens": self.external_tokens,
            "external_usd": round(self.external_usd, 9),
            "external_latency_ms": round(self.external_latency_ms, 6),
            "total_latency_ms": round(total_latency, 6),
            "reviewed_stops": self.reviewed_stops,
            "false_stops": self.false_stops,
            "false_stop_rate": round(false_stop_rate, 6) if false_stop_rate is not None else None,
        }

    @staticmethod
    def _validate_non_negative_number(name: str, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be a number")
        if not math.isfinite(float(value)) or value < 0:
            raise ValueError(f"{name} must be finite and non-negative")
