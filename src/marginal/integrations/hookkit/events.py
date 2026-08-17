"""Engine-neutral value objects for hook-based agent integrations.

Every supported engine reports a slightly different hook payload. An adapter is
responsible for parsing its own native payload and for declaring what that engine
can actually prove; ``hookkit`` never guesses. These objects carry only the
minimum an adapter must supply for lifecycle correlation and repetition control.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from marginal.controls import ActionOutcomeStatus


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _optional_text(value: Any, name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string or None")
    return value


@dataclass(frozen=True, slots=True)
class SessionBoundary:
    """Start or end of one engine session."""

    engine: str
    session_id: str
    workspace: str
    kind: str
    source: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        for name in ("engine", "session_id", "workspace", "kind"):
            _required_text(getattr(self, name), name)
        if self.kind not in {"start", "end"}:
            raise ValueError("kind must be 'start' or 'end'")
        object.__setattr__(self, "source", _optional_text(self.source, "source"))
        object.__setattr__(self, "reason", _optional_text(self.reason, "reason"))


@dataclass(frozen=True, slots=True)
class ToolCallStart:
    """A tool call an engine proposes to execute.

    ``turn_id`` is optional because engines disagree about turn identity. It is
    recorded when available and never invented.
    """

    session_id: str
    call_id: str
    tool_name: str
    tool_input: Mapping[str, Any] = field(default_factory=dict)
    turn_id: str = ""

    def __post_init__(self) -> None:
        for name in ("session_id", "call_id", "tool_name"):
            _required_text(getattr(self, name), name)
        if not isinstance(self.tool_input, Mapping):
            raise TypeError("tool_input must be a mapping")
        object.__setattr__(self, "tool_input", dict(self.tool_input))
        object.__setattr__(self, "turn_id", _optional_text(self.turn_id, "turn_id"))


@dataclass(frozen=True, slots=True)
class ToolCallEnd:
    """A completed tool call with the outcome its engine can actually prove.

    ``outcome`` must be ``UNKNOWN`` unless the engine documents the signal the
    adapter derived it from. ``evidence`` is any JSON-compatible completion
    evidence; only its hash is retained. ``duration_ms`` is engine-measured
    latency when the engine reports it.
    """

    session_id: str
    call_id: str
    tool_name: str
    outcome: ActionOutcomeStatus
    tool_input: Mapping[str, Any] = field(default_factory=dict)
    evidence: Any = None
    duration_ms: float | None = None
    turn_id: str = ""

    def __post_init__(self) -> None:
        for name in ("session_id", "call_id", "tool_name"):
            _required_text(getattr(self, name), name)
        object.__setattr__(self, "outcome", ActionOutcomeStatus.parse(self.outcome))
        if not isinstance(self.tool_input, Mapping):
            raise TypeError("tool_input must be a mapping")
        object.__setattr__(self, "tool_input", dict(self.tool_input))
        object.__setattr__(self, "turn_id", _optional_text(self.turn_id, "turn_id"))
        duration = self.duration_ms
        if duration is None:
            return
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise TypeError("duration_ms must be a number or None")
        value = float(duration)
        if not math.isfinite(value) or value < 0.0:
            raise ValueError("duration_ms must be finite and non-negative")
        object.__setattr__(self, "duration_ms", value)


HookEvent = SessionBoundary | ToolCallStart | ToolCallEnd
