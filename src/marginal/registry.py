"""Registry for explicitly versioned value estimators."""

from __future__ import annotations

from typing import Protocol

from .estimator import EstimatorIdentity
from .models import Action


class RegisteredEstimator(Protocol):
    identity: EstimatorIdentity

    def estimate(self, action: Action) -> float: ...


class EstimatorRegistry:
    """Resolve estimators by stable ``(name, version)`` identity."""

    def __init__(self) -> None:
        self._estimators: dict[tuple[str, str], RegisteredEstimator] = {}

    def register(self, estimator: RegisteredEstimator) -> None:
        key = estimator.identity.key
        if key in self._estimators:
            raise ValueError(
                f"estimator {estimator.identity.name}@{estimator.identity.version} "
                "is already registered"
            )
        self._estimators[key] = estimator

    def resolve(self, name: str, version: str) -> RegisteredEstimator:
        try:
            return self._estimators[(name, version)]
        except KeyError as exc:
            raise KeyError(f"unknown estimator {name}@{version}") from exc

    def identities(self) -> tuple[EstimatorIdentity, ...]:
        return tuple(
            estimator.identity
            for _, estimator in sorted(self._estimators.items(), key=lambda item: item[0])
        )
