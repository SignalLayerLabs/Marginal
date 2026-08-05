"""Stable fingerprints for semantic actions and guarded callable invocations."""

from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence, Set
from enum import Enum
from pathlib import Path
from typing import Any

from .models import Action


def _canonicalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("fingerprint values must contain only finite numbers")
        return value
    if isinstance(value, bytes):
        return {"$bytes": base64.b64encode(value).decode("ascii")}
    if isinstance(value, Path):
        return {"$path": str(value)}
    if isinstance(value, Enum):
        return {
            "$enum": f"{type(value).__module__}.{type(value).__qualname__}",
            "value": _canonicalize(value.value),
        }
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("fingerprint mappings require string keys")
        return {key: _canonicalize(item) for key, item in value.items()}
    if isinstance(value, Set) and not isinstance(value, (str, bytes, bytearray)):
        items = [_canonicalize(item) for item in value]
        return {
            "$set": sorted(
                items,
                key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
            )
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonicalize(item) for item in value]
    raise TypeError(
        f"unsupported fingerprint value {type(value).__module__}.{type(value).__qualname__}; "
        "provide an explicit Action.fingerprint"
    )


def _digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        _canonicalize(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_action(action: Action) -> str:
    """Return a stable SHA-256 fingerprint for an action's declared semantic inputs."""

    return _digest(
        {
            "name": action.name,
            "kind": action.kind,
            "is_verification": action.is_verification,
            "metadata": dict(action.metadata),
        }
    )


def fingerprint_call(
    action: Action,
    function: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
) -> str:
    """Fingerprint an action together with its callable and invocation inputs."""

    module = getattr(function, "__module__", type(function).__module__)
    qualname = getattr(function, "__qualname__", type(function).__qualname__)
    return _digest(
        {
            "action": {
                "name": action.name,
                "kind": action.kind,
                "is_verification": action.is_verification,
                "metadata": dict(action.metadata),
            },
            "callable": f"{module}.{qualname}",
            "args": args,
            "kwargs": dict(kwargs),
        }
    )
