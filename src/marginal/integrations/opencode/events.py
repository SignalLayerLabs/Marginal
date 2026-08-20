"""Strict value objects for the OpenCode plugin bridge protocol.

The plugin runs inside the OpenCode process and speaks newline-delimited JSON to a
bridge process. Verified against OpenCode 1.18.18.

The plugin deliberately does not send tool output. It sends a digest of the result
and a small allowlist of outcome signals, so no file content or command output ever
crosses into MARGINAL, not even in memory.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

OPERATIONS = frozenset({"session_start", "tool_start", "tool_end", "session_end", "status"})


@dataclass(frozen=True, slots=True)
class SessionRequest:
    """Opening or closing one OpenCode session."""

    session_id: str
    workspace: str


@dataclass(frozen=True, slots=True)
class ToolStartRequest:
    session_id: str
    call_id: str
    tool_name: str
    arguments: Mapping[str, Any]
    workspace: str = ""


@dataclass(frozen=True, slots=True)
class ToolEndRequest:
    """A completed tool call, described only by digest and outcome signals."""

    session_id: str
    call_id: str
    tool_name: str
    arguments: Mapping[str, Any]
    evidence_digest: str
    signals: Mapping[str, Any]
    duration_ms: float | None = None


OpenCodeRequest = SessionRequest | ToolStartRequest | ToolEndRequest


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


def _mapping(payload: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


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


def parse_request(operation: str, payload: Mapping[str, Any]) -> OpenCodeRequest:
    """Parse one bridge request for an operation that carries a payload."""

    if not isinstance(payload, Mapping):
        raise TypeError("bridge payload must be a mapping")
    if operation in {"session_start", "session_end"}:
        return SessionRequest(
            session_id=_required_text(payload, "session_id"),
            workspace=_required_text(payload, "workspace"),
        )
    if operation == "tool_start":
        return ToolStartRequest(
            session_id=_required_text(payload, "session_id"),
            call_id=_required_text(payload, "call_id"),
            tool_name=_required_text(payload, "tool_name"),
            arguments=_mapping(payload, "arguments"),
            workspace=_optional_text(payload, "workspace"),
        )
    if operation == "tool_end":
        return ToolEndRequest(
            session_id=_required_text(payload, "session_id"),
            call_id=_required_text(payload, "call_id"),
            tool_name=_required_text(payload, "tool_name"),
            arguments=_mapping(payload, "arguments"),
            evidence_digest=_optional_text(payload, "evidence_digest"),
            signals=_mapping(payload, "signals"),
            duration_ms=_optional_duration(payload),
        )
    raise ValueError(f"unsupported bridge operation: {operation}")
