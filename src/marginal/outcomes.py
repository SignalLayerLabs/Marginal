"""Provider-neutral contracts for verified task outcomes."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class Outcome:
    """A measured task outcome, kept separate from action-level realized gain."""

    task_id: str
    reward: float
    resolved: bool | None = None
    verifier: str = ""
    trajectory_id: str = ""
    evidence: Mapping[str, Any] = field(default_factory=dict)
    metrics: Mapping[str, float | int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise ValueError("task_id must not be empty")
        if isinstance(self.reward, bool) or not isinstance(self.reward, (int, float)):
            raise TypeError("reward must be a number")
        reward = float(self.reward)
        if not math.isfinite(reward):
            raise ValueError("reward must be finite")
        if self.resolved is not None and not isinstance(self.resolved, bool):
            raise TypeError("resolved must be a boolean or None")
        for name in ("verifier", "trajectory_id"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be a string")
        if not isinstance(self.evidence, Mapping):
            raise TypeError("evidence must be a mapping")
        if not isinstance(self.metrics, Mapping):
            raise TypeError("metrics must be a mapping")
        normalized_metrics: dict[str, float | int] = {}
        for name, value in self.metrics.items():
            if not isinstance(name, str) or not name:
                raise ValueError("metric names must be non-empty strings")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError("metric values must be numbers")
            if not math.isfinite(float(value)):
                raise ValueError("metric values must be finite")
            normalized_metrics[name] = value
        object.__setattr__(self, "reward", reward)
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))
        object.__setattr__(self, "metrics", MappingProxyType(normalized_metrics))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "reward": self.reward,
            "resolved": self.resolved,
            "verifier": self.verifier,
            "trajectory_id": self.trajectory_id,
            "evidence": dict(self.evidence),
            "metrics": dict(self.metrics),
        }
