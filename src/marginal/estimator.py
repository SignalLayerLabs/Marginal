"""Transparent, versioned estimates for an action's expected success gain."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .models import Action


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EstimatorIdentity:
    """Stable identity for an estimator implementation and configuration."""

    name: str
    version: str
    config_hash: str
    training_data_fingerprint: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("name", "version", "config_hash"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.training_data_fingerprint is not None:
            if not isinstance(self.training_data_fingerprint, str):
                raise TypeError("training_data_fingerprint must be a string or None")
            if not self.training_data_fingerprint.strip():
                raise ValueError("training_data_fingerprint must not be empty")

    @property
    def key(self) -> tuple[str, str]:
        return self.name, self.version

    def to_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "version": self.version,
            "config_hash": self.config_hash,
            "training_data_fingerprint": self.training_data_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ValueEstimate:
    """Expected gain with uncertainty and provenance metadata."""

    expected_gain: float
    uncertainty: float
    confidence: float
    sample_size: int
    provenance: str
    estimator: EstimatorIdentity

    def __post_init__(self) -> None:
        for name, value in (
            ("expected_gain", self.expected_gain),
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
        if isinstance(self.sample_size, bool) or not isinstance(self.sample_size, int):
            raise TypeError("sample_size must be an integer")
        if self.sample_size < 0:
            raise ValueError("sample_size must be non-negative")
        if not isinstance(self.provenance, str):
            raise TypeError("provenance must be a string")
        if not self.provenance.strip():
            raise ValueError("provenance must not be empty")
        if not isinstance(self.estimator, EstimatorIdentity):
            raise TypeError("estimator must be EstimatorIdentity")


class ValueEstimator:
    """Estimate expected gain from explicit values or contextual observations.

    The implementation is deliberately transparent. It does not claim causal attribution:
    callers must explicitly provide action-level realized gain through ``observe_action``.
    """

    def __init__(
        self,
        default_gain: float = 0.05,
        *,
        name: str = "historical-mean",
        version: str = "2.0.0",
        context_fields: tuple[str, ...] = ("engine", "phase", "task_type", "language", "model"),
        training_data_fingerprint: str | None = None,
    ) -> None:
        self.default_gain = self._validated_gain(default_gain, name="default_gain")
        if not isinstance(name, str):
            raise TypeError("name must be a string")
        if not name.strip():
            raise ValueError("name must not be empty")
        if not isinstance(version, str):
            raise TypeError("version must be a string")
        if not version.strip():
            raise ValueError("version must not be empty")
        if not isinstance(context_fields, tuple):
            raise TypeError("context_fields must be a tuple of strings")
        if any(not isinstance(field, str) or not field.strip() for field in context_fields):
            raise ValueError("context_fields must contain non-empty strings")
        if len(set(context_fields)) != len(context_fields):
            raise ValueError("context_fields must be unique")
        self.context_fields = context_fields
        self._kind_observations: dict[str, list[float]] = defaultdict(list)
        self._context_observations: dict[tuple[str, tuple[str, ...]], list[float]] = defaultdict(
            list
        )
        self._base_training_data_fingerprint = training_data_fingerprint
        config_hash = _stable_hash(
            {"default_gain": self.default_gain, "context_fields": self.context_fields}
        )
        self.identity = EstimatorIdentity(
            name=name,
            version=version,
            config_hash=config_hash,
            training_data_fingerprint=training_data_fingerprint,
        )

    def observe(self, action_kind: str, realized_gain: float) -> None:
        if not isinstance(action_kind, str) or not action_kind.strip():
            raise ValueError("action_kind must not be empty")
        self._kind_observations[action_kind].append(
            self._validated_gain(realized_gain, name="realized_gain")
        )
        self._refresh_identity()

    def observe_action(self, action: Action, realized_gain: float) -> None:
        gain = self._validated_gain(realized_gain, name="realized_gain")
        self._kind_observations[action.kind].append(gain)
        context = self._context_key(action)
        if context is not None:
            self._context_observations[(action.kind, context)].append(gain)
        self._refresh_identity()

    def estimate(self, action: Action) -> float:
        return self.estimate_detail(action).expected_gain

    def estimate_detail(self, action: Action) -> ValueEstimate:
        if action.expected_gain is not None:
            return ValueEstimate(
                expected_gain=action.expected_gain,
                uncertainty=0.0,
                confidence=1.0,
                sample_size=0,
                provenance="action.expected_gain",
                estimator=self.identity,
            )

        context = self._context_key(action)
        if context is not None:
            observations = self._context_observations.get((action.kind, context))
            if observations:
                return self._historical_estimate(
                    observations, provenance=f"historical:context:{action.kind}"
                )

        observations = self._kind_observations.get(action.kind)
        if observations:
            return self._historical_estimate(
                observations, provenance=f"historical:kind:{action.kind}"
            )

        return ValueEstimate(
            expected_gain=self.default_gain,
            uncertainty=0.5,
            confidence=0.0,
            sample_size=0,
            provenance="default_gain",
            estimator=self.identity,
        )

    def _historical_estimate(self, observations: list[float], *, provenance: str) -> ValueEstimate:
        sample_size = len(observations)
        mean = statistics.fmean(observations)
        uncertainty = (
            statistics.stdev(observations) / math.sqrt(sample_size) if sample_size > 1 else 0.5
        )
        confidence = sample_size / (sample_size + 5.0)
        return ValueEstimate(
            expected_gain=mean,
            uncertainty=uncertainty,
            confidence=confidence,
            sample_size=sample_size,
            provenance=provenance,
            estimator=self.identity,
        )

    def _context_key(self, action: Action) -> tuple[str, ...] | None:
        values: list[str] = []
        any_value = False
        for field in self.context_fields:
            value = action.metadata.get(field)
            normalized = "" if value is None else str(value)
            values.append(normalized)
            any_value = any_value or bool(normalized)
        return tuple(values) if any_value else None

    def _refresh_identity(self) -> None:
        kind_observations = {
            kind: sorted(values) for kind, values in sorted(self._kind_observations.items())
        }
        context_observations = [
            {
                "kind": kind,
                "context": list(context),
                "values": sorted(values),
            }
            for (kind, context), values in sorted(self._context_observations.items())
        ]
        training_data_fingerprint = _stable_hash(
            {
                "base": self._base_training_data_fingerprint,
                "kind_observations": kind_observations,
                "context_observations": context_observations,
            }
        )
        self.identity = EstimatorIdentity(
            name=self.identity.name,
            version=self.identity.version,
            config_hash=self.identity.config_hash,
            training_data_fingerprint=training_data_fingerprint,
        )

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
