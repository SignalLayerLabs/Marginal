"""Append-only, provider-neutral execution traces."""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .budget import BudgetUsage
from .models import Action, Decision


class TraceSink(Protocol):
    def emit(self, event: Mapping[str, Any]) -> None: ...


class NullTraceSink:
    def emit(self, event: Mapping[str, Any]) -> None:
        del event


class JsonlTraceSink:
    """Write one self-contained JSON object per line."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def emit(self, event: Mapping[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **dict(event),
        }
        encoded = json.dumps(record, sort_keys=True, ensure_ascii=False, default=repr)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded + "\n")


def action_payload(action: Action) -> dict[str, Any]:
    return {
        "name": action.name,
        "kind": action.kind,
        "cost": asdict(action.cost),
        "expected_gain": action.expected_gain,
        "current_success_probability": action.current_success_probability,
        "is_verification": action.is_verification,
        "fingerprint": action.fingerprint,
        "metadata": dict(action.metadata),
    }


def decision_payload(decision: Decision) -> dict[str, Any]:
    return asdict(decision)


def usage_payload(usage: BudgetUsage) -> dict[str, Any]:
    return asdict(usage)
