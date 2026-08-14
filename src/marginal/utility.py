"""Correctness-first structured utility and marginal-efficiency estimates."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .receipts import GovernanceCost


def _finite_non_negative(value: float | int | None, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number or None")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return normalized


def _confidence(value: float) -> float:
    normalized = _finite_non_negative(value, "confidence")
    assert normalized is not None
    if normalized > 1.0:
        raise ValueError("confidence must be between 0 and 1")
    return normalized


def _compare_benefit(left: float | None, right: float | None) -> int:
    if left is None:
        return 0 if right is None else -1
    if right is None:
        return 1
    return (left > right) - (left < right)


def _compare_cost(left: float | None, right: float | None) -> int:
    if left is None:
        return 0 if right is None else -1
    if right is None:
        return 1
    return (right > left) - (right < left)


@dataclass(frozen=True, slots=True)
class UtilityVector:
    """A lexicographic scorecard where correctness always dominates efficiency."""

    verified_correctness: float | None
    task_completion: float | None
    safety_risk: float | None
    latency_ms: float | None
    tokens: int | None
    monetary_cost: float | None
    governance_overhead: float | None

    def __post_init__(self) -> None:
        for name in (
            "verified_correctness",
            "task_completion",
            "safety_risk",
            "latency_ms",
            "monetary_cost",
            "governance_overhead",
        ):
            object.__setattr__(self, name, _finite_non_negative(getattr(self, name), name))
        if self.tokens is not None:
            if isinstance(self.tokens, bool) or not isinstance(self.tokens, int):
                raise TypeError("tokens must be an integer or None")
            if self.tokens < 0:
                raise ValueError("tokens must be non-negative")

    def compare(self, other: UtilityVector) -> int:
        """Compare utility vectors in the documented correctness-first order."""

        if not isinstance(other, UtilityVector):
            raise TypeError("other must be UtilityVector")
        comparisons = (
            _compare_benefit(self.verified_correctness, other.verified_correctness),
            _compare_benefit(self.task_completion, other.task_completion),
            _compare_cost(self.safety_risk, other.safety_risk),
            _compare_cost(self.latency_ms, other.latency_ms),
            _compare_cost(
                None if self.tokens is None else float(self.tokens),
                None if other.tokens is None else float(other.tokens),
            ),
            _compare_cost(self.monetary_cost, other.monetary_cost),
            _compare_cost(self.governance_overhead, other.governance_overhead),
        )
        for comparison in comparisons:
            if comparison:
                return comparison
        return 0

    def payload(self) -> dict[str, float | int | None]:
        """Return the scorecard without collapsing unavailable fields into zero."""

        return {
            "verified_correctness": self.verified_correctness,
            "task_completion": self.task_completion,
            "safety_risk": self.safety_risk,
            "latency_ms": self.latency_ms,
            "tokens": self.tokens,
            "monetary_cost": self.monetary_cost,
            "governance_overhead": self.governance_overhead,
        }


@dataclass(frozen=True, slots=True)
class MarginalUtilityEstimate:
    """An auditable utility estimate that withholds unjustified scalar efficiency claims."""

    expected_utility: UtilityVector
    estimated_cost: GovernanceCost
    uncertainty: float
    confidence: float
    provenance: Mapping[str, str]
    commensurable_cost: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.expected_utility, UtilityVector):
            raise TypeError("expected_utility must be UtilityVector")
        if not isinstance(self.estimated_cost, GovernanceCost):
            raise TypeError("estimated_cost must be GovernanceCost")
        uncertainty = _finite_non_negative(self.uncertainty, "uncertainty")
        assert uncertainty is not None
        object.__setattr__(self, "uncertainty", uncertainty)
        object.__setattr__(self, "confidence", _confidence(self.confidence))
        if not isinstance(self.provenance, Mapping):
            raise TypeError("provenance must be a mapping")
        frozen_provenance: dict[str, str] = {}
        for key, value in self.provenance.items():
            if not isinstance(key, str) or not key:
                raise ValueError("provenance keys must be non-empty strings")
            if not isinstance(value, str) or not value:
                raise ValueError("provenance values must be non-empty strings")
            frozen_provenance[key] = value
        object.__setattr__(self, "provenance", MappingProxyType(frozen_provenance))
        commensurable_cost = _finite_non_negative(self.commensurable_cost, "commensurable_cost")
        if commensurable_cost == 0.0:
            raise ValueError("commensurable_cost must be positive when provided")
        object.__setattr__(self, "commensurable_cost", commensurable_cost)

    def scalar_emu(self) -> float | None:
        """Return a ratio only when verified utility and a comparable cost are both known."""

        verified_utility = self.expected_utility.verified_correctness
        if verified_utility is None or self.commensurable_cost is None:
            return None
        return verified_utility / self.commensurable_cost

    def scorecard(self) -> Mapping[str, Any]:
        """Return the structured estimate, retaining all unavailable measurements as ``None``."""

        return MappingProxyType(
            {
                "expected_utility": MappingProxyType(self.expected_utility.payload()),
                "estimated_cost": MappingProxyType(self.estimated_cost.payload()),
                "uncertainty": self.uncertainty,
                "confidence": self.confidence,
                "provenance": self.provenance,
                "scalar_emu": self.scalar_emu(),
            }
        )
