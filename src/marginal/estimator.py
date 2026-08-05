"""Simple calibrated estimates for an action's expected success gain."""

from __future__ import annotations

import math
from collections import defaultdict

from .models import Action


class ValueEstimator:
    """Estimate expected gain from explicit values or observed action history.

    The estimator deliberately stays small and transparent. Applications can replace it
    with any object exposing ``estimate(Action) -> float``.
    """

    def __init__(self, default_gain: float = 0.05) -> None:
        self.default_gain = self._validated_gain(default_gain, name="default_gain")
        self._observations: dict[str, list[float]] = defaultdict(list)

    def observe(self, action_kind: str, realized_gain: float) -> None:
        if not action_kind.strip():
            raise ValueError("action_kind must not be empty")
        gain = self._validated_gain(realized_gain, name="realized_gain")
        self._observations[action_kind].append(gain)

    def estimate(self, action: Action) -> float:
        if action.expected_gain is not None:
            return action.expected_gain
        observations = self._observations.get(action.kind)
        if not observations:
            return self.default_gain
        return sum(observations) / len(observations)

    @staticmethod
    def _validated_gain(value: float, *, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be a number")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"{name} must be finite")
        if not 0.0 <= result <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1")
        return result
