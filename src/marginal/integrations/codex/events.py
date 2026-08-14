"""Strict, minimal value objects for the supported Codex hook lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SessionEvent:
    session_id: str
    cwd: str
    hook_event_name: str
    model: str
    permission_mode: str
    transcript_path: str | None = None
    source: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class PreToolUseEvent:
    session_id: str
    cwd: str
    hook_event_name: str
    model: str
    permission_mode: str
    turn_id: str
    tool_name: str
    tool_use_id: str
    tool_input: Mapping[str, Any]
    transcript_path: str | None = None


@dataclass(frozen=True, slots=True)
class PostToolUseEvent:
    session_id: str
    cwd: str
    hook_event_name: str
    model: str
    permission_mode: str
    turn_id: str
    tool_name: str
    tool_use_id: str
    tool_input: Mapping[str, Any]
    tool_response: Any
    transcript_path: str | None = None


@dataclass(frozen=True, slots=True)
class UserPromptSubmitEvent:
    session_id: str
    cwd: str
    hook_event_name: str
    model: str
    permission_mode: str
    prompt: str
    transcript_path: str | None = None


CodexHookEvent = SessionEvent | PreToolUseEvent | PostToolUseEvent | UserPromptSubmitEvent


def _required_text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _optional_text(payload: Mapping[str, Any], name: str) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string or null")
    return value


def _common(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "session_id": _required_text(payload, "session_id"),
        "cwd": _required_text(payload, "cwd"),
        "hook_event_name": _required_text(payload, "hook_event_name"),
        "model": _required_text(payload, "model"),
        "permission_mode": _required_text(payload, "permission_mode"),
        "transcript_path": _optional_text(payload, "transcript_path"),
    }


def _tool_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        raise ValueError("tool_input must be a mapping")
    return {
        "turn_id": _required_text(payload, "turn_id"),
        "tool_name": _required_text(payload, "tool_name"),
        "tool_use_id": _required_text(payload, "tool_use_id"),
        "tool_input": dict(tool_input),
    }


def parse_hook_event(payload: Mapping[str, Any]) -> CodexHookEvent:
    """Parse only hook events for which MARGINAL has an explicit contract."""

    if not isinstance(payload, Mapping):
        raise TypeError("Codex hook payload must be a mapping")
    name = _required_text(payload, "hook_event_name")
    common = _common(payload)
    if name in {"SessionStart", "SessionEnd"}:
        return SessionEvent(
            **common,
            source=_optional_text(payload, "source"),
            reason=_optional_text(payload, "reason"),
        )
    if name == "PreToolUse":
        return PreToolUseEvent(**common, **_tool_fields(payload))
    if name == "PostToolUse":
        if "tool_response" not in payload:
            raise ValueError("tool_response is required")
        return PostToolUseEvent(
            **common,
            **_tool_fields(payload),
            tool_response=payload["tool_response"],
        )
    if name == "UserPromptSubmit":
        return UserPromptSubmitEvent(**common, prompt=_required_text(payload, "prompt"))
    raise ValueError(f"unsupported Codex hook event: {name}")


def _reason_with_code(reason: str, reason_code: str) -> str:
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason must be a non-empty string")
    if not isinstance(reason_code, str) or not reason_code.strip():
        raise ValueError("reason_code must be a non-empty string")
    return f"{reason.strip()} [{reason_code.strip()}]"


def build_pre_tool_output(*, allowed: bool, reason: str, reason_code: str) -> dict[str, Any] | None:
    """Build the documented Codex PreToolUse denial shape."""

    if allowed:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _reason_with_code(reason, reason_code),
        }
    }


def build_post_tool_output(
    *, blocked: bool, reason: str, reason_code: str
) -> dict[str, str] | None:
    """Build the documented Codex PostToolUse result-blocking shape."""

    if not blocked:
        return None
    return {"decision": "block", "reason": _reason_with_code(reason, reason_code)}
