"""Access the versioned JSON Schemas shipped with MARGINAL."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import PurePath
from typing import Any

_SCHEMA_PACKAGE = "marginal.schemas"


def available_schemas() -> tuple[str, ...]:
    """Return the packaged public schema names in deterministic order."""

    root = files(_SCHEMA_PACKAGE)
    return tuple(
        sorted(
            item.name for item in root.iterdir() if item.is_file() and item.name.endswith(".json")
        )
    )


def load_schema(name: str) -> dict[str, Any]:
    """Load one packaged schema by file name.

    Paths, traversal components, and unknown names are rejected so callers cannot use this
    helper as a generic package-resource reader.
    """

    if not isinstance(name, str):
        raise TypeError("schema name must be a string")
    if not name or PurePath(name).name != name or not name.endswith(".json"):
        raise ValueError("schema name must be a plain JSON file name")
    if name not in available_schemas():
        raise KeyError(f"unknown MARGINAL schema: {name}")
    text = files(_SCHEMA_PACKAGE).joinpath(name).read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"packaged schema {name!r} is not a JSON object")
    return payload
