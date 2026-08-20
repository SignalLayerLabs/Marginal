"""Exact public-model identity resolution for MARGINAL Commons."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

_REVIEWED_MODELS = {
    "gpt-5.6-sol": "openai/gpt-5.6-sol",
    "gpt-5.6-terra": "openai/gpt-5.6-terra",
    "gpt-5.6-luna": "openai/gpt-5.6-luna",
}


@dataclass(frozen=True, slots=True)
class CanonicalModelIdentity:
    """One registry-issued public model identity."""

    provider: str
    model: str
    namespace: str
    registry_version: str


def _registry() -> tuple[str, dict[str, str]]:
    resource = files("marginal.commons").joinpath("canonical-model-registry-v1.json")
    payload: Any = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise RuntimeError("canonical model registry is invalid")
    models = payload.get("models")
    if not isinstance(models, dict) or not all(
        isinstance(model, str) and isinstance(namespace, str) for model, namespace in models.items()
    ):
        raise RuntimeError("canonical model registry is invalid")
    parsed = dict(models)
    if parsed != _REVIEWED_MODELS:
        raise RuntimeError("canonical model registry contains an unreviewed model")
    return "1.0", parsed


def resolve_canonical_model(*, provider: str, model: str) -> CanonicalModelIdentity | None:
    """Resolve only an exact, case-sensitive reviewed registry entry."""

    if not isinstance(provider, str) or not isinstance(model, str) or provider != "openai":
        return None
    version, models = _registry()
    namespace = models.get(model)
    if namespace is None:
        return None
    return CanonicalModelIdentity(provider, model, namespace, version)


def resolve_model_attribution(
    observations: Iterable[tuple[str, str]],
) -> CanonicalModelIdentity | None:
    """Resolve a batch only when every observation has one identical safe identity."""

    if isinstance(observations, (str, bytes)):
        return None
    resolved: set[CanonicalModelIdentity] = set()
    seen = False
    try:
        for provider, model in observations:
            seen = True
            identity = resolve_canonical_model(provider=provider, model=model)
            if identity is None:
                return None
            resolved.add(identity)
    except (TypeError, ValueError):
        return None
    if not seen or len(resolved) != 1:
        return None
    return next(iter(resolved))


def is_canonical_namespace(namespace: object) -> bool:
    """Return whether a value is one exact registry-issued namespace."""

    if not isinstance(namespace, str):
        return False
    _, models = _registry()
    return namespace in models.values()


def resolve_canonical_namespace(namespace: object) -> CanonicalModelIdentity | None:
    """Resolve one exact reviewed namespace back to its canonical identity."""

    if not isinstance(namespace, str):
        return None
    version, models = _registry()
    for model, registered_namespace in models.items():
        if namespace == registered_namespace:
            return CanonicalModelIdentity("openai", model, namespace, version)
    return None


def identity_is_canonical(identity: object) -> bool:
    """Reject forged value objects that were not derived from the exact registry mapping."""

    if not isinstance(identity, CanonicalModelIdentity):
        return False
    return resolve_canonical_model(provider=identity.provider, model=identity.model) == identity
