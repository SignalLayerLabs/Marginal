"""Provider-neutral value objects used throughout MARGINAL."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class Cost:
    """Estimated or actual resource cost for one agent action."""

    tokens: int = 0
    usd: float = 0.0
    latency_ms: int = 0
    risk: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.tokens, bool) or not isinstance(self.tokens, int):
            raise TypeError("tokens must be an integer")
        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, int):
            raise TypeError("latency_ms must be an integer")
        for name, value in (("usd", self.usd), ("risk", self.risk)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if not math.isfinite(float(value)):
                raise ValueError("cost values must be finite")
        if self.tokens < 0 or self.latency_ms < 0 or self.usd < 0 or self.risk < 0:
            raise ValueError("cost values must be non-negative")
        object.__setattr__(self, "usd", float(self.usd))
        object.__setattr__(self, "risk", float(self.risk))

    def __add__(self, other: Cost) -> Cost:
        return Cost(
            tokens=self.tokens + other.tokens,
            usd=self.usd + other.usd,
            latency_ms=self.latency_ms + other.latency_ms,
            risk=self.risk + other.risk,
        )


@dataclass(frozen=True, slots=True)
class Action:
    """A proposed unit of agent work that may consume budget."""

    name: str
    kind: str
    cost: Cost = field(default_factory=Cost)
    expected_gain: float | None = None
    current_success_probability: float = 0.0
    is_verification: bool = False
    fingerprint: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not self.name.strip():
            raise ValueError("action name must not be empty")
        if not isinstance(self.kind, str):
            raise TypeError("kind must be a string")
        if not self.kind.strip():
            raise ValueError("action kind must not be empty")
        if not isinstance(self.cost, Cost):
            raise TypeError("cost must be Cost")
        if not isinstance(self.is_verification, bool):
            raise TypeError("is_verification must be a boolean")
        if self.fingerprint is not None:
            if not isinstance(self.fingerprint, str):
                raise TypeError("fingerprint must be a string or None")
            if not self.fingerprint.strip():
                raise ValueError("fingerprint must not be empty")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")

        if self.expected_gain is not None:
            if isinstance(self.expected_gain, bool) or not isinstance(
                self.expected_gain, (int, float)
            ):
                raise TypeError("expected_gain must be a number")
            expected_gain = float(self.expected_gain)
            if not math.isfinite(expected_gain):
                raise ValueError("expected_gain must be finite")
            if not 0.0 <= expected_gain <= 1.0:
                raise ValueError("expected_gain must be between 0 and 1")
            object.__setattr__(self, "expected_gain", expected_gain)

        if isinstance(self.current_success_probability, bool) or not isinstance(
            self.current_success_probability, (int, float)
        ):
            raise TypeError("current_success_probability must be a number")
        current_probability = float(self.current_success_probability)
        if not math.isfinite(current_probability):
            raise ValueError("current_success_probability must be finite")
        if not 0.0 <= current_probability <= 1.0:
            raise ValueError("current_success_probability must be between 0 and 1")
        object.__setattr__(self, "current_success_probability", current_probability)
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class Decision:
    """An explainable authorization decision."""

    allowed: bool
    reason: str
    score: float = 0.0
    expected_gain: float = 0.0
    estimated_cost_value: float = 0.0


@dataclass(frozen=True, slots=True)
class Allocation:
    """A funded candidate and the decision that justified its reservation."""

    action: Action
    decision: Decision
