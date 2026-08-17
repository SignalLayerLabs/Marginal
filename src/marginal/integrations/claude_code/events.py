"""Strict value objects for the supported Claude Code hook lifecycle.

Field names follow the payloads Claude Code actually sends, verified against
Claude Code 2.1.233. Only the hooks MARGINAL has an explicit contract for are
parsed; anything else raises rather than being guessed at.

``transcript_path`` and ``prompt`` are deliberately never retained. The transcript
is outside the Decision Ledger privacy boundary and prompt material is not needed
to detect repeated work.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

SESSION_EVENTS = frozenset({"SessionStart", "SessionEnd"})
TOOL_EVENTS = frozenset({"PreToolUse", "PostToolUse", "PostToolUseFailure"})
SUPPORTED_EVENTS = SESSION_EVENTS | TOOL_EVENTS


@dataclass(frozen=True, slots=True)
class SessionEvent:
    session_id: str
    cwd: str
    hook_event_name: str
    source: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class PreToolUseEvent:
    session_id: str
    cwd: str
    hook_event_name: str
    tool_name: str
    tool_use_id: str
    tool_input: Mapping[str, Any]
    prompt_id: str = ""
    permission_mode: str = ""


@dataclass(frozen=True, slots=True)
class PostToolUseEvent:
    """A tool call Claude Code documents as having completed successfully."""

    session_id: str
    cwd: str
    hook_event_name: str
    tool_name: str
    tool_use_id: str
    tool_input: Mapping[str, Any]
    tool_response: Any
    prompt_id: str = ""
    permission_mode: str = ""
    duration_ms: float | None = None


@dataclass(frozen=True, slots=True)
class PostToolUseFailureEvent:
    """A tool call Claude Code documents as having failed.

    ``error`` is engine-supplied free text. It is used only to derive an evidence
    digest and is never written to the ledger.
    """

    session_id: str
    cwd: str
    hook_event_name: str
    tool_name: str
    tool_use_id: str
    tool_input: Mapping[str, Any]
    error: str
    prompt_id: str = ""
    permission_mode: str = ""
    duration_ms: float | None = None
    is_interrupt: bool = False


ClaudeCodeHookEvent = SessionEvent | PreToolUseEvent | PostToolUseEvent | PostToolUseFailureEvent


def _required_text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _optional_text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string or null")
    return value


def _optional_duration(payload: Mapping[str, Any]) -> float | None:
    value = payload.get("duration_ms")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("duration_ms must be a number or null")
    duration = float(value)
    if not math.isfinite(duration) or duration < 0.0:
        raise ValueError("duration_ms must be finite and non-negative")
    return duration


def _common(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "session_id": _required_text(payload, "session_id"),
        "cwd": _required_text(payload, "cwd"),
        "hook_event_name": _required_text(payload, "hook_event_name"),
    }


def _tool_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        raise ValueError("tool_input must be a mapping")
    return {
        "tool_name": _required_text(payload, "tool_name"),
        "tool_use_id": _required_text(payload, "tool_use_id"),
        "tool_input": dict(tool_input),
        "prompt_id": _optional_text(payload, "prompt_id"),
        "permission_mode": _optional_text(payload, "permission_mode"),
    }


def _tool_response(payload: Mapping[str, Any]) -> Any:
    """Accept either documented result key without inventing a value."""

    for key in ("tool_response", "tool_output"):
        if key in payload:
            return payload[key]
    raise ValueError("tool_response is required")


def parse_hook_event(payload: Mapping[str, Any]) -> ClaudeCodeHookEvent:
    """Parse only hook events for which MARGINAL has an explicit contract."""

    if not isinstance(payload, Mapping):
        raise TypeError("Claude Code hook payload must be a mapping")
    name = _required_text(payload, "hook_event_name")
    if name not in SUPPORTED_EVENTS:
        raise ValueError(f"unsupported Claude Code hook event: {name}")
    common = _common(payload)
    if name in SESSION_EVENTS:
        return SessionEvent(
            **common,
            source=_optional_text(payload, "source"),
            reason=_optional_text(payload, "reason"),
        )
    tool_fields = _tool_fields(payload)
    if name == "PreToolUse":
        return PreToolUseEvent(**common, **tool_fields)
    if name == "PostToolUse":
        return PostToolUseEvent(
            **common,
            **tool_fields,
            tool_response=_tool_response(payload),
            duration_ms=_optional_duration(payload),
        )
    is_interrupt = payload.get("is_interrupt", False)
    if not isinstance(is_interrupt, bool):
        raise ValueError("is_interrupt must be a boolean")
    return PostToolUseFailureEvent(
        **common,
        **tool_fields,
        error=_optional_text(payload, "error"),
        duration_ms=_optional_duration(payload),
        is_interrupt=is_interrupt,
    )
