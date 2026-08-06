"""Provider-neutral value objects used throughout MARGINAL."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


def _validate_non_negative_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Measured token breakdown for one model or agent action.

    ``total_tokens`` is calculated from the component fields when omitted. Cached input is
    intentionally represented separately because providers may price it differently.
    """

    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int | None = None

    def __post_init__(self) -> None:
        components = (
            _validate_non_negative_int("input_tokens", self.input_tokens),
            _validate_non_negative_int("cached_input_tokens", self.cached_input_tokens),
            _validate_non_negative_int("output_tokens", self.output_tokens),
            _validate_non_negative_int("reasoning_tokens", self.reasoning_tokens),
        )
        calculated = sum(components)
        if self.total_tokens is None:
            object.__setattr__(self, "total_tokens", calculated)
            return
        total = _validate_non_negative_int("total_tokens", self.total_tokens)
        if total != calculated:
            raise ValueError(
                "total_tokens must equal input_tokens + cached_input_tokens + "
                "output_tokens + reasoning_tokens"
            )


@dataclass(frozen=True, slots=True)
class Cost:
    """Estimated or actual resource cost for one agent action."""

    tokens: int = 0
    usd: float = 0.0
    latency_ms: int = 0
    risk: float = 0.0

    def __post_init__(self) -> None:
        _validate_non_negative_int("tokens", self.tokens)
        _validate_non_negative_int("latency_ms", self.latency_ms)
        for name, value in (("usd", self.usd), ("risk", self.risk)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if not math.isfinite(float(value)):
                raise ValueError("cost values must be finite")
        if self.usd < 0 or self.risk < 0:
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
    """An explainable applied decision and its underlying recommendation.

    ``allowed`` describes the behavior applied by the current execution mode.
    ``recommended`` describes the policy recommendation before shadow/recommend overrides.
    Existing v0.1 callers can continue to inspect only ``allowed`` and ``reason``.
    """

    allowed: bool
    reason: str
    score: float = 0.0
    expected_gain: float = 0.0
    estimated_cost_value: float = 0.0
    recommended: bool | None = None
    recommendation_reason: str | None = None
    reason_code: str = "UNSPECIFIED"
    recommendation_reason_code: str | None = None
    mode: str = "enforce"
    uncertainty: float = 0.0
    confidence: float = 0.0
    estimator_name: str = ""
    estimator_version: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise TypeError("allowed must be a boolean")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must not be empty")
        if self.recommended is None:
            object.__setattr__(self, "recommended", self.allowed)
        elif not isinstance(self.recommended, bool):
            raise TypeError("recommended must be a boolean or None")
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ValueError("reason_code must not be empty")
        for name, value in (
            ("score", self.score),
            ("expected_gain", self.expected_gain),
            ("estimated_cost_value", self.estimated_cost_value),
            ("uncertainty", self.uncertainty),
            ("confidence", self.confidence),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, float(value))
        if not 0.0 <= self.expected_gain <= 1.0:
            raise ValueError("expected_gain must be between 0 and 1")
        if self.uncertainty < 0:
            raise ValueError("uncertainty must be non-negative")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class Allocation:
    """A funded candidate and the decision that justified its reservation."""

    action: Action
    decision: Decision
