"""Claude Code hook output shapes.

Shadow Mode emits nothing. A hook that printed an advisory would change what the
model sees, which is exactly what Shadow Mode promises not to do, so the only
Shadow Mode output is an empty one and the recommendation goes to the ledger.

The blocking builders below encode the documented deny contract so a later Earned
Enforcement gate has a validated transport to use. Nothing in this integration
calls them yet: the adapter declares no blocking capability, and the core refuses
to run a non-blocking adapter in an enforcing mode.
"""

from __future__ import annotations

from typing import Any


def _reason_with_code(reason: str, reason_code: str) -> str:
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason must be a non-empty string")
    if not isinstance(reason_code, str) or not reason_code.strip():
        raise ValueError("reason_code must be a non-empty string")
    return f"{reason.strip()} [{reason_code.strip()}]"


def build_pre_tool_use_output(
    *, allowed: bool, reason: str, reason_code: str
) -> dict[str, Any] | None:
    """Build the documented Claude Code ``PreToolUse`` denial shape."""

    if allowed:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _reason_with_code(reason, reason_code),
        }
    }


def build_post_tool_use_output(
    *, blocked: bool, reason: str, reason_code: str
) -> dict[str, Any] | None:
    """Build the documented Claude Code ``PostToolUse`` blocking shape."""

    if not blocked:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "decision": "block",
            "reason": _reason_with_code(reason, reason_code),
        }
    }
